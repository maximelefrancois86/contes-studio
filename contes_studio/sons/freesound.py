# SPDX-License-Identifier: GPL-3.0-or-later
"""Freesound (freesound.org) : sons sous licence CC0 uniquement (RULES.md §6), avec une clé d'API
personnelle (https://freesound.org/apiv2/apply)."""
from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request

from .base import Fournisseur, Page, Reglage, ResultatSon

API = "https://freesound.org/apiv2"
CC0 = 'license:"Creative Commons 0"'
CHAMPS = "id,name,username,duration,license,previews,url,tags"
DUREES = {"bruitage": "[0.2 TO 15]", "bande-son": "[15 TO 900]"}
PAR_PAGE = 15


class Freesound(Fournisseur):
    id = "freesound"
    nom = "Freesound"
    site = "https://freesound.org"
    licences = "CC0 (domaine public) uniquement"
    reglages = (Reglage("cle", "Clé d'API Freesound",
                        "Crée une clé gratuite sur https://freesound.org/apiv2/apply (champ « Client secret/Api key »).",
                        secret=True),)

    def _get(self, reglages, route: str, params: dict) -> dict:
        cle = self.config(reglages).get("cle")
        if not cle:
            raise PermissionError(self.pret(reglages)[1])
        url = f"{API}{route}?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Authorization": f"Token {cle}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise PermissionError("clé d'API refusée par Freesound") from e
            raise RuntimeError(f"Freesound a répondu {e.code}") from e

    @staticmethod
    def _resultat(s: dict) -> ResultatSon:
        return ResultatSon(
            fournisseur="freesound", id=str(s["id"]), titre=s.get("name", ""), auteur=s.get("username", ""),
            duree=round(float(s.get("duration", 0)), 1), licence="CC0",
            licence_url=s.get("license", "http://creativecommons.org/publicdomain/zero/1.0/"),
            apercu=(s.get("previews") or {}).get("preview-hq-mp3", ""), page=s.get("url", ""),
            etiquettes=list(s.get("tags") or [])[:8])

    def chercher(self, reglages, requete: str, type_son: str, page: int = 1) -> Page:
        dur = DUREES.get(type_son, DUREES["bruitage"])
        d = self._get(reglages, "/search/text/", {
            "query": requete, "filter": f"{CC0} duration:{dur}", "sort": "score",
            "fields": CHAMPS, "page_size": PAR_PAGE, "page": max(1, page)})
        res = [self._resultat(s) for s in d.get("results", [])]
        total = int(d.get("count", len(res)))
        return Page(res, total, page, max(1, math.ceil(total / PAR_PAGE)))

    def detail(self, reglages, son_id: str) -> ResultatSon:
        s = self._get(reglages, f"/sounds/{int(son_id)}/", {"fields": CHAMPS})
        if "Creative Commons 0" not in s.get("license", "") and "zero" not in s.get("license", ""):
            raise PermissionError("ce son n'est pas sous licence CC0 : refusé (RULES.md)")
        return self._resultat(s)

    def spec(self, son: ResultatSon, usage: str) -> dict:
        # format du générateur : un id numérique désigne ce son précis
        s: dict = {"freesound": int(son.id)}
        if usage == "ambiance":
            s["boucle"] = True
        else:
            s["duree_max"] = float(min(max(son.duree, 1.0), 90.0 if usage == "musique" else 15.0))
        return s
