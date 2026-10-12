# contes-studio

Atelier pour fabriquer des histoires audio à choix pour les enfants : écrire les répliques, choisir
les voix et les tons, écouter, trouver des bruitages, générer illustrations et fonds sonores, puis
transférer le pack sur une conteuse.

C'est une réécriture en Python de [STUdio](https://github.com/marian-m12l/studio), l'éditeur de
packs libre de marian-m12l, pensée pour un travail à deux mains avec un agent IA : les histoires
sont des fichiers YAML lisibles, et l'agent suit des directives écrites dans le dépôt.

> Projet indépendant, non affilié à Lunii SAS. Compatible avec les conteuses « Ma Fabrique à
> Histoires® » de Lunii®, qui sont des marques de Lunii SAS. Le transfert vers un appareil repose
> sur des formats documentés par rétro-ingénierie, à des fins d'interopérabilité : utilisation à vos
> risques, faites une sauvegarde de votre conteuse.

## État

Version 0.3, en construction. Le but : qu'une personne qui ne programme pas crée ses histoires
sur Windows, avec des formulaires, aidée d'un agent IA (Kilo Code).

| Fonction | État |
|---|---|
| Galerie des ateliers, création d'un nouvel atelier (aventure) | ✅ |
| **Flot** : graphe sur grille (zoom, déplacement), couverture → étapes → décisions, bulles à accrocher, images et voix dans les nœuds | ✅ |
| **Répliques** : écrire, ajouter, déplacer, supprimer ; bruitages, musiques, ambiances ; écoute | ✅ |
| **Sons** : recherche et écoute (Freesound, CC0 ; autres fournisseurs possibles), ajout avec crédit | ✅ |
| **Illustrations** : ComfyUI (installation guidée si l'ordinateur le permet) ou dépôt d'image, recadrage 4:3, aperçu en gris, alertes de lisibilité | ✅ |
| Fenêtre de bureau (pywebview) | ✅ (non testée sous Windows) |
| Paquet Windows, premier lancement guidé | prévu |
| **Voix**, personnage par personnage : faire, refaire (prises), enregistrer au micro ou déposer un fichier ; installation guidée de Qwen3-TTS si l'ordinateur le permet | ✅ |
| Boucles dans le flot (labyrinthe, histoire sans fin) | ✅ |
| Bouton « Fabriquer » | prévu |
| Directives pour l'agent IA (`AGENTS.md` par atelier) | prévu |
| Transfert sur la conteuse sans Java | prévu |

Détails : [docs/FEUILLE-DE-ROUTE.md](docs/FEUILLE-DE-ROUTE.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/WINDOWS.md](docs/WINDOWS.md).

## Lancer

L'atelier s'appuie pour l'instant sur le générateur `lunii_gen` (dépôt `contes-gen`, privé pour le
moment) et lit un espace de travail qui contient `histoires/*.yaml` et `.cache/`.

```bash
uv venv --python 3.12 ~/.venvs/studio
uv pip install --python ~/.venvs/studio/bin/python -e ".[bureau,dev]" -e ../gen
./atelier.sh                                           # le plus simple (atelier.bat sous Windows)
~/.venvs/studio/bin/python -m contes_studio app        # fenêtre de bureau (pywebview)
~/.venvs/studio/bin/python -m contes_studio serve      # ou dans un navigateur : http://127.0.0.1:8090
~/.venvs/studio/bin/python -m pytest -q tests          # tests
```

## Licence et crédits

- Code sous licence **GPL-3.0-or-later** (voir `LICENSE`).
- STUdio, © marian-m12l et contributeurs, MPL 2.0 : référence pour les formats de pack et le
  fonctionnement de l'éditeur. Le code repris ou traduit de STUdio garde sa licence MPL 2.0 et ses
  mentions d'origine. La MPL 2.0 permet de l'inclure dans un ensemble sous GPL.
- [Lunii.QT](https://github.com/o-daneel/Lunii.QT), © o-daneel, GPL-3.0 : référence pour la gestion
  des conteuses en Python. Le choix de la GPL permet de réutiliser son code.
- Aucune clé, aucun micrologiciel ni aucun contenu de Lunii SAS n'est distribué ici. Les clés propres
  à chaque conteuse v3 sont lues sur l'appareil de l'utilisateur au moment du transfert.
