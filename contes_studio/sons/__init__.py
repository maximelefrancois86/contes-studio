# SPDX-License-Identifier: GPL-3.0-or-later
"""Fournisseurs de sons (bruitages, bandes son). Pour en ajouter un : une classe qui hérite de
`Fournisseur` (base.py), puis une ligne dans FOURNISSEURS."""
from .base import Fournisseur, Page, ResultatSon, TYPES
from .freesound import Freesound

FOURNISSEURS: dict[str, Fournisseur] = {f.id: f for f in (Freesound(),)}

__all__ = ["FOURNISSEURS", "Fournisseur", "Page", "ResultatSon", "TYPES"]
