# SPDX-License-Identifier: GPL-3.0-or-later
"""Serveur de l'atelier : API JSON + interface web (fichiers de static/), en local uniquement."""
from __future__ import annotations

import io
import os
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .images import capacites, comfy, traitement
from .reglages import Reglages
from .sons import FOURNISSEURS, TYPES
from .taches import Taches, verrou_gpu
from .voix import CacheVoix
from .workspace import EditError, Workspace

STATIC = Path(__file__).with_name("static")
_ENV_LOCK = threading.Lock()


class LineEdit(BaseModel):
    section: str
    i: int
    j: int
    texte: str | None = None
    qui: str | None = None
    ton: str | None = None


class AjoutSon(BaseModel):
    fournisseur: str
    son: str
    usage: str = "bruit"            # bruit | musique | ambiance
    nom: str | None = None


class InsertionSon(BaseModel):
    section: str
    i: int
    apres: int
    genre: str                      # bruit | musique
    son: str


class Ambiance(BaseModel):
    section: str
    i: int
    son: str | None = None


class Texte(BaseModel):
    texte: str | None = None


class Cadre(BaseModel):
    jeton: str
    cadre: dict | None = None


class NouvelAtelier(BaseModel):
    titre: str
    narrateur: str = "conteur"


class OpLigne(BaseModel):
    section: str
    i: int
    j: int = -1
    qui: str | None = None
    texte: str = ""
    ton: str | None = None
    sens: int = 0


class CibleVoix(BaseModel):
    section: str
    i: int
    j: int
    prise: int = 0


class FaireVoix(BaseModel):
    cibles: list[list] | None = None
    qui: str | None = None
    tout: bool = False


class Proposer(BaseModel):
    n: int | None = None
    description: str | None = None


def _png(img) -> Response:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    # l'adresse porte une version (?v=…) qui change quand l'image change : le navigateur peut la garder
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


def ffmpeg_exe() -> str:
    import shutil

    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as e:
        raise RuntimeError("ffmpeg introuvable (installer imageio-ffmpeg)") from e


def create_app(root: Path, reglages: Reglages | None = None) -> FastAPI:
    ws = Workspace(root)
    voix = CacheVoix(root / ".cache" / "tts")
    reg = reglages or Reglages()
    taches = Taches()
    brouillons = traitement.Brouillons(root / ".cache" / "studio" / "brouillons")
    brouillons.menage()
    app = FastAPI(title="Atelier d'histoires", version=__version__)

    def erreur(e: Exception, code: int = 400):
        raise HTTPException(code, str(e)) from e

    # -- général ---------------------------------------------------------------
    @app.get("/api/infos")
    def infos():
        return {"version": __version__, "espace": str(root)}

    @app.get("/api/reglages")
    def lire_reglages():
        return reg.public()

    @app.put("/api/reglages")
    def ecrire_reglages(changes: dict):
        return reg.maj(changes)

    @app.get("/api/taches/{tid}")
    def tache(tid: str):
        t = taches.get(tid)
        if not t:
            raise HTTPException(404, "Tâche inconnue")
        return t.public()

    @app.post("/api/taches/{tid}/annuler")
    def annuler(tid: str):
        t = taches.get(tid)
        if t:
            t.annuler.set()
        return {"ok": True}

    # -- packs et répliques ----------------------------------------------------
    @app.get("/api/packs")
    def packs():
        return ws.packs()

    @app.get("/api/packs/{pid}")
    def pack(pid: str):
        try:
            return ws.pack(pid, voix.path)
        except EditError as e:
            erreur(e, 404)
        except Exception as e:  # noqa: BLE001  (YAML en cours d'écriture)
            erreur(Exception(f"Pack illisible : {e}"), 422)

    @app.post("/api/packs")
    def creer(a: NouvelAtelier):
        try:
            return {"id": ws.creer_pack(a.titre, a.narrateur)}
        except EditError as e:
            erreur(e)

    @app.get("/api/catalogue-voix")
    def catalogue_voix():
        from lunii_gen import voices

        return [{"nom": n, "description": voices.get(n, n).description} for n in voices.names()]

    @app.get("/api/packs/{pid}/graphe")
    def graphe(pid: str):
        try:
            return ws.graphe(pid, voix.path)
        except EditError as e:
            erreur(e, 404)

    @app.post("/api/packs/{pid}/graphe")
    def graphe_op(pid: str, op: dict):
        try:
            r = ws.graphe_op(pid, op)
        except (EditError, KeyError) as e:
            erreur(e)
        return {**r, "graphe": ws.graphe(pid, voix.path)}

    @app.post("/api/packs/{pid}/convertir")
    def convertir(pid: str):
        try:
            return ws.convertir_en_aventure(pid)
        except EditError as e:
            erreur(e)

    @app.put("/api/packs/{pid}/graphe/positions")
    def positions(pid: str, pos: dict):
        try:
            ws.ecrire_positions(pid, pos)
        except EditError as e:
            erreur(e)
        return {"ok": True}

    @app.post("/api/packs/{pid}/lignes/{action}")
    def lignes(pid: str, action: str, o: OpLigne):
        try:
            if action == "ajouter":
                return {"j": ws.ajouter_replique(pid, o.section, o.i, o.j, o.qui, o.texte, o.ton)}
            if action == "supprimer":
                ws.supprimer_ligne(pid, o.section, o.i, o.j)
                return {"j": max(0, o.j - 1)}
            if action == "deplacer":
                return {"j": ws.deplacer_ligne(pid, o.section, o.i, o.j, o.sens)}
        except (EditError, IndexError, KeyError) as e:
            erreur(e)
        raise HTTPException(404, "Action inconnue")

    @app.get("/api/packs/{pid}/flot")
    def flot(pid: str):
        try:
            return ws.flot(pid)
        except EditError as e:
            erreur(e, 404)

    @app.post("/api/packs/{pid}/ligne")
    def edit(pid: str, e: LineEdit):
        try:
            ws.edit_line(pid, e.section, e.i, e.j, texte=e.texte, qui=e.qui, ton=e.ton)
        except EditError as err:
            erreur(err)
        data = ws.pack(pid, voix.path)
        sec = next(s for s in data["sections"] if s["section"] == e.section and s["i"] == e.i)
        return next(l for l in sec["lignes"] if l["j"] == e.j)

    @app.get("/api/voix/{name}")
    def audio(name: str):
        p = voix.dir / name
        if "/" in name or "\\" in name or not name.endswith(".wav") or not p.is_file():
            raise HTTPException(404, "Voix absente du cache")
        return FileResponse(p, media_type="audio/wav")

    # -- sons ------------------------------------------------------------------
    @app.get("/api/sons/fournisseurs")
    def fournisseurs():
        return {"types": TYPES, "fournisseurs": [f.public(reg) for f in FOURNISSEURS.values()]}

    def _fournisseur(fid: str):
        f = FOURNISSEURS.get(fid)
        if not f:
            raise HTTPException(404, f"Fournisseur inconnu : {fid}")
        return f

    @app.post("/api/sons/fournisseurs/{fid}/tester")
    def tester(fid: str):
        ok, msg = _fournisseur(fid).tester(reg)
        return {"ok": ok, "message": msg}

    @app.get("/api/sons/recherche")
    def recherche(fournisseur: str, q: str, type: str = "bruitage", page: int = 1):
        f = _fournisseur(fournisseur)
        if type not in TYPES:
            raise HTTPException(400, f"Type inconnu : {type}")
        if not q.strip():
            return {"resultats": [], "total": 0, "page": 1, "pages": 1}
        try:
            p = f.chercher(reg, q.strip(), type, page)
        except PermissionError as e:
            erreur(e, 403)
        except Exception as e:  # noqa: BLE001
            erreur(Exception(f"{f.nom} ne répond pas : {e}"), 502)
        return {"resultats": [r.public() for r in p.resultats], "total": p.total, "page": p.page, "pages": p.pages}

    @app.get("/api/packs/{pid}/sons")
    def sons(pid: str):
        try:
            return ws.sons(pid)
        except EditError as e:
            erreur(e, 404)

    @app.get("/api/packs/{pid}/sons/{sid}/audio")
    def son_audio(pid: str, sid: str):
        p = ws.chemin_son(pid, sid)
        if not p:
            raise HTTPException(404, "Son pas encore téléchargé")
        return FileResponse(p, media_type="audio/wav")

    @app.post("/api/packs/{pid}/sons")
    def ajouter_son(pid: str, a: AjoutSon):
        f = _fournisseur(a.fournisseur)
        if a.usage not in ("bruit", "musique", "ambiance"):
            raise HTTPException(400, "Usage inconnu")
        try:
            son = f.detail(reg, a.son)
            spec = f.spec(son, a.usage)
            sid = ws.ajouter_son(pid, a.nom or son.titre.rsplit(".", 1)[0], spec)
        except (EditError, PermissionError) as e:
            erreur(e)
        # téléchargement dans le cache du générateur (crédit compris) : le build n'aura plus besoin de la clé
        from lunii_gen.sons import Sonotheque

        try:
            with _ENV_LOCK:
                old = os.environ.get("FREESOUND_TOKEN")
                os.environ["FREESOUND_TOKEN"] = f.config(reg).get("cle", "")
                try:
                    Sonotheque(root / ".cache" / "sons").get(sid, spec)
                finally:
                    if old is None:
                        os.environ.pop("FREESOUND_TOKEN", None)
                    else:
                        os.environ["FREESOUND_TOKEN"] = old
        except Exception as e:  # noqa: BLE001
            return {"id": sid, "telecharge": False, "message": f"Ajouté, mais pas encore téléchargé : {e}"}
        return {"id": sid, "telecharge": True}

    @app.post("/api/packs/{pid}/sons/inserer")
    def inserer_son(pid: str, x: InsertionSon):
        try:
            ws.inserer_son(pid, x.section, x.i, x.apres, x.genre, x.son)
        except EditError as e:
            erreur(e)
        return {"ok": True}

    @app.post("/api/packs/{pid}/ambiance")
    def ambiance(pid: str, a: Ambiance):
        try:
            ws.definir_ambiance(pid, a.section, a.i, a.son)
        except EditError as e:
            erreur(e)
        return {"ok": True}

    # -- illustrations : emplacements --------------------------------------------
    def _image_actuelle(pid: str, e: dict):
        """(image couleur, origine) : fichier choisi, illustration déjà générée par le build, ou carte-titre."""
        from PIL import Image

        if e["image"]:
            p = ws.stories_dir / e["image"]
            if p.exists():
                return Image.open(p).convert("RGB"), "fichier"
        if e["description"]:
            import hashlib

            from lunii_gen import illustrate as il

            key = hashlib.sha1(f"{il.MODEL}|{il.STYLE}|{e['graine']}|{e['description']}".encode()).hexdigest()
            p = root / ".cache" / "img" / f"{key}.png"
            if p.exists():
                return Image.open(p).convert("RGB"), "generee"
        from lunii_gen.images import title_card

        return title_card(e["titre_carte"]), "carte"

    @app.get("/api/packs/{pid}/illustrations")
    def illustrations(pid: str):
        try:
            out = ws.emplacements(pid)
        except EditError as e:
            erreur(e, 404)
        for e in out:
            e["origine"] = _image_actuelle(pid, e)[1]
        return out

    @app.get("/api/packs/{pid}/illustrations/{slot}/image")
    def image_slot(pid: str, slot: str, gris: bool = False, v: str | None = None):
        try:
            img, _ = _image_actuelle(pid, ws.emplacement(pid, slot))
        except EditError as e:
            erreur(e, 404)
        img = traitement.recadrer(img, None) if img.size != traitement.TAILLE else img
        return _png(traitement.en_gris(img) if gris else img)

    @app.post("/api/packs/{pid}/illustrations/{slot}/description")
    def description(pid: str, slot: str, x: Texte):
        try:
            ws.definir_description(pid, slot, x.texte)
        except EditError as e:
            erreur(e)
        return ws.emplacement(pid, slot)

    @app.post("/api/packs/{pid}/illustrations/{slot}/image")
    def choisir_image(pid: str, slot: str, c: Cadre):
        try:
            img = traitement.recadrer(brouillons.ouvrir(c.jeton), c.cadre)
            d = ws.dossier_images(pid)
            d.mkdir(parents=True, exist_ok=True)
            img.save(d / f"{slot}.png")
            ws.definir_image(pid, slot, f"{pid}/images/{slot}.png")
        except (EditError, traitement.ImageRefusee) as e:
            erreur(e)
        return ws.emplacement(pid, slot)

    @app.delete("/api/packs/{pid}/illustrations/{slot}/image")
    def retirer_image(pid: str, slot: str):
        try:
            ws.definir_image(pid, slot, None)
        except EditError as e:
            erreur(e)
        return ws.emplacement(pid, slot)

    # -- illustrations : brouillons (dépôt, recadrage, aperçu) ---------------------
    @app.post("/api/images/deposer")
    async def deposer(fichier: UploadFile = File(...)):
        data = await fichier.read(traitement.POIDS_MAX + 1)
        try:
            img = traitement.lire(data)
        except traitement.ImageRefusee as e:
            erreur(e)
        return {"jeton": brouillons.ajouter(img), **traitement.analyse(img)}

    @app.get("/api/images/brouillons/{jeton}")
    def brouillon(jeton: str):
        try:
            return FileResponse(brouillons.chemin(jeton), media_type="image/png")
        except traitement.ImageRefusee as e:
            erreur(e, 404)

    @app.post("/api/images/apercu")
    def apercu(c: Cadre, gris: bool = False):
        try:
            img = traitement.recadrer(brouillons.ouvrir(c.jeton), c.cadre)
        except traitement.ImageRefusee as e:
            erreur(e)
        return _png(traitement.en_gris(img) if gris else img)

    @app.post("/api/images/controle")
    def controle(c: Cadre):
        try:
            img = traitement.recadrer(brouillons.ouvrir(c.jeton), c.cadre)
        except traitement.ImageRefusee as e:
            erreur(e)
        return {"avertissements": traitement.lisibilite(img)}

    # -- illustrations : ComfyUI ---------------------------------------------------
    def _comfy() -> comfy.Comfy:
        return comfy.Comfy(reg.get("illustrations", "comfyui", defaut={}))

    @app.get("/api/illustrations/etat")
    def etat_illustrations():
        c = _comfy()
        cap = capacites.rapport(c.url, str(c.python), str(c.dossier))
        e = c.etat()
        plan = [] if e["installe"] else comfy.etapes_installation(c.dossier, cap, c.modele)
        return {"capacites": cap, "comfyui": e,
                "plan": [{"titre": p["titre"], "erreur": p.get("erreur")} for p in plan]}

    @app.post("/api/illustrations/comfyui/demarrer")
    def demarrer_comfy():
        c = _comfy()
        return taches.lancer("Démarrage de ComfyUI", lambda t: c.demarrer(t)).public()

    @app.post("/api/illustrations/comfyui/installer")
    def installer_comfy():
        c = _comfy()
        cap = capacites.rapport(c.url, str(c.python), str(c.dossier))
        if cap["verdict"] == "deconseille":
            raise HTTPException(400, "Cet ordinateur n'est pas assez puissant : dépose plutôt tes images.")

        def run(t):
            res = comfy.installer(c.dossier, cap, c.modele, t)
            reg.maj({"illustrations": {"comfyui": {"dossier": res["dossier"], "python": res["python"]}}})
            return res

        return taches.lancer("Installation de ComfyUI", run).public()

    @app.post("/api/packs/{pid}/illustrations/{slot}/proposer")
    def proposer(pid: str, slot: str, p: Proposer):
        try:
            e = ws.emplacement(pid, slot)
        except EditError as err:
            erreur(err, 404)
        desc = (p.description or e["description"] or e["libelle"]).strip()
        n = max(1, min(8, p.n or int(reg.get("illustrations", "propositions", defaut=4))))
        style = reg.get("illustrations", "style", defaut="")
        negatif = reg.get("illustrations", "negatif", defaut="")

        def run(t):
            for m in moteurs.values():  # le moteur de voix garde la carte graphique : on l'arrête
                m.arreter()
            c = _comfy()
            if not c.connecte():
                t.log("Démarrage de ComfyUI…")
                c.demarrer(t)
            with verrou_gpu(t):
                t.log(f"Génération de {n} proposition(s) : {desc}")
                imgs = c.generer(desc, style, negatif, n, t)
                c.liberer()
            return [{"jeton": brouillons.ajouter(im), **traitement.analyse(im)} for im in imgs]

        return taches.lancer(f"Propositions pour « {e['libelle']} »", run).public()

    # -- voix ------------------------------------------------------------------------
    from . import voix_moteur as vm

    moteurs: dict[str, vm.MoteurVoix] = {}

    def moteur() -> vm.MoteurVoix:
        py = reg.get("voix", "python", defaut="") or ""
        if py not in moteurs:
            for m in moteurs.values():
                m.arreter()
            moteurs.clear()
            moteurs[py] = vm.MoteurVoix(py)
        return moteurs[py]

    @app.get("/api/moteur-voix/etat")
    def etat_voix():
        c = _comfy()
        cap = capacites.rapport(c.url, str(c.python), reg.get("voix", "dossier"))
        verdict, raisons = vm.verdict_voix(cap)
        m = moteur()
        ok, msg = m.installe()
        mods = vm.modeles_presents()
        from lunii_gen.paths import GEN

        plan = [] if ok else vm.etapes_installation(Path(reg.get("voix", "dossier")), cap, GEN)
        return {"capacites": cap, "verdict": verdict, "raisons": raisons, "installe": ok, "message": msg,
                "modeles": mods, "pret": ok and all(mods.values()), "en_marche": m.en_marche(),
                "python": reg.get("voix", "python"), "plan": [{"titre": e["titre"], "erreur": e.get("erreur")} for e in plan]}

    @app.post("/api/moteur-voix/installer")
    def installer_voix():
        from lunii_gen.paths import GEN

        c = _comfy()
        cap = capacites.rapport(c.url, str(c.python), reg.get("voix", "dossier"))
        if vm.verdict_voix(cap)[0] == "deconseille":
            raise HTTPException(400, "Cet ordinateur n'est pas assez puissant pour les voix : enregistre-les au micro.")

        def run(t):
            res = vm.installer(Path(reg.get("voix", "dossier")), cap, GEN, t)
            reg.maj({"voix": {"python": res["python"]}})
            return res

        return taches.lancer("Installation des voix", run).public()

    @app.post("/api/moteur-voix/arreter")
    def arreter_voix():
        moteur().arreter()
        return {"ok": True}

    def _lancer_voix(pid: str, demande: dict, titre: str):
        import uuid as _uuid

        demande = {"id": _uuid.uuid4().hex[:10], "espace": str(root), "pack": pid, **demande}
        return taches.lancer(titre, lambda t: moteur().faire(demande, t)).public()

    @app.post("/api/packs/{pid}/voix/faire")
    def faire_voix(pid: str, f: FaireVoix):
        ws.pack_path(pid)
        titre = "Voix de " + (f.qui or "toutes les répliques") if not f.cibles else f"{len(f.cibles)} voix"
        return _lancer_voix(pid, {"cibles": f.cibles, "qui": f.qui, "tout": f.tout}, titre)

    def _ligne(pid: str, c: CibleVoix) -> dict:
        data = ws.pack(pid, voix.path)
        sec = next((x for x in data["sections"] if x["section"] == c.section and x["i"] == c.i), None)
        lg = next((l for l in (sec or {}).get("lignes", []) if l["j"] == c.j), None)
        if not lg or lg["kind"] != "replique":
            raise HTTPException(404, "Réplique introuvable")
        return lg

    @app.post("/api/packs/{pid}/voix/refaire")
    def refaire_voix(pid: str, c: CibleVoix):
        """Nouvelle prise : la réplique passe à la prise suivante, puis elle est synthétisée."""
        lg = _ligne(pid, c)
        nouvelle = max([lg.get("prise") or 0] + (lg.get("prises") or [])) + 1
        try:
            ws.champs_ligne(pid, c.section, c.i, c.j, prise=nouvelle)
        except EditError as e:
            erreur(e)
        return _lancer_voix(pid, {"cibles": [[c.section, c.i, c.j]]}, f"Nouvelle prise ({nouvelle + 1})")

    @app.post("/api/packs/{pid}/voix/prise")
    def choisir_prise(pid: str, c: CibleVoix):
        try:
            ws.champs_ligne(pid, c.section, c.i, c.j, prise=max(0, c.prise))
        except EditError as e:
            erreur(e)
        return _ligne(pid, c)

    @app.post("/api/packs/{pid}/voix/enregistrement")
    async def enregistrer(pid: str, section: str = Form(...), i: int = Form(...), j: int = Form(...),
                          fichier: UploadFile = File(...)):
        """Voix enregistrée au micro ou fichier déposé (MP3, WAV, OGG, M4A, WEBM…), convertie en WAV mono."""
        import subprocess
        import tempfile
        import uuid as _uuid

        lg = _ligne(pid, CibleVoix(section=section, i=i, j=j))
        data = await fichier.read(40 * 1024 * 1024 + 1)
        if len(data) > 40 * 1024 * 1024:
            raise HTTPException(400, "Fichier trop lourd (40 Mo au plus)")
        d = ws.stories_dir / pid / "voix"
        d.mkdir(parents=True, exist_ok=True)
        nom = f"{lg['qui']}-{section[0]}{i}-{j}-{_uuid.uuid4().hex[:6]}.wav"
        with tempfile.NamedTemporaryFile(suffix=Path(fichier.filename or "x").suffix or ".bin", delete=False) as tmp:
            tmp.write(data)
        try:
            r = subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-i", tmp.name, "-t", "300", "-ac", "1", "-ar", "24000",
                                "-c:a", "pcm_s16le", str(d / nom)], capture_output=True, text=True, timeout=120)
        finally:
            Path(tmp.name).unlink(missing_ok=True)
        if r.returncode != 0 or not (d / nom).exists() or (d / nom).stat().st_size < 2000:
            (d / nom).unlink(missing_ok=True)
            raise HTTPException(400, "Ce fichier ne contient pas de son lisible")
        ancien = lg.get("enregistrement")
        try:
            ws.champs_ligne(pid, section, i, j, audio=f"{pid}/voix/{nom}")
        except EditError as e:
            (d / nom).unlink(missing_ok=True)
            erreur(e)
        if ancien and (ws.stories_dir / ancien).exists():
            (ws.stories_dir / ancien).unlink()
        return _ligne(pid, CibleVoix(section=section, i=i, j=j))

    @app.post("/api/packs/{pid}/voix/enregistrement/retirer")
    def retirer_enregistrement(pid: str, c: CibleVoix):
        lg = _ligne(pid, c)
        try:
            ws.champs_ligne(pid, c.section, c.i, c.j, audio=None)
        except EditError as e:
            erreur(e)
        if lg.get("enregistrement") and (ws.stories_dir / lg["enregistrement"]).exists():
            (ws.stories_dir / lg["enregistrement"]).unlink()
        return _ligne(pid, c)

    @app.get("/api/packs/{pid}/voix/fichier/{nom}")
    def fichier_voix(pid: str, nom: str):
        p = ws.stories_dir / pid / "voix" / nom
        if "/" in nom or "\\" in nom or not p.is_file():
            raise HTTPException(404, "Enregistrement introuvable")
        return FileResponse(p, media_type="audio/wav")

    # -- interface -----------------------------------------------------------------
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app
