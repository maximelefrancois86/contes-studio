# Feuille de route

Chaque étape doit être utilisable seule, testée, et ne jamais casser un pack existant.

## 0.1 — Éditeur de répliques (fait)

- Liste des packs, des histoires et des étapes d'aventure.
- Édition du texte, du personnage et du ton d'une réplique ; seule la ligne change dans le YAML ;
  pack vérifié avant enregistrement.
- Écoute des voix en cache, réplique par réplique ou enchaînées ; répliques à resynthétiser signalées.

## 0.2 — Voix

- File de tâches GPU (un seul travail à la fois, verrou partagé avec le générateur
  `~/.cache/lunii-gpu.lock`), progression en direct.
- « Refaire la voix » d'une réplique : nouvelle prise synthétique (graine différente), comparaison
  avec l'ancienne, choix de la prise gardée (champ `prise:` dans le YAML, pris en compte dans la clé
  de cache du générateur).
- Enregistrement au micro d'une réplique (MediaRecorder), normalisé au niveau des voix de synthèse,
  rangé dans `histoires/<pack>/voix/` et référencé dans le YAML.
- Édition des voix du casting : description, ton par défaut, plage de hauteur, écoute de la voix
  de référence.

## 0.3 — Sons et images

- Recherche Freesound (CC0 uniquement), écoute, ajout au catalogue `sons:` du pack avec auteur et
  licence ; insertion d'un bruitage entre deux répliques.
- Ambiances et musiques : génération (Stable Audio Open, MusicGen pour usage non commercial),
  réglage du niveau.
- Illustrations : génération ComfyUI, plusieurs propositions, choix, aperçu en 16 niveaux de gris
  comme sur l'écran de la conteuse.

## 0.4 — Directives pour l'agent IA

- Page « Directives » : brief d'écriture (`BRIEF.md`), règles de prononciation, consignes propres
  au pack, éditées dans l'atelier et lues par l'agent.
- Bouton « Vérifier » : vérificateur du générateur (incises, interjections, durée, histoires
  imbriquées) avec renvoi vers la ligne fautive.
- Demande à l'agent sur une sélection (« raccourcis cette scène », « ajoute une incise ») ; les
  modifications arrivent comme des propositions à accepter ou refuser.

## 0.5 — Graphe et aperçu

- Graphe des choix (questions, options, étapes, branches qui se rejoignent).
- Aperçu interactif : le lecteur du site d'écoute, branché sur le pack en cours.

## 0.6 — Conteuse sans Java

- Lecture du `.md` (v2, v3), liste des packs de l'appareil, suppression, ordre.
- Conversion archive → FS (ni, li, ri, si, BMP RLE4, MP3) et chiffrement v3 ; tests octet par octet
  contre la sortie de STUdio 0.4.2 sur les mêmes archives, puis sur une copie du dossier de
  l'appareil, puis sur l'appareil après sauvegarde.
- Remplacement de `gen/lunii_gen/deploy.py` (qui pilote STUdio par HTTP).

## Questions ouvertes

- Publier le générateur (`contes-gen`) pour que l'atelier soit utilisable par d'autres, ou en
  intégrer les parties utiles ici.
- Renommer le paquet `lunii_gen` avant toute publication (RULES.md §2).
