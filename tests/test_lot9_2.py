"""Lot 9.2 : la base de connaissances d'un client (noyau/connaissances.py)."""

import base64
import hashlib
import json
import os
import re
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from noyau import config as configuration, connaissances, stockage
from noyau.agent import consignes
from noyau.app import creer, outils_du_client

CONF = configuration.lire("clients/exemple.yaml").model_dump(mode="json")
MODELE = os.environ.get("MEGGA_MODELE_DIR")


class FauxVectoriseur:
    """Des mots en commun, des vecteurs proches : de quoi tester sans le modèle."""

    def __init__(self):
        self.appels = 0

    def vecteurs(self, textes):
        self.appels += 1
        sortie = np.zeros((len(textes), connaissances.DIMENSION), dtype=np.float32)
        for i, t in enumerate(textes):
            for mot in re.findall(r"\w{4,}", t.lower()):
                sortie[i, int(hashlib.md5(mot.encode()).hexdigest(), 16) % connaissances.DIMENSION] += 1
        n = np.linalg.norm(sortie, axis=1, keepdims=True)
        return sortie / np.clip(n, 1e-9, None)


@pytest.fixture
def url(tmp_path):
    return f"sqlite:///{tmp_path}/client.db"


def base(url):
    return connaissances.Base(stockage.Connaissances(url), FauxVectoriseur())


CONDITIONS = """Conditions de location

Les frais de dossier s'élèvent à 450 CHF pour toute location. Ils sont dus à la signature du bail.

Horaires

L'agence est ouverte du lundi au vendredi, de 9 h à 18 h, et le samedi matin sur rendez-vous."""


# Lire et découper


def test_le_decoupage_garde_tout_et_se_chevauche():
    texte = " ".join(f"Phrase numéro {i} sur la location et ses conditions." for i in range(80))
    passages = connaissances.decouper(texte, taille=300, chevauchement=80)
    assert len(passages) > 5 and all(len(p) <= 360 for p in passages)
    for i in range(80):
        assert any(f"numéro {i} " in p for p in passages), i
    # chaque passage reprend la fin du précédent
    assert passages[1].split(".")[0] in passages[0]


def test_lire_texte_html_et_pdf():
    assert connaissances.lire(CONDITIONS.encode(), "texte").startswith("Conditions de location")
    page = b"<html><style>p{}</style><script>alert(1)</script><h1>Horaires</h1><p>Ouvert de 9 h &agrave; 18 h.</p></html>"
    lu = connaissances.lire(page, "html")
    assert "alert" not in lu and "p{}" not in lu and "Horaires" in lu and "à 18 h" in lu
    assert "frais de dossier" in connaissances.lire(pdf("Les frais de dossier sont de 450 CHF."), "pdf")
    for mauvais, genre in ((b"%PDF-casse", "pdf"), (b"x", "texte"), (b"y" * (connaissances.CONTENU_MAX + 1), "texte"), (b"abc", "doc")):
        with pytest.raises(ValueError):
            connaissances.lire(mauvais, genre)


def pdf(texte: str) -> bytes:
    """Un PDF d'une page, écrit à la main, avec une ligne de texte."""
    flux = f"BT /F1 12 Tf 72 720 Td ({texte}) Tj ET".encode("latin-1")
    objets = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
              b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
              b"<< /Length " + str(len(flux)).encode() + b" >>\nstream\n" + flux + b"\nendstream",
              b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    sortie, positions = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objets, 1):
        positions.append(len(sortie))
        sortie += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    debut = len(sortie)
    sortie += f"xref\n0 {len(objets) + 1}\n0000000000 65535 f \n".encode()
    sortie += b"".join(f"{p:010d} 00000 n \n".encode() for p in positions)
    sortie += f"trailer\n<< /Size {len(objets) + 1} /Root 1 0 R >>\nstartxref\n{debut}\n%%EOF".encode()
    return bytes(sortie)


# La base


def test_ajouter_chercher_retirer(url):
    b = base(url)
    d = b.ajouter("Conditions de location", CONDITIONS.encode(), "texte", "conditions.txt")
    assert d["titre"] == "Conditions de location" and d["passages"] >= 1
    [r, *_] = b.chercher("Combien coûtent les frais de dossier pour une location ?", seuil=0.1)
    assert "450 CHF" in r["texte"] and r["titre"] == "Conditions de location" and r["source"] == "conditions.txt"
    assert b.chercher("planètes galaxie astronomie", seuil=0.1) == []
    assert [x["titre"] for x in b.documents()] == ["Conditions de location"]
    assert b.retirer(d["id"]) and b.chercher("frais de dossier location", seuil=0.0) == []
    assert not b.retirer(d["id"])


def test_les_bornes_du_client(url, monkeypatch):
    monkeypatch.setattr(stockage, "DOCUMENTS_MAX", 1)
    b = base(url)
    b.ajouter("Un", CONDITIONS.encode(), "texte")
    with pytest.raises(ValueError, match="déjà 1 documents"):
        b.ajouter("Deux", CONDITIONS.encode(), "texte")
    with pytest.raises(ValueError, match="titre"):
        b.ajouter("  ", CONDITIONS.encode(), "texte")


def test_l_index_est_garde_en_memoire(url):
    b = base(url)
    b.ajouter("Conditions", CONDITIONS.encode(), "texte")
    v = b.vectoriseur
    b.chercher("frais de dossier")
    b.chercher("horaires de l'agence")
    avant = v.appels
    b.chercher("samedi")
    assert v.appels == avant + 1  # la question seulement : les passages ne sont pas relus


def test_l_outil(url):
    b = base(url)
    b.ajouter("Conditions de location", CONDITIONS.encode(), "texte")
    [chercher] = connaissances.outils(b)
    assert chercher.__name__ == "chercher_dans_les_documents"
    trouve = chercher("frais de dossier location signature bail")
    assert trouve.startswith("Extraits des documents") and "(Conditions de location)" in trouve and "450 CHF" in trouve
    assert "n'invente pas" in chercher("planètes galaxie astronomie")
    assert "pas consultables" in connaissances.outils(None)[0]("frais")


def test_un_document_envoye_a_une_route():
    assert connaissances.contenu_de({"titre": "T", "genre": "texte", "texte": "abc"}) == ("T", b"abc", "texte", None)
    assert connaissances.contenu_de({"titre": "T", "genre": "pdf", "base64": base64.b64encode(b"%PDF").decode(), "source": "a.pdf"})[1] == b"%PDF"
    for mauvais in ({"genre": "texte", "texte": "x"}, {"titre": "T", "genre": "doc", "texte": "x"}, {"titre": "T", "base64": "!!"},
                    {"titre": "T", "genre": "texte"}):
        with pytest.raises(ValueError):
            connaissances.contenu_de(mauvais)


# L'agent


def test_le_groupe_d_outils_et_sa_consigne(url):
    conf = configuration.lire({**CONF, "outils": ["connaissances"]})
    noms = [o.__name__ for o in outils_du_client(conf, stockage.Rappels(url), connaissances=base(url))]
    assert "chercher_dans_les_documents" in noms
    assert connaissances.CONSIGNE in consignes(conf)
    sans = configuration.lire(CONF)
    assert "chercher_dans_les_documents" not in [o.__name__ for o in outils_du_client(sans, stockage.Rappels(url))]
    assert connaissances.CONSIGNE not in consignes(sans)
    # par rôle : un visiteur peut l'avoir sans qu'un partenaire l'ait
    roles = configuration.lire({**CONF, "roles": {"visiteur": {"outils": ["rappels", "connaissances"]}, "partenaire": {}}})
    assert connaissances.CONSIGNE in consignes(roles, roles.les_roles()["visiteur"])
    assert connaissances.CONSIGNE not in consignes(roles, roles.les_roles()["partenaire"])


def test_les_routes_internes(url):
    from test_app import FauxAgent, FauxExpediteur

    conf = {**CONF, "outils": ["connaissances"]}
    app = creer({"CLIENT_CONFIG": json.dumps(conf), "DATABASE_URL": url, "INTERNE_TOKEN": "interne"},
                agent=FauxAgent(), expediteur=FauxExpediteur(), connaissances=base(url))
    t, interne = TestClient(app), {"x-megga-interne": "interne"}
    assert t.get("/interne/connaissances").status_code == 401
    r = t.post("/interne/connaissances", headers=interne, json={"titre": "Conditions", "genre": "texte", "texte": CONDITIONS})
    assert r.status_code == 200 and r.json()["titre"] == "Conditions"
    r2 = t.post("/interne/connaissances", headers=interne,
                json={"titre": "Tarifs", "genre": "pdf", "base64": base64.b64encode(pdf("Les frais de dossier sont de 450 CHF.")).decode()})
    assert r2.status_code == 200, r2.text
    assert t.post("/interne/connaissances", headers=interne, json={"titre": "Vide", "genre": "texte", "texte": "x"}).status_code == 400
    assert [d["titre"] for d in t.get("/interne/connaissances", headers=interne).json()["documents"]] == ["Conditions", "Tarifs"]
    assert t.delete(f"/interne/connaissances/{r.json()['id']}", headers=interne).json()["retire"] is True
    assert t.delete("/interne/connaissances/abc", headers=interne).status_code == 400
    # un agent sans le groupe d'outils n'a pas de base
    sans = creer({"CLIENT_CONFIG": json.dumps(CONF), "DATABASE_URL": url, "INTERNE_TOKEN": "interne"},
                 agent=FauxAgent(), expediteur=FauxExpediteur())
    assert TestClient(sans).get("/interne/connaissances", headers=interne).status_code == 409


def test_l_atelier_gere_les_documents(tmp_path):
    from atelier.app import creer as creer_atelier
    from atelier.porte import PorteErreur
    from test_lot5 import ADMIN, CLE_PILOTAGE_TEXTE, FaussePorte, FauxModele, jeton_client, nouveau_client

    class Porte(FaussePorte):
        def __init__(self):
            super().__init__()
            self.appels = []

        async def connaissances(self, ident, methode="GET", chemin="", corps=None):
            self.appels.append((ident, methode, chemin, corps and corps.get("titre")))
            if corps and corps.get("titre") == "Vide":
                raise PorteErreur(400, '{"erreur": "document sans texte lisible"}')
            return {"documents": []} if methode == "GET" else {"id": 1, "titre": corps["titre"], "passages": 3} if corps else {"id": 1, "retire": True}

    porte = Porte()
    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/atelier.db",
                                  "ESSAIS_DIR": str(tmp_path / "essais"), "PILOTAGE_CLE": CLE_PILOTAGE_TEXTE},
                                 porte=porte, principal_essai=FauxModele()))
    nouveau_client(t)
    client = jeton_client(t)
    assert t.get("/atelier/clients/exemple/connaissances", headers=client).json() == {"documents": []}
    r = t.post("/atelier/clients/exemple/connaissances", headers=client, json={"titre": "Conditions", "genre": "texte", "texte": "…"})
    assert r.status_code == 201 and r.json()["passages"] == 3
    vide = t.post("/atelier/clients/exemple/connaissances", headers=client, json={"titre": "Vide", "genre": "texte", "texte": "x"})
    assert vide.status_code == 400 and "sans texte" in vide.json()["erreur"]
    assert t.post("/atelier/clients/exemple/connaissances", headers=client, json={"titre": "T", "autre": 1}).status_code == 400
    assert t.delete("/atelier/clients/exemple/connaissances/1", headers=client).json()["retire"] is True
    assert [(m, c, ti) for _, m, c, ti in porte.appels] == [("GET", "", None), ("POST", "", "Conditions"), ("POST", "", "Vide"), ("DELETE", "/1", None)]


# Avec le vrai modèle (dans l'image, ou MEGGA_MODELE_DIR)


@pytest.mark.skipif(not (MODELE and (Path(MODELE) / "model.onnx").is_file()), reason="modèle de recherche absent (MEGGA_MODELE_DIR)")
def test_avec_le_vrai_modele(url):
    b = connaissances.Base(stockage.Connaissances(url), connaissances.Vectoriseur(MODELE))
    b.ajouter("Conditions de location", CONDITIONS.encode(), "texte")
    b.ajouter("Adresse", "Unsere Agentur befindet sich an der Avenue de la Gare 12 in Lausanne.".encode(), "texte")
    assert "450 CHF" in b.chercher("Combien coûte le dossier pour louer un appartement ?")[0]["texte"]
    assert b.chercher("Où se trouve votre agence ?")[0]["titre"] == "Adresse"  # d'une langue à l'autre
    assert b.chercher("Quelle est la capitale du Japon ?") == []  # sous le seuil : rien plutôt qu'un passage au hasard
