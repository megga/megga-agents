"""Lot 7.2 : les outils d'annonces d'Alix FSP sur le socle, contre une fausse gestion de site."""

import asyncio
import time
import json
import re
from dataclasses import dataclass

import httpx
import pytest

from noyau import config as configuration, stockage
from noyau.roles import Personnes, lire_gestionnaires
from packs.immobilier import garde
from packs.immobilier.annonces import Services, outils
from packs.immobilier.gestion import Gestion
from packs.immobilier.redaction import lire_reponse

GREG = "+41790000001"
VISITEUR = "+41790000002"
CONF = configuration.lire("clients/four-seasons-properties.yaml")


@dataclass
class Tour:
    """Le contexte d'un tour d'Agno, tel que les outils le lisent."""

    user_id: str
    run_id: str


class FauxSite:
    """La gestion du site, en mémoire : annonces, photos, accès, recherches."""

    def __init__(self):
        self.annonces = {
            "cologny-villa-lac": {"slug": "cologny-villa-lac", "titre": "Villa contemporaine avec vue sur le lac", "localite": "Cologny",
                                  "adresse": "Chemin du Lac", "categorie": "Villa", "transaction": "vente", "prix": "CHF 9’500’000",
                                  "montant": 9500000, "devise": "CHF", "chambres": 5, "surface": 420, "accroche": "Le lac.",
                                  "description": ["Une villa.", ["liste", ["Piscine", "Jardin"]]], "en": {"titre": "Villa", "description": ["A villa."]},
                                  "photos": [["a.jpg", "salon"], ["b.jpg", "jardin"], ["c.jpg", "vue"]], "couverture": "a.jpg",
                                  "equipements": ["pool", "garden"], "courtier": "greg", "enLigne": True},
            "marbella-villa-olie": {"slug": "marbella-villa-olie", "titre": "Villa andalouse avec piscine", "localite": "Marbella",
                                    "prix": "EUR 4’200’000", "montant": 4200000, "devise": "EUR", "chambres": 4, "surface": 300,
                                    "photos": [["m.jpg", ""]], "couverture": "m.jpg", "courtier": "autre", "enLigne": True, "transaction": "vente",
                                    "categorie": "Villa", "equipements": ["pool"]},
        }
        self.acces = {}
        self.portes = []  # les PUT /acces/porte/<site>, dans l'ordre
        self.mot_de_passe_porte = {}
        self.recherches = [{"id": "r1", "client": {"nom": "Les Martin"}, "criteres": {"communes": ["Cologny"], "budgetMax": 10000000},
                            "biens": []}]
        self.appels = []
        self.recus = []

    def __call__(self, r: httpx.Request) -> httpx.Response:
        chemin = r.url.path.removeprefix("/api/gestion")
        self.appels.append((r.method, chemin, r.headers.get("x-gestion-compte")))
        corps = json.loads(r.content) if r.headers.get("content-type", "").startswith("application/json") and r.content else None
        if r.headers.get("x-gestion-compte") != "greg@agence.ch" or r.headers.get("authorization") != "Bearer cle-gestion":
            return httpx.Response(403, json={"erreur": "compte inconnu"})
        if chemin == "/resume":
            return httpx.Response(200, json={"moi": {"courtier": "greg", "role": "admin"}, "annonces": list(self.annonces.values()),
                                             "choix": {"communes": [{"slug": "cologny"}, {"slug": "marbella"}]}})
        if r.url.path.startswith("/gestion/images/"):
            return httpx.Response(200, content=b"\xff\xd8\xffphoto-du-site")
        m = re.fullmatch(r"/annonces/([a-z0-9-]+)(/[a-z]+)?", chemin)
        if chemin == "/annonces" and r.method == "POST":
            c = corps["champs"]
            slug = f"{c['localite'].lower()}-nouvelle"
            self.annonces[slug] = {"slug": slug, "titre": c["titre"], "localite": c["localite"], "photos": [], "envoi": c}
            return httpx.Response(200, json={"annonce": {"slug": slug}})
        if m:
            slug, suite = m.group(1), m.group(2) or ""
            a = self.annonces.get(slug)
            if a is None:
                return httpx.Response(404, json={"erreur": "annonce inconnue"})
            if suite == "" and r.method == "GET":
                return httpx.Response(200, json={"annonce": a, "sha": a.get("_sha", "sha-1")})
            if suite == "" and r.method == "PUT":
                if corps.get("sha") != a.get("_sha", "sha-1"):  # comme la vraie gestion : une version périmée est refusée
                    return httpx.Response(409, json={"erreur": "l'annonce a changé"})
                a.update(corps["champs"])
                a["_sha"] = f"sha-{int(a.get('_sha', 'sha-1')[4:]) + 1}"
                return httpx.Response(200, json={"annonce": a})
            if suite == "" and r.method == "DELETE":
                del self.annonces[slug]
                return httpx.Response(200, json={"titre": a["titre"]})
            if suite == "/visibilite":
                a["masquee"] = corps["masquee"]
                return httpx.Response(200, json={"annonce": a})
            if suite == "/photos" and r.method == "POST":
                self.recus.append(r.headers.get("content-type", "").split(";")[0])
                n = r.content.count(b'name="fichier"')
                a["photos"] = a.get("photos", []) + [[f"n{i}.jpg", ""] for i in range(n)]
                return httpx.Response(200, json={"photos": len(a["photos"])})
            if suite == "/photos" and r.method == "PUT":
                if [p[0] for p in a["photos"]] != corps["avant"]:
                    return httpx.Response(409, json={"erreur": "les photos ont changé"})
                a["photos"] = [[f, ""] for f in corps["photos"]]
                return httpx.Response(200, json={"photos": len(a["photos"])})
            if suite == "/documents":
                self.recus.append((r.headers.get("content-type"), r.url.params.get("titre"), r.content[:4]))
                return httpx.Response(200, json={"documents": 1})
            if suite == "/acces":
                if r.method == "GET":
                    return httpx.Response(200, json=self.acces.get(slug, {"prive": False}))
                self.acces[slug] = corps
                return httpx.Response(200, json={"annonce": a})
            if suite == "/videos" and r.method == "POST":
                a.setdefault("videos", []).append({"lien": corps["lien"], "titre": corps["titre"]})
                return httpx.Response(200, json={"videos": len(a["videos"])})
            if suite == "/videos" and r.method == "DELETE":
                a["videos"].pop(corps["numero"] - 1)
                return httpx.Response(200, json={"videos": len(a["videos"])})
            if suite == "/fiche":
                return httpx.Response(200, json={"fiche": {"titre": a["titre"], "adresse": "Cologny", "prix": a["prix"],
                                                           "chiffres": [{"libelle": "Chambres", "valeur": "5"}]}})
        m = re.fullmatch(r"/acces/porte/([a-z]+)", chemin)
        if m and r.method == "PUT":
            # Comme la vraie gestion : le site principal (geneve) ne rend que le mot de passe reçu ; les autres, celui en vigueur.
            site = m.group(1)
            self.portes.append((site, corps))
            if site == "geneve":
                return httpx.Response(200, json={"ok": True, "actif": corps["actif"], "motDePasse": corps["actif"] and corps.get("motDePasse") or None})
            mdp = corps.get("motDePasse") or self.mot_de_passe_porte.get(site) or corps.get("motDePasseSiAbsent") or ""
            self.mot_de_passe_porte[site] = mdp
            return httpx.Response(200, json={"ok": True, "actif": corps["actif"], "motDePasse": mdp or None})
        if chemin == "/clients" and r.method == "GET":
            return httpx.Response(200, json={"recherches": self.recherches})
        m = re.fullmatch(r"/clients/recherches/([A-Za-z0-9_-]+)", chemin)
        if m and r.method == "DELETE":
            r_ = next((x for x in self.recherches if x["id"] == m.group(1)), None)
            if r_ is None:
                return httpx.Response(404, json={"erreur": "recherche inconnue"})
            self.recherches.remove(r_)
            return httpx.Response(200, json={"client": r_["client"]})
        if chemin == "/clients/recherches" and r.method == "POST":
            return httpx.Response(200, json={"recherche": {"id": "r1", "client": corps["client"], "criteres": corps.get("criteres", {}),
                                                          "biens": ["cologny-villa-lac"]}})
        return httpx.Response(404, json={"erreur": f"route inconnue {r.method} {chemin}"})


class FauxExp:
    def __init__(self):
        self.envois = []

    async def telecharger(self, media_id, maximum=0):
        return b"%PDF-1.7" if media_id.startswith("DOC") else b"\xff\xd8\xffphoto-" + media_id.encode()

    async def texte(self, vers, texte):
        self.envois.append(("texte", vers, texte))

    async def carrousel(self, vers, corps, cartes):
        self.envois.append(("carrousel", vers, corps, cartes))

    async def document(self, vers, nom, media_id="", lien="", legende=""):
        self.envois.append(("document", vers, nom, lien))

    async def formulaire(self, vers, flow_id, corps, bouton, jeton, ecran):
        self.envois.append(("formulaire", vers, flow_id, ecran))


class FausseRedactrice:
    def __init__(self, titre="Villa contemporaine avec vue sur le lac"):
        self.titre = titre
        self.appels = []

    async def rediger(self, faits, notes, photos):
        self.appels.append((faits, notes, len(photos)))
        return {"titre": self.titre, "titre_en": "Contemporary villa with lake view", "accroche": "Une villa — face au lac.",
                "accroche_en": "A villa facing the lake.", "description": "Une villa lumineuse.\n\n- Piscine\n- Jardin",
                "description_en": "A bright villa.\n\n- Pool\n- Garden", "adresse_en": "1223 Cologny, Geneva"}


@pytest.fixture
def alix(tmp_path):
    url = f"sqlite:///{tmp_path}/fsp.db"
    site = FauxSite()
    exp = FauxExp()
    personnes = Personnes(CONF, lire_gestionnaires(json.dumps({GREG: "greg@agence.ch"})))
    medias, etats = stockage.Medias(url), stockage.Etats(url)
    gestion = Gestion(CONF.gestion, "cle-gestion", transport=httpx.MockTransport(site))
    redactrice = FausseRedactrice()
    services = Services(gestion, personnes, medias, etats, exp, redactrice, CONF.gestion.noms_interdits, "1234567")
    o = {f.__name__: f for f in outils(services)}
    return o, site, exp, medias, etats, redactrice


def run(coro):
    return asyncio.run(coro)


def test_seul_un_gestionnaire(alix):
    o, *_ = alix
    with pytest.raises(ValueError, match="pas de compte"):
        run(o["lister_annonces"]("", Tour(VISITEUR, "t1")))


def test_lister_et_voir(alix):
    o, site, *_ = alix
    liste = run(o["lister_annonces"]("lac", Tour(GREG, "t1")))
    assert "cologny-villa-lac | Villa contemporaine avec vue sur le lac, Cologny | CHF 9’500’000 | 3 photo(s)" in liste
    assert "marbella" not in liste.split("\n")[1] and "Communes du site : cologny, marbella" in liste
    tout = run(o["lister_annonces"]("", Tour(GREG, "t1")))
    assert tout.index("cologny-villa-lac") < tout.index("marbella-villa-olie")  # les siennes d'abord
    vue = run(o["voir_annonce"]("cologny-villa-lac", Tour(GREG, "t1")))
    assert "Photos (3, la 1 en couverture) :\n1. salon\n2. jardin\n3. vue" in vue
    assert "Une villa.\n\n- Piscine\n- Jardin" in vue
    with pytest.raises(ValueError, match="slug"):
        run(o["voir_annonce"]("../admin", Tour(GREG, "t1")))
    assert site.appels[0][2] == "greg@agence.ch"


def test_du_brouillon_a_l_annonce(alix):
    o, site, exp, medias, etats, redactrice = alix
    for n in ("IMG1", "IMG2"):
        medias.noter(GREG, "image", n, "image/jpeg")
    medias.noter(GREG, "document", "DOC1", "application/pdf", "plaquette.pdf")
    t1 = Tour(GREG, "t1")
    with pytest.raises(ValueError, match="il manque : adresse, prix"):
        run(o["preparer_annonce"](t1, commune="Cologny", categorie="Villa", transaction="vente"))
    b = run(o["preparer_annonce"](t1, adresse="1223 Cologny", prix={"montant": 9500000, "devise": "CHF"}, medias=[1, 2], pdf=3,
                                  chambres=5, surface=420, notes="vue sur le lac, piscine"))
    assert "Brouillon prêt, rien n'est encore créé" in b and "CHF 9’500’000" in b and "2 photo(s), la plaquette PDF" in b
    assert "Une villa, face au lac." in b  # la rédaction, sans tiret long
    (faits, notes, n_photos), = redactrice.appels
    assert faits["commune"] == "Cologny" and notes == "vue sur le lac, piscine" and n_photos == 2
    # Pas dans le même tour que le brouillon
    with pytest.raises(ValueError, match="pas encore vu le brouillon"):
        run(o["creer_annonce"](t1))
    r = run(o["creer_annonce"](Tour(GREG, "t2")))
    assert "Annonce créée, slug cologny-nouvelle, avec 2 photo(s)" in r and "plaquette PDF est rangée" in r
    envoi = site.annonces["cologny-nouvelle"]["envoi"]
    assert envoi["prix"] == {"montant": 9500000, "devise": "CHF"} and envoi["description"] == ["Une villa lumineuse.", ["liste", ["Piscine", "Jardin"]]]
    assert envoi["en"]["adresse"] == "1223 Cologny, Geneva" and envoi["localite"] == "Cologny"
    assert "multipart/form-data" in site.recus and ("application/pdf", "Plaquette", b"%PDF") in site.recus
    assert etats.lire(GREG, "brouillon") is None
    with pytest.raises(ValueError, match="aucun brouillon complet"):
        run(o["creer_annonce"](Tour(GREG, "t3")))


def test_un_site_a_part_demande_le_quartier_et_les_medias_doivent_etre_des_photos(alix):
    o, _, _, medias, *_ = alix
    medias.noter(GREG, "document", "DOC1", "application/pdf", "plaquette.pdf")
    with pytest.raises(ValueError, match="quartier"):
        run(o["preparer_annonce"](Tour(GREG, "t1"), commune="Marbella", categorie="Villa", transaction="vente", adresse="Nagüeles",
                                  prix={"montant": 4200000, "devise": "EUR"}))
    with pytest.raises(ValueError, match="pas tous des photos"):
        run(o["preparer_annonce"](Tour(GREG, "t1"), commune="Marbella", quartier="Nagüeles", medias=[1]))
    with pytest.raises(ValueError, match="média inconnu"):
        run(o["preparer_annonce"](Tour(GREG, "t1"), medias=[9]))
    with pytest.raises(ValueError, match="prix"):
        run(o["preparer_annonce"](Tour(GREG, "t2"), prix={"montant": "beaucoup"}))


def test_les_garde_fous(alix):
    o, site, *_ = alix
    with pytest.raises(ValueError, match="nomme « Greg »"):
        run(o["modifier_annonce"]("cologny-villa-lac", Tour(GREG, "t1"), titre="Villa de Greg avec vue sur le lac"))
    with pytest.raises(ValueError, match="trop court"):
        run(o["modifier_annonce"]("cologny-villa-lac", Tour(GREG, "t1"), titre="Villa"))
    with pytest.raises(ValueError, match="liste de mots"):
        run(o["modifier_annonce"]("cologny-villa-lac", Tour(GREG, "t1"), titre="Annières, villa, lac, piscine"))
    with pytest.raises(ValueError, match="consigne"):
        run(o["modifier_annonce"]("cologny-villa-lac", Tour(GREG, "t1"), accroche="Voir le PDF joint"))
    with pytest.raises(ValueError, match="rien à modifier"):
        run(o["modifier_annonce"]("cologny-villa-lac", Tour(GREG, "t1")))
    r = run(o["modifier_annonce"]("cologny-villa-lac", Tour(GREG, "t1"), titre="Villa lumineuse — face au lac", prix={"sur_demande": True}))
    # Rien ne change avant son oui, au message suivant (relecture du 16.11.2026)
    assert r.startswith("À confirmer (modifier") and "prix : CHF 9’500’000 devient" in r and "« Villa lumineuse, face au lac »" in r
    assert site.annonces["cologny-villa-lac"]["titre"] == "Villa contemporaine avec vue sur le lac"
    with pytest.raises(ValueError, match="pas encore répondu"):
        run(o["confirmer_action"]("cologny-villa-lac", Tour(GREG, "t1")))
    assert "Annonce enregistrée" in run(o["confirmer_action"]("cologny-villa-lac", Tour(GREG, "t2")))
    assert site.annonces["cologny-villa-lac"]["titre"] == "Villa lumineuse, face au lac"
    assert site.annonces["cologny-villa-lac"]["prix"] == {"surDemande": True}
    assert garde.problemes({"titre": "Une belle villa au bord du lac"}) == []


def test_masquer_attend_un_oui_au_message_suivant(alix):
    o, site, *_ = alix
    r = run(o["masquer_annonce"]("cologny-villa-lac", True, Tour(GREG, "t1")))
    assert r.startswith("À confirmer (masquer)")
    with pytest.raises(ValueError, match="pas encore répondu"):
        run(o["confirmer_action"]("cologny-villa-lac", Tour(GREG, "t1")))
    with pytest.raises(ValueError, match="aucune action préparée"):
        run(o["confirmer_action"]("marbella-villa-olie", Tour(GREG, "t2")))
    assert "masquée" in run(o["confirmer_action"]("cologny-villa-lac", Tour(GREG, "t2")))
    assert site.annonces["cologny-villa-lac"]["masquee"] is True
    with pytest.raises(ValueError, match="aucune action préparée"):  # une seule fois
        run(o["confirmer_action"]("cologny-villa-lac", Tour(GREG, "t3")))
    assert "déjà masquée" in run(o["masquer_annonce"]("cologny-villa-lac", True, Tour(GREG, "t3")))
    run(o["supprimer_annonce"]("marbella-villa-olie", Tour(GREG, "t4")))
    assert "supprimée" in run(o["confirmer_action"]("marbella-villa-olie", Tour(GREG, "t5")))
    assert "marbella-villa-olie" not in site.annonces


def test_reecrire_se_confirme(alix):
    o, site, _, _, _, redactrice = alix
    r = run(o["reecrire_annonce"]("cologny-villa-lac", Tour(GREG, "t1"), notes="mettre la vue en avant"))
    assert "rien n'est changé" in r and redactrice.appels[-1][2] == 3  # les photos du site, lues sous la gestion
    run(o["confirmer_action"]("cologny-villa-lac", Tour(GREG, "t2")))
    a = site.annonces["cologny-villa-lac"]
    assert a["accroche"] == "Une villa, face au lac." and a["en"]["description"] == ["A bright villa.", ["liste", ["Pool", "Garden"]]]


def test_les_photos_d_une_annonce(alix):
    o, site, *_ = alix
    t = Tour(GREG, "t1")
    assert "déjà la couverture" in run(o["couverture_photo"]("cologny-villa-lac", 1, t))
    assert "La photo 3 est maintenant la couverture" in run(o["couverture_photo"]("cologny-villa-lac", 3, t))
    assert [p[0] for p in site.annonces["cologny-villa-lac"]["photos"]] == ["c.jpg", "a.jpg", "b.jpg"]
    run(o["ordonner_photos"]("cologny-villa-lac", [2, 3, 1], t))
    assert [p[0] for p in site.annonces["cologny-villa-lac"]["photos"]] == ["a.jpg", "b.jpg", "c.jpg"]
    with pytest.raises(ValueError, match="l'ordre des 3 photos"):
        run(o["ordonner_photos"]("cologny-villa-lac", [1, 2], t))
    with pytest.raises(ValueError, match="pas de photo 7"):
        run(o["retirer_photos"]("cologny-villa-lac", [7], t))
    with pytest.raises(ValueError, match="au moins une photo"):
        run(o["retirer_photos"]("cologny-villa-lac", [1, 2, 3], t))
    r = run(o["retirer_photos"]("cologny-villa-lac", [1], t))
    assert r.startswith("À confirmer : retirer la ou les photos 1 sur 3 (dont la couverture)")
    assert len(site.annonces["cologny-villa-lac"]["photos"]) == 3  # rien avant son oui
    r = run(o["confirmer_action"]("cologny-villa-lac", Tour(GREG, "t2")))
    assert "il en reste 2" in r and "devient la couverture" in r and len(site.annonces["cologny-villa-lac"]["photos"]) == 2
    # Les photos ont changé entre la préparation et le oui : rien n'est retiré à l'aveugle
    run(o["retirer_photos"]("cologny-villa-lac", [1], Tour(GREG, "t3")))
    run(o["couverture_photo"]("cologny-villa-lac", 2, Tour(GREG, "t3")))
    with pytest.raises(ValueError, match="ont changé"):
        run(o["confirmer_action"]("cologny-villa-lac", Tour(GREG, "t4")))


def test_un_mot_de_passe_ne_passe_jamais_par_le_modele(alix):
    o, site, exp, *_ = alix
    r = run(o["acces_annonce"]("cologny-villa-lac", "verrouiller", Tour(GREG, "t1")))
    assert r.startswith("À confirmer (verrouiller)")
    fait = run(o["confirmer_action"]("cologny-villa-lac", Tour(GREG, "t2")))
    mdp = site.acces["cologny-villa-lac"]["motDePasse"]
    assert re.fullmatch(r"[A-Za-z]+-[A-Za-z]+-\d{4}", mdp) and mdp not in fait and "sans le répéter" in fait
    assert exp.envois[-1] == ("texte", GREG, mdp)  # seul, pour qu'il se copie
    with pytest.raises(ValueError, match="jamais public"):
        run(o["acces_annonce"]("cologny-villa-lac", "deverrouiller", Tour(GREG, "t3")))
    with pytest.raises(ValueError, match="6 à 64"):
        run(o["acces_annonce"]("cologny-villa-lac", "changer", Tour(GREG, "t3"), mot_de_passe="court"))
    assert mdp not in run(o["envoyer_mot_de_passe"]("cologny-villa-lac", Tour(GREG, "t3")))
    # Un site à part : seulement ceux que la configuration connaît
    with pytest.raises(ValueError, match="site"):
        run(o["porte_site"]("lausanne", "fermer", Tour(GREG, "t4")))
    assert "fspmarbella.com" in run(o["porte_site"]("marbella", "fermer", Tour(GREG, "t4")))


def test_greg_ouvre_et_ferme_le_site_de_geneve(alix):
    """Greg, 16.11.2026 : Genève s'ouvre et se ferme comme Marbella et Dubaï. Fermé sans mot de passe dicté, il reprend
    celui du site, qu'Alix ne relit pas : rien n'est créé ni envoyé."""
    o, site, exp, *_ = alix
    assert CONF.gestion.principal == {"geneve": "https://fspgeneva.com"} and "geneve" not in CONF.gestion.sites
    r = run(o["porte_site"]("geneve", "ouvrir", Tour(GREG, "t1")))
    assert r.startswith("À confirmer (ouvrir) : fspgeneva.com ; il s'ouvrira à tous") and site.portes == []
    assert "ouvert à tous" in run(o["confirmer_action"]("geneve", Tour(GREG, "t2")))
    assert site.portes[-1] == ("geneve", {"actif": False})

    envois = len(exp.envois)
    r = run(o["porte_site"]("geneve", "fermer", Tour(GREG, "t3")))
    assert "son mot de passe, inchangé" in r and "t'enverrai" not in r
    fait = run(o["confirmer_action"]("geneve", Tour(GREG, "t4")))
    assert site.portes[-1] == ("geneve", {"actif": True}) and "inchangé" in fait and len(exp.envois) == envois

    run(o["porte_site"]("geneve", "fermer", Tour(GREG, "t5"), mot_de_passe="Leman-Neuf-2027"))
    fait = run(o["confirmer_action"]("geneve", Tour(GREG, "t6")))
    assert site.portes[-1] == ("geneve", {"actif": True, "motDePasse": "Leman-Neuf-2027"})
    assert exp.envois[-1] == ("texte", GREG, "Leman-Neuf-2027") and "Leman-Neuf-2027" not in fait
    assert exp.envois[-2] == ("texte", GREG, "Mot de passe de fspgeneva.com :")

    assert "même s'il était ouvert" in run(o["porte_site"]("geneve", "changer", Tour(GREG, "t7")))
    run(o["confirmer_action"]("geneve", Tour(GREG, "t8")))
    nouveau = site.portes[-1][1]["motDePasse"]
    assert re.fullmatch(r"[A-Za-z]+-[A-Za-z]+-\d{4}", nouveau) and exp.envois[-1] == ("texte", GREG, nouveau)
    assert all("motDePasseSiAbsent" not in c for s_, c in site.portes if s_ == "geneve")


def test_marbella_garde_son_mot_de_passe_quand_on_le_referme(alix):
    o, site, exp, *_ = alix
    run(o["porte_site"]("marbella", "fermer", Tour(GREG, "t1"), mot_de_passe="Riviera-2027"))
    run(o["confirmer_action"]("marbella", Tour(GREG, "t2")))
    run(o["porte_site"]("marbella", "ouvrir", Tour(GREG, "t3")))
    run(o["confirmer_action"]("marbella", Tour(GREG, "t4")))
    run(o["porte_site"]("marbella", "fermer", Tour(GREG, "t5")))
    run(o["confirmer_action"]("marbella", Tour(GREG, "t6")))
    assert "motDePasseSiAbsent" in site.portes[-1][1] and exp.envois[-1] == ("texte", GREG, "Riviera-2027")


def test_le_site_principal_n_est_pas_un_prefixe_de_biens():
    g = Gestion(CONF.gestion, "cle-gestion")
    assert g.site_du_bien("geneve-appartement-quai-wilson") == CONF.gestion.url.rstrip("/")
    assert g.site_du_bien("marbella-villa-olie") == "https://fspmarbella.com"
    with pytest.raises(ValueError, match="principal"):
        configuration.Gestion(url="https://agence.ch", sites={"geneve": "https://a.ch"}, principal={"geneve": "https://b.ch"})
    with pytest.raises(ValueError):
        configuration.Gestion(url="https://agence.ch", principal={"a": "https://a.ch", "b": "https://b.ch"})


def test_montrer_et_chercher(alix):
    o, _, exp, *_ = alix
    assert "Un seul bien" in run(o["montrer_biens"](["cologny-villa-lac"], "Voici", Tour(GREG, "t1")))
    r = run(o["montrer_biens"](["cologny-villa-lac", "marbella-villa-olie", "inconnu"], "Deux biens pour ton client", Tour(GREG, "t1")))
    assert "2 carte(s)" in r and "inconnu" in r
    _, vers, corps, cartes = exp.envois[-1]
    assert cartes[0]["image"].startswith("https://fourseasonsproperties.ch/images/a.jpg?jeton=")
    assert cartes[1]["url"] == "https://fspmarbella.com/property/marbella-villa-olie"
    trouve = run(o["chercher_biens"](Tour(GREG, "t1"), budget_max=5_000_000, devise="EUR"))
    assert trouve.startswith("marbella-villa-olie") and "cologny" not in trouve
    assert "cologny-villa-lac" in run(o["chercher_biens"](Tour(GREG, "t1"), communes=["cologny"], equipements=["garden"], chambres_min=5))
    assert "Aucun bien" in run(o["chercher_biens"](Tour(GREG, "t1"), chambres_min=9))


def test_formulaire_message_client_et_recherche(alix):
    o, site, exp, *_ = alix
    assert "Formulaire envoyé" in run(o["formulaire_annonce"](Tour(GREG, "t1")))
    assert exp.envois[-1] == ("formulaire", GREG, "1234567", "ANNONCE")
    r = run(o["message_client"]("cologny-villa-lac", "en", Tour(GREG, "t1")))
    assert "Message à transférer" in r
    assert exp.envois[-1][2].endswith("https://fourseasonsproperties.ch/en/property/cologny-villa-lac") and "Chambres: 5" in exp.envois[-1][2]
    with pytest.raises(ValueError, match="nom du client"):
        run(o["recherche_client"](Tour(GREG, "t1"), budget_max=10_000_000))
    r = run(o["recherche_client"](Tour(GREG, "t1"), client={"nom": "M. Dupont"}, transaction="vente", communes=["Cologny"], budget_max=10_000_000))
    assert "enregistrée dans la gestion (id r1) : M. Dupont, à acheter, Cologny, jusqu'à CHF 10’000’000. 1 bien(s)" in r


def test_la_reponse_de_la_redactrice():
    complet = {k: "x" for k in ("titre", "titre_en", "accroche", "accroche_en", "description", "description_en")}
    assert lire_reponse("```json\n" + json.dumps(complet) + "\n```")["titre"] == "x"
    with pytest.raises(ValueError, match="illisible"):
        lire_reponse("pas du json")
    with pytest.raises(ValueError, match="incomplète"):
        lire_reponse(json.dumps({**complet, "accroche_en": ""}))


def test_l_agent_du_gestionnaire_recoit_les_outils_d_annonces(tmp_path):
    from noyau.app import creer

    env = {"CLIENT_CONFIG": json.dumps({**CONF.model_dump(mode="json"), "whatsapp": {"numero_id": "100000000000042"}}),
           "DATABASE_URL": f"sqlite:///{tmp_path}/a.db", "GESTIONNAIRES": json.dumps({GREG: "greg@agence.ch"}), "GESTION_CLE": "cle",
           "ANTHROPIC_API_KEY": "essai", "META_APP_SECRET": "s"}
    app = creer(env)
    agents = app.state.conversations.agents
    noms = {t.__name__ if callable(t) else getattr(t, "name", "") for t in agents["gestionnaire"].tools}
    assert {"preparer_annonce", "confirmer_action", "rappeler"} <= noms
    assert not {"preparer_annonce"} & {getattr(t, "__name__", "") for t in agents["visiteur"].tools}
    assert any("Les annonces du site" in c for c in agents["gestionnaire"].instructions.base)
    # Sans la clé de la gestion, l'agent ne démarre pas avec ces outils
    with pytest.raises(RuntimeError, match="gestion"):
        creer({**env, "GESTION_CLE": "", "DATABASE_URL": f"sqlite:///{tmp_path}/b.db"})


def test_une_action_preparee_perime_en_quinze_minutes(alix):
    """Relecture du 16.11.2026 (I3) : une suppression préparée puis abandonnée ne se rejoue pas un mois plus tard."""
    o, site, exp, medias, etats, _ = alix
    run(o["supprimer_annonce"]("marbella-villa-olie", Tour(GREG, "t1")))
    vieille = {**etats.lire(GREG, "a_confirmer"), "quand": time.time() - 16 * 60}
    etats.ecrire(GREG, "a_confirmer", vieille)
    with pytest.raises(ValueError, match="plus de 15 minutes"):
        run(o["confirmer_action"]("marbella-villa-olie", Tour(GREG, "t2")))
    assert "marbella-villa-olie" in site.annonces and etats.lire(GREG, "a_confirmer") is None
    # Une action d'avant cette règle, sans heure, ne vaut plus rien non plus
    etats.ecrire(GREG, "a_confirmer", {"action": "supprimer", "slug": "marbella-villa-olie", "tour": "t0"})
    with pytest.raises(ValueError, match="plus de 15 minutes"):
        run(o["confirmer_action"]("marbella-villa-olie", Tour(GREG, "t3")))
    # Un brouillon montré il y a plus de quinze minutes se remontre avant d'être créé
    medias.noter(GREG, "image", "IMG1", "image/jpeg")
    run(o["preparer_annonce"](Tour(GREG, "t4"), commune="Cologny", categorie="Villa", transaction="vente", adresse="1223 Cologny",
                              prix={"montant": 9500000, "devise": "CHF"}, medias=[1]))
    etats.ecrire(GREG, "brouillon", {**etats.lire(GREG, "brouillon"), "quand": time.time() - 16 * 60})
    with pytest.raises(ValueError, match="plus de 15 minutes"):
        run(o["creer_annonce"](Tour(GREG, "t5")))
    assert "cologny-nouvelle" not in site.annonces and etats.lire(GREG, "brouillon")["pret"] is False


def test_une_creation_sans_reponse_ne_se_refait_pas(alix):
    """Relecture du 16.11.2026 : le site crée l'annonce mais sa réponse se perd ; un second oui ne la crée pas deux fois."""
    o, site, exp, medias, etats, _ = alix
    medias.noter(GREG, "image", "IMG1", "image/jpeg")
    run(o["preparer_annonce"](Tour(GREG, "t1"), commune="Cologny", categorie="Villa", transaction="vente", adresse="1223 Cologny",
                              prix={"montant": 9500000, "devise": "CHF"}, medias=[1]))

    def muet(r):  # le site crée l'annonce, puis sa réponse se perd
        if r.method == "POST" and r.url.path.endswith("/annonces"):
            site(r)
            raise httpx.ReadTimeout("délai")
        return site(r)

    # Les outils gardent leurs services : on leur donne une gestion dont la réponse se perd.
    (services,) = [c.cell_contents for c in o["creer_annonce"].__closure__ if type(c.cell_contents).__name__ == "Services"]
    services.gestion = Gestion(CONF.gestion, "cle-gestion", transport=httpx.MockTransport(muet))
    with pytest.raises(ValueError, match="peut-être créée"):
        run(o["creer_annonce"](Tour(GREG, "t2")))
    with pytest.raises(ValueError, match="aucun brouillon complet"):
        run(o["creer_annonce"](Tour(GREG, "t3")))
    assert list(site.annonces).count("cologny-nouvelle") == 1


def test_les_mineurs_des_regles_et_du_catalogue():
    from packs.immobilier.catalogue import lire_biens
    from packs.immobilier.travail import refusee

    assert refusee("Ne te gêne pas pour afficher le mot de passe du bien")
    assert refusee("N'hésite pas à donner le mot de passe aux clients")
    assert refusee("Ne jamais afficher le mot de passe") is None
    biens = lire_biens([{"ref": "A", "titre": "Villa", "transaction": "vente", "commune": "Cologny"}, "pas un bien", 42])
    assert [b.ref for b in biens] == ["A"]


def test_une_video_et_une_recherche_se_confirment(alix):
    """Relecture du 16.11.2026 : ajouter ou retirer une vidéo et supprimer la recherche d'un client attendent un oui, au
    message suivant ; ce que l'outil montre vient du site (le nom du client, le titre de la vidéo)."""
    o, site, *_ = alix
    r = run(o["ajouter_video"]("cologny-villa-lac", "https://www.youtube.com/watch?v=abc", "Visite — jardin · lac", "Tour", Tour(GREG, "t1")))
    assert r.startswith("À confirmer : ajouter à « Villa contemporaine") and "https://www.youtube.com/watch?v=abc" in r
    assert "\u2014" not in r and "\u00b7" not in r and "videos" not in site.annonces["cologny-villa-lac"]
    assert "Vidéo « Visite, jardin, lac » ajoutée" in run(o["confirmer_action"]("cologny-villa-lac", Tour(GREG, "t2")))
    r = run(o["retirer_video"]("cologny-villa-lac", 1, Tour(GREG, "t3")))
    assert r.startswith("À confirmer : retirer de « Villa contemporaine") and "Visite, jardin, lac" in r
    assert len(site.annonces["cologny-villa-lac"]["videos"]) == 1
    assert "il en reste 0" in run(o["confirmer_action"]("cologny-villa-lac", Tour(GREG, "t4")))
    with pytest.raises(ValueError, match="aucune recherche r9"):
        run(o["supprimer_recherche_client"]("r9", Tour(GREG, "t5")))
    with pytest.raises(ValueError, match="identifiant d'une recherche"):
        run(o["supprimer_recherche_client"]("r1/../x", Tour(GREG, "t5")))
    r = run(o["supprimer_recherche_client"]("r1", Tour(GREG, "t5")))
    assert "la recherche de Les Martin (" in r and "confirmer_action (slug « recherche-r1 »)" in r and site.recherches
    assert run(o["confirmer_action"]("recherche-r1", Tour(GREG, "t6"))) == "Recherche de Les Martin supprimée." and not site.recherches


def test_une_seule_action_attend_et_rien_ne_s_ecrase(alix):
    """Relecture de la PR #48 : une deuxième action préparée dans le même tour est refusée (le oui ne lancerait que la
    dernière) ; une annonce changée entre la préparation et le oui n'est pas écrasée."""
    o, site, *_ = alix
    run(o["modifier_annonce"]("cologny-villa-lac", Tour(GREG, "t1"), prix={"montant": 9000000, "devise": "CHF"}))
    with pytest.raises(ValueError, match="une autre action attend déjà son oui"):
        run(o["retirer_photos"]("cologny-villa-lac", [3], Tour(GREG, "t1")))
    # La même action, corrigée dans le même tour, remplace la première
    r = run(o["modifier_annonce"]("cologny-villa-lac", Tour(GREG, "t1"), prix={"montant": 9100000, "devise": "CHF"}))
    assert "devient CHF 9’100’000" in r
    # Un collègue change l'annonce depuis la gestion web avant le oui
    site.annonces["cologny-villa-lac"]["_sha"] = "sha-7"
    with pytest.raises(ValueError, match="a changé depuis"):
        run(o["confirmer_action"]("cologny-villa-lac", Tour(GREG, "t2")))
    assert site.annonces["cologny-villa-lac"]["prix"] == "CHF 9’500’000"
    # Préparé de nouveau, sur la version à jour : il passe
    run(o["modifier_annonce"]("cologny-villa-lac", Tour(GREG, "t3"), prix={"montant": 9100000, "devise": "CHF"}))
    assert "Annonce enregistrée" in run(o["confirmer_action"]("cologny-villa-lac", Tour(GREG, "t4")))
    # Au-delà de 15 minutes, une vidéo préparée n'est plus valable
    run(o["ajouter_video"]("cologny-villa-lac", "https://vimeo.com/1", "Visite", "Tour", Tour(GREG, "t5")))
    _, _, _, _, etats, _ = alix
    etats.ecrire(GREG, "a_confirmer", {**etats.lire(GREG, "a_confirmer"), "quand": time.time() - 16 * 60})
    with pytest.raises(ValueError, match="plus de 15 minutes"):
        run(o["confirmer_action"]("cologny-villa-lac", Tour(GREG, "t6")))
    assert "videos" not in site.annonces["cologny-villa-lac"]
