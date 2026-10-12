# SPDX-License-Identifier: GPL-3.0-or-later
"""Images déposées ou générées : contrôle, recadrage 4:3, réduction en 320×240, aperçu en gris.

L'écran de la conteuse fait 320×240 et n'affiche que 16 niveaux de gris : on montre l'image telle
qu'elle y apparaîtra et on prévient si elle risque d'être illisible.
"""
from __future__ import annotations

import io
import re
import uuid
from pathlib import Path

from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError

TAILLE = (320, 240)
RATIO = TAILLE[0] / TAILLE[1]
FORMATS = {"PNG", "JPEG", "WEBP", "GIF", "BMP", "TIFF"}
POIDS_MAX = 25 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 60_000_000
_JETON = re.compile(r"^[0-9a-f]{32}$")


class ImageRefusee(ValueError):
    pass


class Brouillons:
    """Images en cours de préparation (déposées ou proposées par ComfyUI), repérées par un jeton."""

    def __init__(self, dossier: Path):
        self.dossier = dossier
        dossier.mkdir(parents=True, exist_ok=True)

    def chemin(self, jeton: str, suffixe: str = "") -> Path:
        if not _JETON.match(jeton):
            raise ImageRefusee("jeton invalide")
        return self.dossier / f"{jeton}{suffixe}.png"

    def ajouter(self, img: Image.Image) -> str:
        jeton = uuid.uuid4().hex
        img.save(self.chemin(jeton))
        return jeton

    def ouvrir(self, jeton: str) -> Image.Image:
        p = self.chemin(jeton)
        if not p.exists():
            raise ImageRefusee("image expirée : recharge-la")
        return Image.open(p).convert("RGB")

    def menage(self, age_s: float = 86400) -> None:
        import time

        for p in self.dossier.glob("*.png"):
            if time.time() - p.stat().st_mtime > age_s:
                p.unlink(missing_ok=True)


def lire(data: bytes) -> Image.Image:
    if len(data) > POIDS_MAX:
        raise ImageRefusee(f"fichier trop lourd ({len(data) // 1_000_000} Mo, 25 Mo au plus)")
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        img.load()
    except (UnidentifiedImageError, OSError) as e:
        raise ImageRefusee("format d'image non reconnu (PNG, JPEG, WEBP, GIF, BMP ou TIFF)") from e
    except Image.DecompressionBombError as e:
        raise ImageRefusee("image beaucoup trop grande") from e
    if fmt not in FORMATS:
        raise ImageRefusee(f"format {fmt} non pris en charge (PNG, JPEG, WEBP, GIF, BMP ou TIFF)")
    img = ImageOps.exif_transpose(img)  # photo de téléphone tournée
    if img.mode in ("RGBA", "LA", "P"):
        fond = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        fond.paste(rgba, mask=rgba.getchannel("A"))
        img = fond
    return img.convert("RGB")


def cadre_propose(l: int, h: int) -> dict:
    """Plus grand cadre 4:3 centré."""
    if l / h > RATIO:
        cl, ch = round(h * RATIO), h
    else:
        cl, ch = l, round(l / RATIO)
    return {"x": (l - cl) // 2, "y": (h - ch) // 2, "l": cl, "h": ch}


def analyse(img: Image.Image) -> dict:
    l, h = img.size
    av = []
    if l < TAILLE[0] or h < TAILLE[1]:
        av.append(f"Image petite ({l}×{h}) : elle sera agrandie et paraîtra floue. 320×240 au moins.")
    ecart = abs(l / h - RATIO) / RATIO
    return {"largeur": l, "hauteur": h, "recadrage": ecart > 0.01, "cadre": cadre_propose(l, h),
            "avertissements": av}


def recadrer(img: Image.Image, cadre: dict | None) -> Image.Image:
    l, h = img.size
    c = cadre or cadre_propose(l, h)
    x, y = max(0, int(c["x"])), max(0, int(c["y"]))
    cl, ch = max(1, int(c["l"])), max(1, int(c["h"]))
    cl, ch = min(cl, l - x), min(ch, h - y)
    if abs(cl / ch - RATIO) / RATIO > 0.02:  # cadre déformé : on rétablit le 4:3 autour de son centre
        cx, cy = x + cl / 2, y + ch / 2
        if cl / ch > RATIO:
            cl = round(ch * RATIO)
        else:
            ch = round(cl / RATIO)
        x, y = int(cx - cl / 2), int(cy - ch / 2)
    return img.crop((x, y, x + cl, y + ch)).resize(TAILLE, Image.LANCZOS)


def en_gris(img: Image.Image, niveaux: int = 16) -> Image.Image:
    """Rendu de l'écran : gris, contraste étiré (2 % écrêtés), 16 niveaux (même calcul que le générateur)."""
    g = ImageOps.autocontrast(img.convert("L"), cutoff=2)
    pas = 256 // niveaux
    return g.point(lambda v: min(255, (v // pas) * pas + pas // 2)).convert("RGB")


def lisibilite(img: Image.Image) -> list[str]:
    """Avertissements sur l'image 320×240 en couleur, une fois passée en gris.

    Seuils étalonnés sur les illustrations du générateur (sujet simple sur fond uni) : la part de
    pixels nettement différents du fond y vaut au moins 6 % dans 95 % des cas, l'écart-type de
    luminosité au moins 40."""
    av = []
    gris = en_gris(img).convert("L")
    hist = gris.histogram()
    total = sum(hist)
    fond = max(range(256), key=lambda i: hist[i])
    sujet = sum(n for i, n in enumerate(hist) if abs(i - fond) > 32) / total
    ecart = ImageStat.Stat(img.convert("L")).stddev[0]
    sat = ImageStat.Stat(img.convert("HSV")).mean[1]
    if sujet < 0.05:
        av.append("Le sujet est petit ou de la même teinte que le fond : vérifie qu’il se voit bien dans l’aperçu en gris.")
    if ecart < 30:
        av.append("Peu contrastée : sur l'écran, le sujet risque de se fondre dans le fond.")
    if sat > 90 and ecart < 40:
        av.append("Couleurs vives mais de luminosité proche : elles se confondront en gris.")
    return av
