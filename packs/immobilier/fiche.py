"""La fiche PDF d'une annonce, et les photos tirées d'une plaquette PDF (repris d'Alix FSP : fiche/, photos-pdf.js).

La fiche se compose en JavaScript (pdf-lib), comme chez Alix FSP, sans rien réécrire de sa mise en page : le
service `fiche/` de l'image, appelé comme un processus (une demande JSON en entrée, le PDF en sortie). Rien ne
sort du conteneur. Le modèle de fiche du client (ses polices, son logo) se règle dans Config.gestion.fiche.

Les photos d'une plaquette : les images du PDF qui ont l'air de photos (ni petites, ni allongées, ni grises,
ni en double), en JPEG tel quel ou en PNG refait de leurs pixels.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import struct
import unicodedata
import zlib
from pathlib import Path

SERVICE = Path(os.environ.get("MEGGA_FICHE") or Path(__file__).resolve().parents[2] / "fiche" / "src" / "composer.mjs")
DELAI = 90
LIBELLES = {
    "fr": {"surface": "Surface habitable", "chambres": "Chambres", "sdb": "Salles de bains", "pieces": "Pièces", "terrain": "Surface du terrain", "sur": "Prix sur demande"},
    "en": {"surface": "Living area", "chambres": "Bedrooms", "sdb": "Bathrooms", "pieces": "Rooms", "terrain": "Land area", "sur": "Price on request"},
}


async def composer(fiche: dict, photos: list[bytes], modele: str, version: str = "marque", sans_prix: bool = False,
                   marque: str = "") -> bytes:
    """Les octets du PDF, composés par le service de fiche."""
    demande = json.dumps({"modele": modele, "fiche": fiche, "photos": [base64.b64encode(p).decode() for p in photos],
                          "version": version, "sans_prix": sans_prix, "marque": marque}).encode()
    p = await asyncio.create_subprocess_exec("node", str(SERVICE), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                             stderr=asyncio.subprocess.PIPE)
    try:
        sortie, erreur = await asyncio.wait_for(p.communicate(demande), DELAI)
    except asyncio.TimeoutError:
        p.kill()
        raise RuntimeError("la fiche a pris trop de temps") from None
    if p.returncode != 0 or not sortie.startswith(b"%PDF"):
        raise RuntimeError(f"fiche non composée : {erreur.decode(errors='replace')[:200]}")
    return sortie


def court(t, n: int) -> str:
    return " ".join(str(t or "").split())[:n]


def milliers(n: int, langue: str) -> str:
    return f"{n:,}".replace(",", "," if langue == "en" else "’")


def fiche_libre(e: dict, description: list, contact: dict | None, site: str = "") -> dict:
    """Une fiche à partir de ce que le courtier donne sur WhatsApp, pour un bien qui n'est pas sur le site : la
    même forme que celle que rend la gestion du site."""
    langue = "en" if e.get("langue") == "en" else "fr"
    l = LIBELLES[langue]
    c = e.get("chiffres") or {}

    def entier(v):
        return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None

    chiffres = [x for x in (
        entier(c.get("surface")) is not None and {"libelle": l["surface"], "valeur": f"{milliers(c['surface'], langue)} m²"},
        entier(c.get("chambres")) is not None and {"libelle": l["chambres"], "valeur": str(c["chambres"])},
        entier(c.get("sdb")) is not None and {"libelle": l["sdb"], "valeur": str(c["sdb"])},
        entier(c.get("pieces")) is not None and {"libelle": l["pieces"], "valeur": str(c["pieces"])},
        entier(c.get("terrain")) is not None and {"libelle": l["terrain"], "valeur": f"{milliers(c['terrain'], langue)} m²"},
    ) if x][:4]
    details = []
    for d in e.get("details") or []:
        p = re.split(r"\s*:\s*", str(d))
        if len(p) >= 2 and p[0].strip() and ":".join(p[1:]).strip():
            details.append([court(p[0], 60), court(" : ".join(p[1:]), 120)])
    return {
        "langue": langue, "titre": court(e.get("titre"), 140), "adresse": court(e.get("adresse"), 120), "confidentiel": None,
        "prix": court(e.get("prix"), 60) or l["sur"], "accroche": court(e.get("accroche"), 1000), "description": description,
        "chiffres": chiffres, "details": details[:30],
        "equipements": [court(x, 40) for x in e.get("equipements") or [] if court(x, 40)][:24], "reference": None, "photos": [],
        "contact": contact and {"nom": contact.get("nom", ""), "fonction": contact.get("fonction", ""), "email": contact.get("email", ""),
                                "telephone": contact.get("telephone", ""), "site": site},
    }


def anonymiser(fiche: dict, marque: str = "") -> dict:
    """La version anonyme : ni contact, ni référence, ni ligne qui nomme la référence ou la marque."""
    nom = re.compile(re.escape(marque).replace(r"\ ", r"\s*"), re.I) if marque.strip() else None
    details = [d for d in fiche.get("details") or []
               if not (isinstance(d, list) and d and re.fullmatch(r"r[ée]f[ée]rence", str(d[0]).strip(), re.I))
               and not (nom and nom.search(json.dumps(d, ensure_ascii=False)))]
    return {**fiche, "contact": None, "reference": None, "details": details}


def nom_de_fichier(titre: str, langue: str = "fr") -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", str(titre or "fiche")) if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60] or "fiche"
    return f"{s}{'-en' if langue == 'en' else ''}.pdf"


# Les photos d'une plaquette PDF

MIN_COTE = 500
MIN_PIXELS = 300_000
RAPPORT_MAX = 3
GARDEES = 30
BRUT_MAX = 60_000_000
FENETRE = 8192


def dimensions_jpeg(o: bytes) -> tuple[int, int, int] | None:
    """(largeur, hauteur, composantes) d'un JPEG, lus dans son en-tête."""
    i = 2
    while i + 9 < len(o):
        if o[i] != 0xFF:
            return None
        m = o[i + 1]
        if m == 0xFF:
            i += 1
            continue
        if m == 0xD8 or 0xD0 <= m <= 0xD7 or m == 0x01:
            i += 2
            continue
        longueur = (o[i + 2] << 8) | o[i + 3]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            return (o[i + 7] << 8) | o[i + 8], (o[i + 5] << 8) | o[i + 6], o[i + 9]
        i += 2 + longueur
    return None


def _objet(o: bytes, n: str, cache: dict) -> str:
    if n not in cache:
        m = re.search(rb"(?<![^\s])" + n.encode() + rb" 0 obj", o)
        cache[n] = re.split(r"endobj|\bstream\b", o[m.end():m.end() + 4096].decode("latin-1"))[0] if m else ""
    return cache[n]


def _entier(dico: str, nom: str, o: bytes, cache: dict) -> int | None:
    m = re.search(rf"/{nom}\s+(\d+)(?:\s+(\d+)\s+R)?", dico)
    if not m:
        return None
    if m.group(2) is None:
        return int(m.group(1))
    v = re.match(r"\s*(\d+)", _objet(o, m.group(1), cache))
    return int(v.group(1)) if v else None


def _canaux(dico: str, o: bytes, cache: dict) -> int | None:
    m = re.search(r"/ColorSpace\s*(/\w+|\[[^\]]*\]|\d+\s+\d+\s+R)", dico)
    cs = m.group(1) if m else ""
    if cs[:1].isdigit():
        cs = _objet(o, cs.split()[0], cache).strip()
    if re.search(r"DeviceRGB|CalRGB", cs):
        return 3
    if re.search(r"DeviceGray|CalGray", cs):
        return 1
    if "DeviceCMYK" in cs:
        return 4
    icc = re.search(r"ICCBased\s+(\d+)\s+\d+\s+R", cs)
    return _entier(_objet(o, icc.group(1), cache), "N", o, cache) if icc else None


def images_du_pdf(o: bytes) -> list[dict]:
    """Les images d'un PDF qui ont l'air de photos, dans l'ordre du fichier, les GARDEES plus grandes."""
    trouvees, cache, vues = [], {}, set()
    for m in re.finditer(rb"/Image(?=[\s/<>\[\]()%])", o):
        i = m.start()
        s = o.find(b"stream", i, min(len(o), i + FENETRE))
        d0 = o.rfind(b"obj", max(0, i - FENETRE), i)
        if s < 0 or d0 < 0:
            continue
        dico = o[d0 + 3:s].decode("latin-1")
        if "endobj" in dico or not re.search(r"/Subtype\s*/Image\b", dico) or re.search(r"/ImageMask\s+true", dico):
            continue
        f = re.search(r"/Filter\s*(\[[^\]]*\]|/\w+)", dico)
        filtres = ",".join(re.findall(r"/\w+", f.group(1))) if f else ""
        mode = {"/DCTDecode": "jpeg", "/FlateDecode,/DCTDecode": "flate-jpeg", "/FlateDecode": "flate"}.get(filtres)
        if not mode:
            continue
        debut = s + 6
        if o[debut:debut + 2] == b"\r\n":
            debut += 2
        elif o[debut:debut + 1] in (b"\n", b"\r"):
            debut += 1
        longueur = _entier(dico, "Length", o, cache)
        fin = debut + longueur if longueur is not None and debut + longueur <= len(o) else -1
        if fin >= 0 and not o[fin:fin + 32].lstrip().startswith(b"endstream"):
            fin = -1
        if fin < 0:
            fin = o.find(b"endstream", debut)
            if fin < 0:
                continue
            while fin > debut and o[fin - 1] in b"\x00\t\n\x0c\r ":
                fin -= 1
        largeur, hauteur = _entier(dico, "Width", o, cache) or 0, _entier(dico, "Height", o, cache) or 0
        n = _canaux(dico, o, cache)
        if mode == "jpeg":
            j = dimensions_jpeg(o[debut:min(fin, debut + 65536)])
            if not j or j[2] not in (3, 4):
                continue
            largeur, hauteur, n = j
        elif mode == "flate" and (n != 3 or _entier(dico, "BitsPerComponent", o, cache) != 8):
            continue
        if min(largeur, hauteur) < MIN_COTE or largeur * hauteur < MIN_PIXELS or max(largeur, hauteur) / min(largeur, hauteur) > RAPPORT_MAX:
            continue
        signature = (fin - debut, o[debut + 16:min(fin, debut + 48)], o[max(debut, fin - 32):fin])
        if signature in vues:
            continue
        vues.add(signature)
        image = {"debut": debut, "fin": fin, "mode": mode, "largeur": largeur, "hauteur": hauteur}
        if mode == "flate":
            pred = _entier(dico, "Predictor", o, cache) or 1
            image.update(predicteur=pred, png=pred >= 10 and (_entier(dico, "Columns", o, cache) or largeur) == largeur
                         and (_entier(dico, "Colors", o, cache) or 1) == 3)
        trouvees.append(image)
    grandes = sorted(trouvees, key=lambda x: -x["largeur"] * x["hauteur"])[:GARDEES]
    return [x for x in trouvees if x in grandes]


def _png(largeur: int, hauteur: int, donnees_zlib: bytes) -> bytes:
    def bloc(genre: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + genre + d + struct.pack(">I", zlib.crc32(genre + d) & 0xFFFFFFFF)

    tete = struct.pack(">IIBBBBB", largeur, hauteur, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + bloc(b"IHDR", tete) + bloc(b"IDAT", donnees_zlib) + bloc(b"IEND", b"")


IMAGE_MAX = 25_000_000  # une photo tirée d'un PDF, une fois décompressée


def _decompresser(brut: bytes, maximum: int) -> bytes:
    """zlib, borné : une plaquette piégée (quelques Ko qui en font des centaines de Mo) est refusée sans remplir la
    mémoire du conteneur (relecture du 16.11.2026, I6)."""
    d = zlib.decompressobj()
    sortie = d.decompress(brut, maximum)
    if d.unconsumed_tail:
        raise ValueError("image du PDF trop lourde une fois décompressée")
    return sortie


def octets_image(pdf: bytes, im: dict) -> bytes:
    """Les octets d'une image du PDF, en JPEG ou en PNG."""
    brut = pdf[im["debut"]:im["fin"]]
    if im["mode"] == "jpeg":
        return brut
    if im["mode"] == "flate-jpeg":
        return _decompresser(brut, IMAGE_MAX)
    if im.get("png"):
        return _png(im["largeur"], im["hauteur"], brut)
    if im.get("predicteur") != 1 or im["largeur"] * im["hauteur"] * 3 > BRUT_MAX:
        raise ValueError("image du PDF illisible")
    pixels = _decompresser(brut, im["largeur"] * im["hauteur"] * 3)
    ligne = im["largeur"] * 3
    if len(pixels) < ligne * im["hauteur"]:
        raise ValueError("image du PDF incomplète")
    filtrees = b"".join(b"\x00" + pixels[y * ligne:(y + 1) * ligne] for y in range(im["hauteur"]))
    return _png(im["largeur"], im["hauteur"], zlib.compress(filtrees))
