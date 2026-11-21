"""Lot 11 : le catalogue des 283 agents d'agency-agents, en modèles prêts à l'emploi."""

import importlib.util
import re
import shutil
from collections import Counter
from pathlib import Path

import pytest
from test_gabarits import atelier  # noqa: F401 (fixture)
from test_lot5 import MEGGA, jeton_client

from atelier import gabarits, regles
from atelier.regles import Refus
from noyau import config as configuration

CATALOGUE = gabarits.CATALOGUE_DIR
RACINE = Path(__file__).resolve().parent.parent
COMMIT = "8ae6164602c95ca78828b148b9052460ee426885"
# Les catégories d'agency-agents au 20.11.2026 et leur nombre d'agents (283 en tout).
PAR_CATEGORIE = {"engineering": 66, "specialized": 59, "marketing": 37, "game-development": 21, "gis": 13, "security": 12,
                 "design": 10, "testing": 9, "sales": 9, "project-management": 7, "paid-media": 7, "support": 6,
                 "spatial-computing": 6, "product": 6, "academic": 6, "finance": 5, "healthcare": 3, "research": 1}
SANTE = {"healthcare-clinical-evidence-agent", "healthcare-innovation-strategist", "healthcare-sovereign-health-systems-agent",
         "healthcare-aging-parent-care-companion", "healthcare-customer-service", "healthcare-marketing-compliance",
         "medical-billing-coding-specialist"}
JURIDIQUE = {"legal-billing-time-tracking", "legal-client-intake", "legal-document-review", "support-legal-compliance-checker",
             "data-privacy-officer", "healthcare-marketing-compliance", "finance-tax-strategist", "study-abroad-advisor"}
ADAPTES = {"security-penetration-tester", "security-blockchain-security-auditor", "security-architect",
           "security-appsec-engineer", "security-cloud-security-architect", "security-threat-detection-engineer",
           "security-threat-intelligence-analyst"}


def socle(nom: str) -> str:
    return (CATALOGUE / nom).read_text(encoding="utf-8").strip()


def script():
    spec = importlib.util.spec_from_file_location("catalogue_agency_agents", RACINE / "scripts" / "catalogue_agency_agents.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_les_283_agents_sont_installes_par_categorie():
    assert len(gabarits.CATALOGUE) == 283
    assert Counter(g["categorie"] for g in gabarits.CATALOGUE.values()) == PAR_CATEGORIE
    assert list(gabarits.MODELES)[:2] == list(gabarits.GABARITS)   # les gabarits écrits dans le code d'abord, inchangés
    assert not set(gabarits.GABARITS) & set(gabarits.CATALOGUE)
    for ident, g in gabarits.CATALOGUE.items():
        s = g["source"]
        assert s["licence"] == "MIT" and s["commit"] == COMMIT and s["depot"].endswith("/agency-agents"), ident
        assert len(s["chemins"]) == 1 and s["chemins"][0].startswith(g["categorie"] + "/"), ident
        assert Path(s["chemins"][0]).stem == ident, ident
    assert (gabarits.ICI / "LICENCE-agency-agents.txt").read_text(encoding="utf-8").startswith("MIT License")


def test_chaque_modele_du_catalogue_est_pret_a_l_emploi():
    """Un client créé d'après n'importe quel modèle du catalogue est valide et prêt à mettre en service."""
    for ident, g in gabarits.CATALOGUE.items():
        conf = configuration.lire(gabarits.nouvelle_config(ident, {"id": "essai", "entreprise": "Essai", "zone": "suisse"}, "Lea"))
        assert regles.manques(conf) == [], ident
        assert conf.metier == "general" and conf.outils == () and conf.roles is None, ident
        assert regles.consignes_de_gabarit(conf.consignes), ident   # reconnues comme celles d'un modèle, pas du sur-mesure
        for texte in (conf.consignes, g["titre"], g["description"]):
            assert not re.search(r"[\u2014\u2013\u00b7]", texte), ident


def test_les_consignes_sont_le_socle_les_garde_fous_puis_le_role():
    for ident, g in gabarits.CATALOGUE.items():
        consignes = g["reglages"]["consignes"]
        attendu = "\n\n".join([socle("_catalogue.md"), *(socle(f"_{x}.md") for x in g["garde_fous"])])
        assert consignes.startswith(attendu + "\n\n") and len(consignes) <= 8000, ident
        assert len(consignes) > len(attendu) + 500, ident   # le rôle de la source est bien là
        assert "avis médical" in consignes and "avis juridique" in consignes, ident   # pour tous, par le socle


def test_les_socles_ne_promettent_que_ce_que_l_agent_sait_faire():
    """Sur main, l'agent n'a ni le transfert à un humain (lot 9.3) ni les demandes notées (lot 9.4) : les socles et
    les rôles ne nomment aucun de ces outils, et ne promettent pas de transmettre une question à l'équipe."""
    for g in gabarits.CATALOGUE.values():
        c = g["reglages"]["consignes"]
        assert "passer_la_main" not in c and "enregistrer_lead" not in c
    for nom in ("_catalogue.md", "_securite.md", "_sante.md", "_juridique.md"):
        assert "transmettre" not in socle(nom), nom


def test_les_douze_agents_de_securite_passent_la_regle_defensive():
    securite = {k: g for k, g in gabarits.CATALOGUE.items() if g["categorie"] == "security"}
    assert len(securite) == 12
    regle = socle("_securite.md")
    assert "strictement défensif" in regle and "logiciel malveillant" in regle and "contourner une protection" in regle
    for ident, g in securite.items():
        assert "securite" in g["garde_fous"] and regle in g["reglages"]["consignes"], ident
        role = g["reglages"]["consignes"].split(regle, 1)[1]
        assert not re.search(r"red team|purple team|proof.of.concept|proof of exploitability|underground|dark web|"
                             r"malware sample|infrastructure scanning|social engineering", role, re.I), ident
    # Ceux qui dépassaient la règle sont adaptés, et le disent dans leur fichier.
    assert {k for k in securite if "adapte:" in (CATALOGUE / "security" / f"{k}.md").read_text(encoding="utf-8")} == ADAPTES
    pentest = securite["security-penetration-tester"]
    assert pentest["titre"] == "Penetration Test Coordinator" and "never run an attack" in pentest["reglages"]["consignes"]
    # Hors de la catégorie security, aucun modèle n'a besoin de la règle : le socle interdit déjà d'attaquer ou de contourner.
    assert "contourner une protection" in socle("_catalogue.md")


def test_sante_et_juridique_sans_avis_et_la_sante_pas_aux_etats_unis():
    assert {k for k, g in gabarits.CATALOGUE.items() if "sante" in g["garde_fous"]} == SANTE
    assert {k for k, g in gabarits.CATALOGUE.items() if "juridique" in g["garde_fous"]} == JURIDIQUE
    assert "144" in socle("_sante.md") and "jamais d'avis médical" in socle("_sante.md")
    assert "jamais d'avis juridique" in socle("_juridique.md") and "délai" in socle("_juridique.md")
    assert set(gabarits.PAS_AUX_ETATS_UNIS) == SANTE
    usa = {"id": "essai", "entreprise": "Essai", "zone": "etats-unis"}
    for ident in SANTE:
        with pytest.raises(Refus, match="zone États-Unis"):
            gabarits.nouvelle_config(ident, usa, "Lea")
        with pytest.raises(Refus, match="zone États-Unis"):
            gabarits.reglages_pour(ident, {"zone": "etats-unis"})
    for ident in JURIDIQUE - SANTE:   # sans numéro d'urgence suisse : ouverts aux États-Unis
        configuration.lire(gabarits.nouvelle_config(ident, usa, "Lea"))


def test_le_catalogue_se_choisit_dans_l_atelier(atelier):  # noqa: F811
    t = atelier
    ids = [g["id"] for g in t.get("/atelier/gabarits", headers=MEGGA).json()["gabarits"]]
    assert len(ids) == 285 and ids[:2] == list(gabarits.GABARITS)
    corps = {"gabarit": "security-architect", "nom_agent": "Lea",
             "client": {"id": "cabinet-x", "entreprise": "Cabinet X", "zone": "europe"}}
    r = t.post("/atelier/clients", headers=MEGGA, json=corps)
    assert r.status_code == 201, r.text
    config = t.get("/atelier/clients/cabinet-x/versions/1", headers=MEGGA).json()["config"]
    assert config["consignes"] == gabarits.CATALOGUE["security-architect"]["reglages"]["consignes"]
    client = jeton_client(t, "cabinet-x")   # le client passe lui-même à un autre modèle du catalogue, l'essaie et le met en service
    r = t.post("/atelier/clients/cabinet-x/gabarit", headers=client, json={"gabarit": "marketing-seo-specialist"})
    assert r.status_code == 201 and r.json()["manques"] == [], r.text
    assert r.json()["config"]["consignes"] == gabarits.CATALOGUE["marketing-seo-specialist"]["reglages"]["consignes"]
    assert t.post("/atelier/clients/cabinet-x/versions/2/essai", headers=client, json={"message": "Bonjour"}).status_code == 200
    assert t.post("/atelier/clients/cabinet-x/versions/2/activer", headers=client).status_code == 200


def copie(dossier: Path) -> Path:
    shutil.copytree(CATALOGUE, dossier / "catalogue")
    return dossier / "catalogue"


@pytest.mark.parametrize("avant, apres, message", [
    ("garde_fous: [securite]", "garde_fous: []", "toujours le garde-fou securite"),
    ("categorie: security", "categorie: marketing", "celle de son dossier"),
    ("licence: MIT", "licence: GPL", "licence MIT"),
    ("garde_fous: [securite]", "garde_fous: [securite, magie]", "garde_fous"),
])
def test_un_modele_mal_forme_arrete_le_chargement(tmp_path, avant, apres, message):
    dossier = copie(tmp_path)
    f = dossier / "security" / "security-architect.md"
    f.write_text(f.read_text(encoding="utf-8").replace(avant, apres, 1), encoding="utf-8")
    with pytest.raises(ValueError, match=message) as e:
        gabarits.charger_catalogue(dossier)
    assert "security/security-architect.md" in str(e.value)


def test_un_nom_deja_pris_ou_des_consignes_trop_longues_arretent_le_chargement(tmp_path):
    dossier = copie(tmp_path)
    with pytest.raises(ValueError, match="déjà pris"):
        gabarits.charger_catalogue(dossier, pris={"security-architect": {}})
    f = dossier / "security" / "security-architect.md"
    _, entete, _ = f.read_text(encoding="utf-8").split("---\n", 2)
    f.write_text("---\n" + entete + "---\n" + "x" * 6000 + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="8000"):
        gabarits.charger_catalogue(dossier)


def test_le_script_nettoie_raccourcit_et_adapte():
    s = script()
    assert s.COMMIT == COMMIT and s.CATEGORIES == gabarits.CATEGORIES
    texte = "# Titre\n\nIntro \u2014 courte.\n\n## \U0001F9E0 Your Identity\n\n- a\n\n```bash\nrm -rf /\n```\n\n### Vide\n\n---\n\n## Learning & Memory\n\n- b"
    propre = s.nettoyer(texte)
    assert "rm -rf" not in propre and "\u2014" not in propre and "\U0001F9E0" not in propre and "### Vide" not in propre
    assert "## Your Identity" in propre and "---" not in propre
    court = s.raccourcir(propre, 2000)
    assert "Learning" not in court and court.index("Intro") < court.index("## Your Identity")
    long = "\n\n".join(f"## Section {i}\n\n" + "\n".join(f"- point {i}.{j} " + "x" * 60 for j in range(30)) for i in range(10))
    assert len(s.raccourcir("Intro.\n\n" + long, 3000)) <= 3000
    with pytest.raises(SystemExit, match="trouvé 0 fois"):
        s.adapter("security-architect", "une source qui a changé")
    assert s.INTERDITS_SECURITE.search("run atomic red team tests")
