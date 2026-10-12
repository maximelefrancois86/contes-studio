# Architecture

## Vue d'ensemble

Un seul processus Python (FastAPI) sert l'interface web, les outils d'écriture et, plus tard, les
opérations sur la conteuse. Pas de serveur Java, pas de CORS, pas de proxy.

```
navigateur ──HTTP──▶ contes_studio.server (FastAPI, 127.0.0.1:8090)
                        ├── workspace.py   packs YAML : lecture, édition ligne par ligne
                        ├── voix.py        voix en cache (.cache/tts/qwen3/…)
                        ├── (à venir) jobs.py      tâches GPU en file : synthèse, images, musiques
                        ├── (à venir) sons.py      recherche Freesound CC0
                        ├── (à venir) archive.py   lecture et écriture des archives STUdio
                        └── (à venir) device/      conteuse : détection, index, conversion, chiffrement
                     lunii_gen (générateur) : TTS Qwen3, ComfyUI, mixage, archive
```

**Source de vérité : le YAML.** Une histoire est un fichier `histoires/<pack>.yaml` (format du
générateur : `voix`, `questions`, `histoires` ou `etapes`, `sons`). L'atelier ne réécrit que la
ligne modifiée, vérifie le pack avec le chargeur du générateur, puis remplace le fichier d'un coup :
un agent IA et un humain peuvent travailler sur les mêmes fichiers, et les commentaires (univers,
plans) restent en place.

**Voix.** La clé de cache est celle du générateur (texte prononcé, voix, ton, réglages du modèle) :
l'atelier retrouve le fichier d'une réplique sans charger le modèle. Une réplique modifiée n'a plus
de voix en cache, elle est signalée et sera synthétisée au prochain build.

## Formats de la conteuse à porter en Python

Inventaire établi sur STUdio 0.4.2 (tag `0.4.2`, commit `ec6f378`). Les chemins renvoient au code
Java de STUdio. À croiser avec Lunii.QT (Python, GPL-3.0), déjà testé sur v1, v2 et v3.

**Détection.** Identifiants USB : `0c45:6820` (fw1), `0c45:6840` (fw2), `0483:a341` (v2 et v3)
(`driver/.../LibUsbDetectionHelper.java:23-28`). On cherche ensuite un point de montage qui contient
un fichier `.md` (`FsStoryTellerAsyncDriver.java:58-99`). En Python : `/proc/mounts` ou
`psutil.disk_partitions()`, et pyudev pour les branchements. Les appareils v1 « raw » ne sont pas
portés.

**Fichier `.md`** (`FsStoryTellerAsyncDriver.java:110-224`), version en u16 petit-boutiste à
l'octet 0 :

- md v1 à v3 (firmware 2) : version majeure et mineure (u16 LE aux octets 6 et 8), numéro de série
  (i64 gros-boutiste à l'octet 10), identifiant de l'appareil (256 octets à l'octet 256) ;
- md v6 et v7 (firmware 3) : version (chiffres ASCII aux octets 2 et 4), numéro de série (24 octets
  ASCII à l'octet 26), clé AES, vecteur d'initialisation et fichier `bt` tirés du `.md` lui-même
  (v6 : du numéro de série ; v7 : des octets 64 à 95). Rien d'autre n'est nécessaire.
- Ces clés sont propres à l'appareil : ne jamais les journaliser ni les renvoyer à l'interface
  (STUdio les expose dans `/api/device/infos`, on ne le reproduit pas).

**Index des packs `.pi`.** Suite d'UUID de 16 octets, gros-boutistes. Dossier d'un pack :
`.content/<8 derniers caractères hexadécimaux de l'UUID, en majuscules>`. Écriture via `.pi.new`
puis remplacement.

**Conversion archive → format FS** (`LibraryService.java:306-372`,
`PackAssetsCompression.java:151-204`, `FsStoryPackWriter.java:45-326`) :

- `ni` : en-tête de 512 octets (u16 1, u16 version du pack, i32 512, i32 44, nombre de nœuds,
  d'images, de sons, u8 1), puis un enregistrement de 44 octets par nœud : index image, index son,
  transition OK (action, nombre d'options, option), transition maison (idem), cinq drapeaux u16
  (molette, OK, maison, pause, lecture auto), u16 0. −1 signifie « aucun ».
- `li` : index des nœuds de chaque action, à la suite. `ri` et `si` : chemins ASCII de 12 octets
  `000\NNNNNNNN` vers `rf/000/…` (images) et `sf/000/…` (sons). Assets dédupliqués par SHA-1.
- Images : BMP 4 bits compressé RLE4, 320×240 exactement, 16 couleurs. Pillow lit le RLE4 mais ne
  l'écrit pas : encodeur à écrire (environ 60 lignes, attention au remplissage).
- Sons : MP3 mono 44,1 kHz sans étiquettes ID3
  (`ffmpeg -ac 1 -ar 44100 -c:a libmp3lame -q:a 4 -map_metadata -1 -id3v2_version 0`). Un nœud sans
  son reçoit un MP3 silencieux, à générer nous-mêmes.

**Chiffrement** (`CipherUtils.java`, `AESCBCCipher.java`) : `ni` et `nm` restent en clair ; `li`,
`ri`, `si`, `rf/*`, `sf/*` sont chiffrés sur leurs 512 premiers octets. v3 : AES-CBC sans
remplissage (fichier court complété par des zéros jusqu'à un multiple de 16), clé et IV inversés par
mots de 32 bits. v2 : XXTEA avec une clé commune au micrologiciel. **Cette clé n'est pas
distribuée** : si la v2 est un jour prise en charge, l'utilisateur la fournit dans un fichier local.

**Archive STUdio (zip).** `story.json` + `assets/` + `thumbnail.png`. Les champs inconnus de
`story.json` sont ignorés par STUdio mais perdus s'il réenregistre le pack : nos métadonnées
(temps des répliques, crédits) vivent à côté, dans `<pack>.meta.json`.

## API de STUdio (liste de contrôle des fonctions)

| Groupe | Route | Rôle |
|---|---|---|
| appareil | `GET /api/device/infos`, `GET /api/device/packs` | état, packs présents |
| appareil | `POST /api/device/addFromLibrary`, `removeFromDevice`, `reorder`, `addToLibrary` | transfert, suppression, ordre, copie |
| bibliothèque | `GET /api/library/packs`, `POST upload`, `convert`, `download`, `remove` | gestion locale |
| événements | `storyteller.plugged`, `unplugged`, `transfer.<id>.progress` | branchement, progression |

Ici, les événements passeront par Server-Sent Events.

## À ne pas porter

L'agent Java qui s'accroche à l'application officielle, la base de métadonnées officielle (serveurs
de Lunii), le pilote v1 « raw », le vérificateur de mises à jour.
