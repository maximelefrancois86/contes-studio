# Feuille de route

**But final** : qu'une personne qui ne programme pas (Pépé) crée ses propres histoires à choix sur
un ordinateur Windows, avec des formulaires, aidée d'un agent IA (Kilo Code). Le YAML reste un
format interne que l'atelier et l'agent écrivent ; personne n'a à le lire.

Chaque étape doit être utilisable seule, testée, et ne jamais casser un pack existant.

## Fait

**0.1 — Éditeur de répliques.** Packs, histoires et étapes ; texte, personnage et ton d'une réplique
(seule la ligne change dans le fichier) ; écoute des voix en cache, réplique par réplique ou
enchaînées.

**0.2 — Galerie, sons, illustrations, flot.**
- Galerie des ateliers ; « Nouvel atelier » (titre, voix du narrateur) crée une aventure vide.
- Atelier ouvert : quatre onglets, Flot, Répliques, Sons, Illustrations ; page Réglages.
- **Flot** : éditeur de graphe sur grille (zoom, déplacement, ascenseurs). Couverture → étapes
  (un fichier audio chacune) → décisions (une entrée, un choix par sortie). Cliquer une sortie crée
  une étape ; sa bulle s'accroche à l'entrée d'une décision ou reste libre (fin). Choix ajoutés ou
  retirés dans le nœud ; images et voix visibles et écoutables dans les nœuds ; double-clic :
  fiche de la décision ou répliques de l'étape ; liste « à compléter avant fabrication » ; boucles
  refusées ; positions enregistrées dans `histoires/<pack>/flot.json`. Les packs « à questions »
  s'affichent en lecture seule.
- **Répliques** : ajouter, déplacer, supprimer ; insérer un bruitage ou une musique ; ambiance par
  étape.
- **Sons** : recherche et écoute de bruitages et de bandes son ; fournisseurs interchangeables
  (Freesound pour l'instant, CC0 uniquement, clé d'API dans les Réglages) ; un son ajouté est
  téléchargé dans le cache du générateur avec son crédit.
- **Illustrations** : capacités de l'ordinateur (carte graphique, mémoire, disque) ; si c'est
  raisonnable, installation guidée de ComfyUI et du modèle FLUX.1 schnell ; « commande système »
  de style dans les Réglages ; propositions à choisir. Sinon, ou en plus : dépôt d'une image (PNG,
  JPEG, WEBP, GIF, BMP, TIFF), contrôle de la taille, recadrage 4:3, réduction 320×240, aperçu en
  16 niveaux de gris et alertes de lisibilité.
- Générateur : décisions partagées (`decisions:`), mode brouillon pour les packs en construction.
- Fenêtre de bureau : `python -m contes_studio app` (pywebview).

## Prochaines étapes

**0.3 — Pour Pépé, sous Windows.**
- Paquet Windows : installeur ou dossier autonome (PyInstaller), icône, mises à jour simples
  (voir [WINDOWS.md](WINDOWS.md)).
- Tout en formulaires : voix du casting (description, ton, écoute), titre et description du pack,
  options des packs à questions ; plus aucune action qui renvoie au YAML.
- Infobulles et aide contextuelle partout ; premier lancement guidé (dossier de travail, clé
  Freesound, test de la carte graphique).
- Bouton « Fabriquer » : vérification complète, voix, mixage, archive ; progression en direct.

**0.4 — Voix.**
- File de tâches GPU partagée avec le générateur.
- « Refaire la voix » d'une réplique (nouvelle prise, comparaison, choix de la prise).
- Enregistrement au micro, normalisé au niveau des voix de synthèse.
- Question ouverte : l'ordinateur de Pépé a-t-il une carte NVIDIA d'au moins 8 Go ? Sinon, les voix
  synthétiques ne pourront pas être faites chez lui : micro, voix faites sur un autre ordinateur,
  ou service en ligne (à étudier, avec ses conditions).

**0.5 — Agent IA (Kilo Code).**
- Chaque atelier a son `AGENTS.md` (chargé automatiquement par Kilo Code) : règles d'écriture
  (BRIEF), format du pack, univers et personnages, consignes propres à l'histoire.
- Page « Directives » dans l'atelier pour le rédiger en formulaire.
- L'atelier surveille le fichier : ce que l'agent écrit apparaît aussitôt dans le Flot et les
  Répliques, avec la liste « à compléter ».
- Un atelier = un dossier ouvrable dans VS Code + Kilo Code (`histoires/<pack>/` : pack, images,
  positions, AGENTS.md).

**0.6 — Conteuse sans Java.** Lecture du `.md` (v2, v3), conversion archive → format de
l'appareil, chiffrement v3, transfert ; tests octet par octet contre STUdio 0.4.2, puis sur une
copie du dossier de l'appareil, puis sur l'appareil après sauvegarde. Réutiliser Lunii.QT
(GPL-3.0) autant que possible.

## Questions ouvertes

- Publier le générateur (`contes-gen`) ou en intégrer ici les parties utiles : l'atelier en dépend.
- Renommer le paquet `lunii_gen` avant toute publication (RULES.md §2).
- Packs « à questions » : les convertir en aventures pour les éditer dans le Flot ?
