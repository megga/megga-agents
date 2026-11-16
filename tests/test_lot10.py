"""Lot 10 : les modèles d'accueil par métier."""

import asyncio
import json
import shutil
from pathlib import Path

import pytest
from test_lot6_pilote import MEGGA, activer, canal, nouvelle_version, releve_signe  # noqa: F401 (canal : fixture)

from atelier import gabarits, regles
from noyau import config as configuration
from noyau import connecteurs, stockage, version
from noyau.app import creer
from pilote import service as pilote_service
from test_lot9_3 import Contexte, FaussesConversations

NOUVEAUX = ("sante", "hotellerie", "juridique", "commerce", "fiduciaire", "garage")
CONF = configuration.lire("clients/exemple.yaml").model_dump(mode="json")
ICI_GABARITS = Path(gabarits.__file__).parent


def test_les_huit_metiers():
    assert configuration.NOMS_METIERS == ("general", "immobilier", *NOUVEAUX)
    assert configuration.METIERS_D_AVANT == ("general", "immobilier")
    for m in NOUVEAUX:
        assert configuration.METIERS[m] == configuration.OUTILS_DES_ROLES[m] == configuration.GROUPES_DU_NOYAU
        assert configuration.lire({**CONF, "metier": m, "outils": ["connaissances", "leads"]}).metier == m
        with pytest.raises(Exception):  # le pack immobilier ne va qu'au métier immobilier
            configuration.lire({**CONF, "metier": m, "outils": ["immobilier"], "catalogue": "demo:megga-estates"})


def test_la_carte_donne_les_metiers():
    assert version.carte()["metiers"] == list(configuration.NOMS_METIERS)
    assert "metiers" in pilote_service.SANTE  # le pilote le remonte


def test_un_metier_que_l_image_ne_connait_pas():
    from atelier.app import metier_inconnu

    assert metier_inconnu({"version": "0.3.0", "schema": 2}, "sante")  # sans metiers : une image d'avant
    assert not metier_inconnu({"version": "0.3.0", "schema": 2}, "immobilier")
    assert not metier_inconnu({"version": "0.4.0", "metiers": ["general", "sante"]}, "sante")
    assert metier_inconnu({"version": "0.4.0", "metiers": ["general"]}, "garage")
    for inconnu in (None, {}, {"ok": False, "erreur": "injoignable"}):
        assert not metier_inconnu(inconnu, "sante")  # on ne sait pas : l'installation jugera
    for illisible in ("sante", ["sante", 3], None):
        assert metier_inconnu({"version": "0.4.0", "metiers": illisible}, "sante")


def test_le_releve_garde_les_metiers(canal):
    c = canal
    agent = {"ok": True, "version": "0.4.0", "schema": 2, "metiers": ["general", "sante"]}
    assert releve_signe(c, {"pilotage": "suivi", "etat": {"agent": agent}}).status_code == 200
    gardes = c.t.get("/atelier/clients/exemple/installation", headers=MEGGA).json()
    assert gardes["installation"]["agent"]["metiers"] == ["general", "sante"]


def test_l_activation_refuse_un_metier_inconnu(canal):
    c = canal
    v = nouvelle_version(c.t, metier="sante")
    avant = {"ok": True, "version": "0.3.0", "schema": 2}  # une image d'avant : pas de metiers
    assert releve_signe(c, {"pilotage": "suivi", "etat": {"agent": avant}}).status_code == 200
    r = activer(c.t, v)
    assert r.status_code == 409 and "ne connaît pas le métier sante" in r.json()["erreur"], r.text
    recente = {**avant, "version": "0.4.0", "metiers": ["general", "immobilier", "sante"]}
    c.horloge.t += 10
    assert releve_signe(c, {"pilotage": "suivi", "etat": {"agent": recente}}).status_code == 200
    assert activer(c.t, v).status_code == 200


# L'équipe prévenue d'une demande


@pytest.fixture
def url(tmp_path):
    return f"sqlite:///{tmp_path}/client.db"


def leads(url, gestionnaires=("+41790000099", "+41790000098"), **k):
    l = connecteurs.Leads(stockage.Leads(url), agent="Alix", gestionnaires=gestionnaires, **k)
    l.conversations = FaussesConversations()
    return l


def test_une_demande_previent_l_equipe_apres_le_tour(url):
    l = leads(url)
    r = asyncio.run(l.outils()[0]("Un rendez-vous pour le service de ma Clio", 4, Contexte("+41790000001"), delai="jeudi", nom="M. Favre"))
    assert r == "Demande 1 enregistrée ; l'équipe est prévenue."
    assert len(l.conversations.apres) == 2 and l.conversations.envois == []   # rien avant la fin du tour
    for f in l.conversations.apres:
        asyncio.run(f())
    assert [(qui, usage) for qui, _, usage in l.conversations.envois] == [("+41790000099", "lead"), ("+41790000098", "lead")]
    texte = l.conversations.envois[0][1][0]["texte"]
    assert all(m in texte for m in ("Clio", "jeudi", "M. Favre", "+41790000001", "4/5"))


def test_sans_equipe_ou_alerte_coupee_rien_ne_part(url):
    for l in (leads(url, gestionnaires=()), leads(url, alerte=False)):
        assert asyncio.run(l.outils()[0]("Une table pour 4", 3, Contexte("+41790000001"))).endswith("enregistrée pour l'équipe.")
        assert l.conversations.apres == []


def test_l_alerte_masque_les_secrets_nomme_l_api_et_saute_l_auteur(url):
    l = leads(url)
    asyncio.run(l.outils()[0]("Devis, ma clé sk-abcdefghijklmnopqrstuvwxyz", 2, Contexte("api:dossier:42")))
    for f in l.conversations.apres:
        asyncio.run(f())
    texte = l.conversations.envois[0][1][0]["texte"]
    assert "sk-" not in texte and "[masqué]" in texte and "api:dossier:42" in texte and "+api" not in texte
    l2 = leads(url)
    asyncio.run(l2.outils()[0]("Une villa", 5, Contexte("+41790000099")))   # un gestionnaire note lui-même
    for f in l2.conversations.apres:
        asyncio.run(f())
    assert [qui for qui, _, _ in l2.conversations.envois] == ["+41790000098"]


def test_le_client_coupe_l_alerte_dans_sa_configuration():
    assert configuration.lire({**CONF, "outils": ["leads"], "leads": {"alerte": False}}).leads.alerte is False
    assert configuration.lire({**CONF, "outils": ["leads"]}).leads is None   # sans leads : l'alerte vaut vrai


def test_l_app_branche_les_conversations(url):
    from test_app import FauxAgent, FauxExpediteur

    l = connecteurs.Leads(stockage.Leads(url))
    app = creer({"CLIENT_CONFIG": json.dumps({**CONF, "outils": ["leads"]}), "DATABASE_URL": url, "INTERNE_TOKEN": "interne"},
                agent=FauxAgent(), expediteur=FauxExpediteur(), leads=l)
    assert l.conversations is app.state.conversations


# Les modèles en fichiers


def test_les_modeles_se_chargent_de_leurs_fichiers():
    assert list(gabarits.GABARITS)[:2] == ["generaliste", "immobilier"]
    socle = (ICI_GABARITS / "_accueil.md").read_text(encoding="utf-8").strip()
    for id_, g in gabarits.GABARITS.items():
        r = g["reglages"]
        assert r["consignes"].startswith(socle) and len(r["consignes"]) <= 8000
        assert r["outils"] == ["connaissances", "leads"] and r["transfert"] is True and r["mention_ia"] is True
        assert r["voix"] == {"voix": gabarits.VOIX_PAR_DEFAUT}
    assert gabarits.GABARITS["generaliste"]["source"]["licence"] == "MIT"
    assert all("source" in g for g in gabarits.lister())


def copie_des_modeles(dossier):
    for f in ICI_GABARITS.glob("*.md"):
        shutil.copy(f, dossier / f.name)


def remplacer(texte: str, ligne: str) -> str:
    """Remplace la ligne d'un champ de l'en-tête, et la suite de sa valeur si elle tient sur plusieurs lignes."""
    cle, sortie, suite = ligne.split(":")[0] + ":", [], False
    for l in texte.splitlines():
        if suite and l.startswith(" "):
            continue
        suite = l.startswith(cle)
        sortie.append(ligne if suite else l)
    return "\n".join(sortie) + "\n"


@pytest.mark.parametrize("defaut, message", [
    ("metier: boulanger", "metier"), ("ordre: 2", "ordre"), ("ton: vif \u2014 et drôle", "tiret"),
    ("titre: ", "titre"), ("source: {depot: x, chemins: [a.md], commit: abc, licence: GPL}", "licence")])
def test_un_fichier_mal_forme_arrete_le_chargement(tmp_path, defaut, message):
    copie_des_modeles(tmp_path)
    f = tmp_path / "generaliste.md"
    f.write_text(remplacer(f.read_text(encoding="utf-8"), defaut), encoding="utf-8")   # ordre 2 : celui d'immobilier
    with pytest.raises(ValueError, match=message) as e:
        gabarits.charger(tmp_path)
    assert "generaliste.md" in str(e.value)   # le fichier fautif est nommé


def test_des_consignes_trop_longues_arretent_le_chargement(tmp_path):
    copie_des_modeles(tmp_path)
    f = tmp_path / "generaliste.md"
    _, entete, _ = f.read_text(encoding="utf-8").split("---\n", 2)
    f.write_text("---\n" + entete + "---\n" + "x" * 8000 + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="8000"):
        gabarits.charger(tmp_path)


def test_les_anciens_textes_restent_ceux_d_un_modele():
    anciens = json.loads((ICI_GABARITS / "anciens.json").read_text(encoding="utf-8"))
    assert set(anciens) == {"generaliste", "immobilier"}
    for texte in anciens.values():
        assert regles.consignes_de_gabarit(texte)
    for g in gabarits.GABARITS.values():
        assert regles.consignes_de_gabarit(g["reglages"]["consignes"])
    assert not regles.consignes_de_gabarit("Consignes sur mesure de MEGGA.")


def test_l_immobilier_garde_son_pack_et_le_garage_le_retire():
    assert gabarits.reglages_pour("immobilier", {"catalogue": "demo:megga-estates"})["outils"] == ["immobilier", "connaissances", "leads"]
    base = {**CONF, "metier": "immobilier", "outils": ["immobilier"], "catalogue": "demo:megga-estates"}
    r = gabarits.reglages_pour("generaliste", base)   # un autre métier : le pack immobilier part
    assert r["outils"] == ["connaissances", "leads"]
    configuration.lire({**base, **r})
    if "garage" not in gabarits.GABARITS:
        pytest.skip("le modèle garage vient à la tâche 7")
    r = gabarits.reglages_pour("garage", base)
    assert r["outils"] == ["connaissances", "leads"]
    configuration.lire({**base, **r})


def test_le_banc_range_les_documents_et_offre_les_leads(tmp_path):
    from test_lot5 import FauxModele
    from test_lot9_2 import FauxVectoriseur

    from noyau import banc

    conf = configuration.lire({**CONF, "outils": ["connaissances", "leads"]})
    agent = banc.agent_d_essai({}, principal=FauxModele(), vectoriseur=FauxVectoriseur())(
        conf, tmp_path / "cas", [{"titre": "Horaires", "texte": "Ouvert du lundi au vendredi, de 8 h à 18 h."}])
    noms = {getattr(o, "__name__", getattr(o, "name", "")) for o in agent.tools}
    assert {"chercher_dans_les_documents", "enregistrer_lead"} <= noms
    assert [d["titre"] for d in stockage.Connaissances(f"sqlite:///{tmp_path / 'cas'}/banc.db").documents()] == ["Horaires"]
