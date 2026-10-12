# SPDX-License-Identifier: GPL-3.0-or-later
"""Interface commune des fournisseurs de sons."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field

# bruitage : son court, inséré entre deux répliques ({bruit: id})
# bande-son : musique ou ambiance longue ({musique: id}, ou `ambiance: id` en boucle sous une histoire)
TYPES = ("bruitage", "bande-son")


@dataclass
class ResultatSon:
    fournisseur: str
    id: str
    titre: str
    auteur: str
    duree: float
    licence: str
    licence_url: str
    apercu: str            # URL d'un MP3 écoutable directement par le navigateur
    page: str              # page du son chez le fournisseur (crédit)
    etiquettes: list[str] = field(default_factory=list)

    def public(self) -> dict:
        return asdict(self)


@dataclass
class Page:
    resultats: list[ResultatSon]
    total: int
    page: int
    pages: int


@dataclass
class Reglage:
    """Réglage dont le fournisseur a besoin (affiché dans la page Réglages)."""
    cle: str
    libelle: str
    aide: str
    secret: bool = False


class Fournisseur(ABC):
    id: str
    nom: str
    site: str
    licences: str  # licences proposées, en clair (ex. « CC0 uniquement »)
    reglages: tuple[Reglage, ...] = ()

    def config(self, reglages) -> dict:
        return reglages.get("sons", self.id, defaut={}) or {}

    def pret(self, reglages) -> tuple[bool, str]:
        """(utilisable, message pour l'utilisateur)."""
        for r in self.reglages:
            if not self.config(reglages).get(r.cle):
                return False, f"Renseigne « {r.libelle} » dans les Réglages pour chercher sur {self.nom}."
        return True, ""

    @abstractmethod
    def chercher(self, reglages, requete: str, type_son: str, page: int = 1) -> Page: ...

    @abstractmethod
    def detail(self, reglages, son_id: str) -> ResultatSon: ...

    @abstractmethod
    def spec(self, son: ResultatSon, usage: str) -> dict:
        """Entrée du catalogue `sons:` du YAML pour ce son (lue par le générateur)."""

    def tester(self, reglages) -> tuple[bool, str]:
        ok, msg = self.pret(reglages)
        if not ok:
            return ok, msg
        try:
            self.chercher(reglages, "door", "bruitage")
            return True, f"Connexion à {self.nom} réussie."
        except Exception as e:  # noqa: BLE001
            return False, f"{self.nom} refuse la connexion : {e}"

    def public(self, reglages) -> dict:
        ok, msg = self.pret(reglages)
        return {"id": self.id, "nom": self.nom, "site": self.site, "licences": self.licences,
                "pret": ok, "message": msg,
                "reglages": [{"cle": r.cle, "libelle": r.libelle, "aide": r.aide, "secret": r.secret}
                             for r in self.reglages]}
