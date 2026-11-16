"""Lot 7.3 : la fiche PDF (le service JavaScript de l'image) et les photos d'une plaquette PDF."""

import asyncio
import base64
import shutil
import struct
import zlib
from pathlib import Path

import httpx
import pytest

from noyau import stockage
from packs.immobilier import fiche as fiches
from packs.immobilier.annonces import Services, outils
from packs.immobilier.gestion import Gestion
from packs.immobilier.redaction import Choisisseuse, lire_choix
from test_lot7_2 import CONF, GREG, FausseRedactrice, FauxExp, FauxSite, Tour, run
from noyau.roles import Personnes, lire_gestionnaires

# Une photo JPEG de 1 × 1 pixel, que pdf-lib sait poser.
JPEG = base64.b64decode("/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/yQALCAABAAEBAREA/8wABgAQEAX/2gAIAQEAAD8A0s8g/9k=")
SERVICE_PRET = shutil.which("node") is not None and (Path(fiches.SERVICE).parents[1] / "node_modules" / "pdf-lib").exists()
avec_service = pytest.mark.skipif(not SERVICE_PRET, reason="Node ou fiche/node_modules absents (cd fiche && npm ci)")


def jpeg_factice(largeur: int, hauteur: int, composantes: int = 3) -> bytes:
    """Un en-tête JPEG (SOI, SOF0) qui dit ses dimensions : ce que lit l'extraction, sans image décodable."""
    sof = struct.pack(">BBHBHHB", 0xFF, 0xC0, 8 + 3 * composantes, 8, hauteur, largeur, composantes) + b"\x01\x22\x00" * composantes
    return b"\xff\xd8" + sof + b"\xff\xd9"


def pdf_avec_images() -> bytes:
    """Un PDF avec quatre images : une photo JPEG, une photo en pixels (Flate), une vignette et une image grise."""
    objets = []

    def image(dico: str, flux: bytes):
        objets.append(f"<< /Type /XObject /Subtype /Image {dico} /Length {len(flux)} >>".encode() + b"\nstream\n" + flux + b"\nendstream")

    image("/Width 800 /Height 600 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode", jpeg_factice(800, 600))
    pixels = bytes([10, 120, 200]) * (700 * 500)
    image("/Width 700 /Height 500 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode", zlib.compress(pixels))
    image("/Width 100 /Height 100 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode", jpeg_factice(100, 100))
    image("/Width 800 /Height 600 /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /DCTDecode", jpeg_factice(800, 600, 1))
    corps = b"%PDF-1.7\n"
    for i, o in enumerate(objets, 1):
        corps += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    return corps + b"%%EOF\n"


def test_les_photos_d_une_plaquette():
    pdf = pdf_avec_images()
    images = fiches.images_du_pdf(pdf)
    assert [(i["mode"], i["largeur"], i["hauteur"]) for i in images] == [("jpeg", 800, 600), ("flate", 700, 500)]
    assert fiches.octets_image(pdf, images[0]).startswith(b"\xff\xd8")
    png = fiches.octets_image(pdf, images[1])
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", png[16:24]) == (700, 500)
    assert fiches.dimensions_jpeg(jpeg_factice(1024, 768)) == (1024, 768, 3)


def test_la_fiche_libre_et_anonyme():
    f = fiches.fiche_libre({"langue": "fr", "titre": "Villa contemporaine", "prix": "", "chiffres": {"surface": 4200, "chambres": 5, "sdb": True},
                            "details": ["Étage : rez", "sans valeur"], "equipements": ["Piscine"]}, ["Une villa."],
                           {"nom": "Agent", "email": "a@exemple.ch"}, "exemple.ch")
    assert f["prix"] == "Prix sur demande" and f["chiffres"] == [{"libelle": "Surface habitable", "valeur": "4’200 m²"}, {"libelle": "Chambres", "valeur": "5"}]
    assert f["details"] == [["Étage", "rez"]] and f["contact"]["site"] == "exemple.ch"
    a = fiches.anonymiser({**f, "reference": "FSP-12", "details": [["Référence", "FSP-12"], ["Agence", "Four Seasons Properties"], ["Étage", "rez"]]},
                          "Four Seasons Properties")
    assert a["contact"] is None and a["reference"] is None and a["details"] == [["Étage", "rez"]]
    assert fiches.nom_de_fichier("Villa à Cologny", "en") == "villa-a-cologny-en.pdf"


def test_le_choix_des_photos():
    assert lire_choix('{"ordre": [3, 1, 3, 9]}', 4, 10) == [3, 1]
    assert lire_choix('```json\n{"ordre": [2]}\n```', 4, 10) == [2]
    assert lire_choix('{"ordre": [4, 1, 2', 4, 2) == [4, 1]  # coupée
    assert lire_choix("rien", 4, 10) is None

    class Reponse:
        def __init__(self, texte):
            self.content = [type("B", (), {"text": texte})()]

    class Client:
        def __init__(self, texte):
            self.messages = self
            self.texte = texte

        async def create(self, **_):
            return Reponse(self.texte)

    photos = [JPEG + bytes([i]) for i in range(3)]
    assert run(Choisisseuse("cle", "Agence", client=Client('{"ordre": [3, 1]}')).choisir(photos, 2)) == [photos[2], photos[0]]
    assert run(Choisisseuse("cle", "Agence", client=Client("illisible")).choisir(photos, 2)) == photos[:2]


class SiteAvecPhotos(FauxSite):
    def __call__(self, r: httpx.Request) -> httpx.Response:
        if r.url.path.startswith("/gestion/images/"):
            return httpx.Response(200, content=JPEG)
        if r.url.path.endswith("/fiche"):
            return httpx.Response(200, json={"fiche": {
                "langue": "fr", "titre": "Villa contemporaine avec vue sur le lac", "adresse": "1223 Cologny", "confidentiel": None,
                "prix": "CHF 9’500’000", "accroche": "Face au lac.", "description": ["Une villa."], "chiffres": [], "details": [["Référence", "FSP-1"]],
                "equipements": [], "reference": "FSP-1", "photos": ["/gestion/images/a.jpg", "/gestion/images/b.jpg"],
                "contact": {"nom": "Agent", "fonction": "Courtier", "email": "a@exemple.ch", "telephone": "", "site": ""}}})
        return super().__call__(r)


class ExpPdf(FauxExp):
    def __init__(self):
        super().__init__()
        self.deposes = []

    async def telecharger(self, media_id, maximum=0):
        return pdf_avec_images() if media_id.startswith("DOC") else JPEG

    async def televerser(self, octets, type_, nom):
        self.deposes.append((octets, type_, nom))
        return "M1"

    async def document(self, vers, nom, media_id="", lien="", legende=""):
        self.envois.append(("document", vers, nom, media_id, legende))


@pytest.fixture
def alix(tmp_path):
    url = f"sqlite:///{tmp_path}/fsp.db"
    site, exp = SiteAvecPhotos(), ExpPdf()
    personnes = Personnes(CONF, lire_gestionnaires('{"' + GREG + '": "greg@agence.ch"}'))
    medias = stockage.Medias(url)
    s = Services(Gestion(CONF.gestion, "cle-gestion", transport=httpx.MockTransport(site)), personnes, medias, stockage.Etats(url), exp,
                 FausseRedactrice(), CONF.gestion.noms_interdits, None, None, CONF.gestion.fiche, CONF.entreprise)
    return {f.__name__: f for f in outils(s)}, site, exp, medias


def test_les_photos_d_un_pdf_recu_deviennent_des_medias(alix):
    o, site, exp, medias = alix
    medias.noter(GREG, "document", "DOC1", "application/pdf", "plaquette.pdf")
    r = run(o["photos_du_pdf"](1, Tour(GREG, "t1")))
    assert "2 photo(s) sortie(s) du PDF 1 (« plaquette.pdf ») : média(s) 2, 3" in r
    assert medias.lire(GREG, 3)["media_id"] == "pdf:DOC1#1" and medias.lire(GREG, 3)["type"] == "image/png"
    assert "déjà sorties" in run(o["photos_du_pdf"](1, Tour(GREG, "t2")))
    # Elles servent comme des photos reçues : ajoutées à une annonce, refaites depuis le PDF
    assert "2 photo(s) ajoutée(s)" in run(o["ajouter_photos"]("cologny-villa-lac", [2, 3], Tour(GREG, "t2")))


@avec_service
def test_la_fiche_d_une_annonce_du_site(alix):
    o, site, exp, _ = alix
    r = run(o["fiche_pdf"]("anonyme", "fr", Tour(GREG, "t1"), slug="cologny-villa-lac", sans_prix=True))
    assert "Fiche PDF envoyée" in r and "anonyme, sans prix, français, 2 photo(s)" in r
    pdf, genre, nom = exp.deposes[0]
    assert pdf.startswith(b"%PDF") and genre == "application/pdf" and nom == "villa-contemporaine-avec-vue-sur-le-lac.pdf"
    assert b"Four Seasons" not in pdf  # ni marque ni référence dans l'anonyme
    assert exp.envois[-1][:4] == ("document", GREG, nom, "M1")
    site.annonces["cologny-villa-lac"]["reference"] = "FSP-1"
    run(o["fiche_pdf"]("marque", "en", Tour(GREG, "t1"), reference="fsp 1"))
    assert exp.deposes[1][2].endswith("-en.pdf")
    with pytest.raises(ValueError, match="aucun bien en ligne"):
        run(o["fiche_pdf"]("anonyme", "fr", Tour(GREG, "t1"), reference="ZZZ"))


@avec_service
def test_la_fiche_d_un_bien_hors_du_site(alix):
    o, site, exp, medias = alix
    medias.noter(GREG, "image", "IMG1", "image/jpeg")
    with pytest.raises(ValueError, match="au moins une photo"):
        run(o["fiche_pdf"]("anonyme", "fr", Tour(GREG, "t1")))
    r = run(o["fiche_pdf"]("anonyme", "fr", Tour(GREG, "t1"), medias=[1], adresse="Vandœuvres", prix="CHF 4’000’000",
                           chiffres={"surface": 300, "chambres": 4}, notes="belle vue"))
    assert "1 photo(s)" in r and exp.deposes[-1][0].startswith(b"%PDF")
    assert exp.deposes[-1][2] == "villa-contemporaine-avec-vue-sur-le-lac.pdf"  # le titre rédigé


def test_sans_modele_de_fiche(tmp_path):
    url = f"sqlite:///{tmp_path}/x.db"
    s = Services(Gestion(CONF.gestion, "c", transport=httpx.MockTransport(FauxSite())),
                 Personnes(CONF, lire_gestionnaires('{"' + GREG + '": "greg@agence.ch"}')), stockage.Medias(url), stockage.Etats(url), FauxExp())
    o = {f.__name__: f for f in outils(s)}
    with pytest.raises(ValueError, match="modèle de fiche"):
        asyncio.run(o["fiche_pdf"]("anonyme", "fr", Tour(GREG, "t1"), slug="cologny-villa-lac"))
