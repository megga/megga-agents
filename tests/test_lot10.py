"""Lot 10 : les modèles d'accueil par métier."""

import asyncio
import json
import shutil
import time
from pathlib import Path

import pytest
import yaml
from sqlalchemy import update
from test_lot6_pilote import MEGGA, activer, canal, nouvelle_version, releve_signe  # noqa: F401 (canal : fixture)
from test_lot9_4 import dns_public  # noqa: F401 (fixture : les webhooks des essais résolvent vers une adresse publique)

from atelier import gabarits, regles
from atelier.regles import Refus
from noyau import config as configuration
from noyau import banc, connecteurs, stockage, version
from noyau.app import creer
from pilote import service as pilote_service
from test_lot9_3 import Contexte, FaussesConversations
from test_lot9_4 import fini, recepteur

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


class Equipe(FaussesConversations):
    """Les conversations, avec des gestionnaires joignables (tous, par défaut) ou pas (noyau/tour.py, peut_ecrire)."""

    def __init__(self, joignables=None):
        super().__init__()
        self.joignables = joignables

    async def peut_ecrire(self, personne, usage, langue=""):
        return self.joignables is None or personne in self.joignables


def leads(url, gestionnaires=("+41790000099", "+41790000098"), joignables=None, **k):
    l = connecteurs.Leads(stockage.Leads(url), agent="Alix", gestionnaires=gestionnaires, **k)
    l.conversations = Equipe(joignables)
    return l


def vieillir(url, secondes):
    """Les demandes déjà notées, comme si elles l'avaient été `secondes` plus tôt."""
    m = stockage.Leads(url)
    with m._e.begin() as c:
        c.execute(update(m._t).values(cree=m._t.c.cree - secondes))


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
    for personne, l in (("+41790000001", leads(url, gestionnaires=())), ("+41790000002", leads(url, alerte=False))):
        outil = l.outils()[0]
        assert asyncio.run(outil("Une table pour 4", 3, Contexte(personne))).endswith("enregistrée pour l'équipe.")
        assert asyncio.run(outil("Une table pour 4 à 20 h", 3, Contexte(personne))).endswith("complétée.")   # aucune alerte partie
        assert l.conversations.apres == []


def test_une_demande_completee_dans_les_30_minutes_reste_la_meme(url):
    """Relecture finale (I2) : la même personne qui complète sa demande ne crée ni une seconde demande ni une seconde alerte ;
    le webhook reçoit la fiche complétée sous le même numéro."""
    recus, transport = recepteur([200])
    l = leads(url, webhook="https://crm.exemple.ch/leads", transport=transport)
    outil = l.outils()[0]

    async def essai():
        r1 = await outil("Le service de ma Clio", 3, Contexte("+41790000001"), nom="M. Favre")
        await fini(l)
        r2 = await outil("Le service de ma Clio, avec les pneus d'hiver", 2, Contexte("+41790000001"), delai="jeudi")
        await fini(l)
        return r1, r2

    r1, r2 = asyncio.run(essai())
    assert r1 == "Demande 1 enregistrée ; l'équipe est prévenue."
    assert r2 == "Demande 1 complétée ; l'équipe a déjà été prévenue."
    assert len(l.conversations.apres) == 2   # une alerte par gestionnaire, pour la première seulement
    [lead] = stockage.Leads(url).lister()
    assert (lead["id"], lead["besoin"], lead["score"], lead["delai"], lead["nom"]) == (
        1, "Le service de ma Clio, avec les pneus d'hiver", 3, "jeudi", "M. Favre")   # le score garde le plus haut
    envois = [json.loads(r.content)["lead"] for r in recus]
    assert [e["id"] for e in envois] == [1, 1] and (envois[1]["delai"], envois[1]["nom"], envois[1]["score"]) == ("jeudi", "M. Favre", 3)
    assert lead["etat"] == "envoye"


def test_apres_30_minutes_ou_pour_une_autre_personne_une_nouvelle_demande(url):
    l = leads(url)
    outil = l.outils()[0]
    assert asyncio.run(outil("Une table pour 4", 3, Contexte("+41790000001"))) == "Demande 1 enregistrée ; l'équipe est prévenue."
    assert asyncio.run(outil("Une chambre double", 3, Contexte("+41790000002"))) == "Demande 2 enregistrée ; l'équipe est prévenue."
    vieillir(url, 31 * 60)
    assert asyncio.run(outil("Une table pour 6", 4, Contexte("+41790000001"))) == "Demande 3 enregistrée ; l'équipe est prévenue."
    assert len(l.conversations.apres) == 6   # trois demandes, deux gestionnaires
    assert [d["besoin"] for d in stockage.Leads(url).lister()] == ["Une table pour 6", "Une chambre double", "Une table pour 4"]


def test_l_equipe_est_prevenue_seulement_si_un_gestionnaire_est_joignable(url):
    """Relecture finale (M2) : sinon l'alerte attend quand même, et l'outil le dit autrement."""
    l = leads(url, joignables={"+41790000098"})
    assert asyncio.run(l.outils()[0]("Une table pour 4", 3, Contexte("+41790000001"))) == "Demande 1 enregistrée ; l'équipe est prévenue."
    l = leads(url, joignables=set())
    outil = l.outils()[0]
    assert asyncio.run(outil("Une table pour 2", 3, Contexte("+41790000002"))) == (
        "Demande 2 enregistrée ; l'équipe la verra dès que possible.")
    assert len(l.conversations.apres) == 2   # l'alerte attend le prochain message des gestionnaires
    assert asyncio.run(outil("Une table pour 2, en terrasse", 3, Contexte("+41790000002"))) == "Demande 2 complétée."


def test_joignable_d_apres_les_conversations(url):
    """Le vrai contrôle (noyau/tour.py, peut_ecrire) : les 24 heures du gestionnaire, ou un modèle Meta « lead » ou « message » ;
    sans WhatsApp, personne."""
    from noyau.tour import Conversations
    from test_app import FauxAgent, FauxExpediteur

    contacts = stockage.Contacts(url)

    def essai(personne, **reglages):
        conf = configuration.Config.model_validate({**CONF, **reglages})
        l = connecteurs.Leads(stockage.Leads(url), agent="Alix", gestionnaires=("+41790000099",))
        l.conversations = Conversations(conf, FauxAgent(), FauxExpediteur(), contacts=contacts, differes=stockage.Differes(url))
        return asyncio.run(l.outils()[0]("Une table pour 4", 3, Contexte(personne)))

    prevenue, plus_tard = "l'équipe est prévenue.", "l'équipe la verra dès que possible."
    assert essai("+41790000001").endswith(plus_tard)   # hors des 24 heures, sans modèle Meta
    assert essai("+41790000002", modeles_meta={"lead": {"nom": "fsp_lead"}}).endswith(prevenue)
    assert essai("+41790000003", modeles_meta={"message": {"nom": "fsp_message"}}).endswith(prevenue)
    assert essai("+41790000004", whatsapp=None, modeles_meta={"lead": {"nom": "fsp_lead"}}).endswith(plus_tard)
    contacts.noter("+41790000099", time.time() - 3600)   # le gestionnaire a écrit il y a une heure
    assert essai("+41790000005").endswith(prevenue)
    assert essai("+41790000006", whatsapp=None).endswith(plus_tard)


def test_un_webhook_et_une_alerte_l_alerte_l_emporte(url):
    """Relecture finale (M7) : la fiche part au webhook, l'alerte est programmée, et l'outil dit que l'équipe est prévenue."""
    recus, transport = recepteur([200])
    l = leads(url, webhook="https://crm.exemple.ch/leads", transport=transport)

    async def essai():
        r = await l.outils()[0]("Une chambre double du 3 au 5 mars", 4, Contexte("+41790000001"))
        await fini(l)
        return r

    assert asyncio.run(essai()) == "Demande 1 enregistrée ; l'équipe est prévenue."
    assert [json.loads(r.content)["lead"]["id"] for r in recus] == [1] and len(l.conversations.apres) == 2


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
    assert list(gabarits.GABARITS) == ["generaliste", "immobilier", "sante", "hotellerie", "juridique", "commerce", "fiduciaire", "garage"]
    assert [g["reglages"]["metier"] for g in gabarits.GABARITS.values()] == list(configuration.NOMS_METIERS)
    socle = (ICI_GABARITS / "_accueil.md").read_text(encoding="utf-8").strip()
    for id_, g in gabarits.GABARITS.items():
        r = g["reglages"]
        assert r["consignes"].startswith(socle) and len(r["consignes"]) <= 8000
        assert r["outils"] == ["connaissances", "leads"] and r["transfert"] is True and r["mention_ia"] is True
        assert r["voix"] == {"voix": gabarits.VOIX_PAR_DEFAUT}
    assert gabarits.GABARITS["generaliste"]["source"]["licence"] == "MIT"
    assert [k for k, g in gabarits.GABARITS.items() if g["source"] is None] == ["fiduciaire", "garage"]   # écrits sans source
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


def test_chaque_modele_a_le_role_gestionnaire_sans_lequel_le_transfert_est_inerte():
    """Le transfert passe la main à l'équipe et n'agit qu'avec le rôle gestionnaire (relecture du lot 9.3) : chaque modèle règle
    le gestionnaire et le visiteur, avec les outils de l'agent. Le pack immobilier les suit ; des rôles déjà réglés restent."""
    for g in gabarits.lister():
        conf = configuration.lire(gabarits.nouvelle_config(g["id"], {"id": "essai", "entreprise": "Essai", "zone": "suisse"}, "Lea"))
        assert conf.transfert and set(conf.les_roles()) == {"gestionnaire", "visiteur"}, g["id"]
        assert all(r.outils == ("rappels", "connaissances", "leads") for r in conf.les_roles().values()), g["id"]
    immo = gabarits.reglages_pour("immobilier", {"zone": "suisse", "catalogue": "https://agence.example/flux.json"})
    assert immo["roles"]["visiteur"]["outils"] == ["rappels", "immobilier", "connaissances", "leads"]
    assert gabarits.GABARITS["immobilier"]["reglages"]["roles"]["visiteur"]["outils"] == ["rappels", "connaissances", "leads"]
    assert "roles" not in gabarits.reglages_pour("garage", {"zone": "suisse", "roles": {"gestionnaire": {}, "partenaire": {}}})


def test_l_immobilier_garde_son_pack_et_le_garage_le_retire():
    assert gabarits.reglages_pour("immobilier", {"catalogue": "demo:megga-estates"})["outils"] == ["immobilier", "connaissances", "leads"]
    base = {**CONF, "metier": "immobilier", "outils": ["immobilier"], "catalogue": "demo:megga-estates"}
    r = gabarits.reglages_pour("generaliste", base)   # un autre métier : le pack immobilier part
    assert r["outils"] == ["connaissances", "leads"]
    configuration.lire({**base, **r})
    r = gabarits.reglages_pour("garage", base)
    assert r["outils"] == ["connaissances", "leads"]
    configuration.lire({**base, **r})


ETATS_UNIS = {"id": "acme", "entreprise": "Acme", "zone": "etats-unis"}


@pytest.mark.parametrize("modele", ["sante", "garage"])
def test_sante_et_garage_pas_encore_aux_etats_unis(modele):
    """Relecture finale (I7) : leurs numéros d'urgence (144, 112) sont ceux de la Suisse et de l'Europe."""
    for appel in (lambda: gabarits.nouvelle_config(modele, ETATS_UNIS, "Lea"),
                  lambda: gabarits.reglages_pour(modele, {**CONF, "zone": "etats-unis"})):
        with pytest.raises(Refus) as e:
            appel()
        assert (e.value.statut, e.value.message) == (400, "Ce modèle n'est pas encore disponible pour la zone États-Unis.")
    for zone in ("suisse", "europe", "client"):
        assert gabarits.nouvelle_config(modele, {**ETATS_UNIS, "zone": zone}, "Lea")["metier"] == modele
        assert gabarits.reglages_pour(modele, {**CONF, "zone": zone})["metier"] == modele


def test_les_six_autres_restent_ouverts_aux_etats_unis():
    autres = [g for g in gabarits.GABARITS if g not in ("sante", "garage")]
    assert len(autres) == 6
    for g in autres:
        conf = configuration.Config.model_validate(gabarits.nouvelle_config(g, ETATS_UNIS, "Lea"))
        assert conf.zone == "etats-unis" and "le 112 en Suisse et en Europe" in conf.consignes
        assert gabarits.reglages_pour(g, {**CONF, "zone": "etats-unis"})["consignes"] == conf.consignes


def test_l_atelier_refuse_sante_aux_etats_unis(tmp_path):
    from fastapi.testclient import TestClient

    from atelier.app import creer as creer_atelier
    from test_lot5 import ADMIN, FaussePorte, FauxModele

    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db", "ESSAIS_DIR": str(tmp_path / "e")},
                                 porte=FaussePorte(), principal_essai=FauxModele()))
    client = {**ETATS_UNIS, "numero_id": "100000000000042"}
    r = t.post("/atelier/clients", headers=MEGGA, json={"gabarit": "sante", "client": client, "nom_agent": "Lea"})
    assert (r.status_code, r.json()["erreur"]) == (400, "Ce modèle n'est pas encore disponible pour la zone États-Unis.")
    assert t.post("/atelier/clients", headers=MEGGA, json={"gabarit": "generaliste", "client": client, "nom_agent": "Lea"}).status_code == 201
    r = t.post("/atelier/clients/acme/gabarit", headers=MEGGA, json={"gabarit": "garage"})
    assert (r.status_code, r.json()["erreur"]) == (400, "Ce modèle n'est pas encore disponible pour la zone États-Unis.")
    assert t.post("/atelier/clients/acme/gabarit", headers=MEGGA, json={"gabarit": "hotellerie"}).status_code == 201


def test_le_banc_range_les_documents_et_offre_les_leads(tmp_path):
    from test_lot5 import FauxModele
    from test_lot9_2 import FauxVectoriseur

    conf = configuration.lire({**CONF, "outils": ["connaissances", "leads"]})
    agent = banc.agent_d_essai({}, principal=FauxModele(), vectoriseur=FauxVectoriseur())(
        conf, tmp_path / "cas", [{"titre": "Horaires", "texte": "Ouvert du lundi au vendredi, de 8 h à 18 h."}])
    noms = {getattr(o, "__name__", getattr(o, "name", "")) for o in agent.tools}
    assert {"chercher_dans_les_documents", "enregistrer_lead"} <= noms
    assert [d["titre"] for d in stockage.Connaissances(f"sqlite:///{tmp_path / 'cas'}/banc.db").documents()] == ["Horaires"]


def test_avec_des_roles_le_banc_garde_les_documents_et_les_leads_du_visiteur(tmp_path):
    """Le banc essaie l'agent du visiteur (lot 9.6) : ses documents et ses demandes restent, le banc les fournit."""
    from test_lot5 import FauxModele
    from test_lot9_2 import FauxVectoriseur

    roles = {"visiteur": {"consignes": "Tu sers les visiteurs.", "outils": ["rappels", "connaissances", "leads"]}}
    conf = configuration.lire({**CONF, "outils": ["connaissances", "leads"], "roles": roles})
    agent = banc.agent_d_essai({}, principal=FauxModele(), vectoriseur=FauxVectoriseur())(
        conf, tmp_path / "cas", [{"titre": "Horaires", "texte": "Ouvert du lundi au vendredi, de 8 h à 18 h."}])
    assert agent.id == f"{conf.id}-visiteur"
    noms = {getattr(o, "__name__", getattr(o, "name", "")) for o in agent.tools}
    assert {"chercher_dans_les_documents", "enregistrer_lead"} <= noms


def configuration_du_banc(dossier, metier):
    chemin = dossier / f"banc-{metier}.yaml"
    conf = gabarits.nouvelle_config(metier, {"id": f"banc-{metier}", "entreprise": "Essai", "zone": "europe"}, "Lea")
    chemin.write_text(yaml.safe_dump(conf, allow_unicode=True), encoding="utf-8")
    return str(chemin)


def test_le_banc_s_arrete_avant_de_jouer_sans_le_modele_de_recherche(tmp_path, monkeypatch, capsys):
    """Relecture finale (I3) : des cas rangent des documents ; sans le modèle de recherche, rien n'est joué (ni payé)."""
    joues = []

    async def faux_passer(conf, construire_agent, juger, k=3, cas=None):
        joues.append(conf.metier)
        return {"k": k, "cas": 0, "tenus": 0, "score": 1, "pass_1": 1, "incomplet": None, "resultats": []}

    monkeypatch.setattr(banc, "passer", faux_passer)
    monkeypatch.setenv("MEGGA_MODELE_DIR", str(tmp_path / "pas-de-modele"))
    assert banc.principal([configuration_du_banc(tmp_path, "sante"), "1"]) == 2 and joues == []
    sortie = capsys.readouterr().out
    assert all(m in sortie for m in ("modèle de recherche", "pas-de-modele", "socle/modele.py", "MEGGA_MODELE_DIR", "Rien n'a été joué"))
    assert banc.principal([configuration_du_banc(tmp_path, "generaliste"), "1"]) == 0 and joues == ["general"]   # aucun document


def test_le_banc_partage_un_seul_modele_de_recherche(tmp_path, monkeypatch):
    modele = tmp_path / "modele"
    modele.mkdir()
    (modele / "model.onnx").write_bytes(b"")
    (modele / "tokenizer.json").write_text("{}")
    monkeypatch.setenv("MEGGA_MODELE_DIR", str(modele))
    vus = []

    def faux_agent_d_essai(cles, principal=None, vectoriseur=None):
        vus.append(vectoriseur)
        return lambda *a: None

    async def faux_passer(conf, construire_agent, juger, k=3, cas=None):
        return {"k": k, "cas": 0, "tenus": 0, "score": 1, "pass_1": 1, "incomplet": None, "resultats": []}

    monkeypatch.setattr(banc, "agent_d_essai", faux_agent_d_essai)
    monkeypatch.setattr(banc, "passer", faux_passer)
    assert banc.principal([configuration_du_banc(tmp_path, "garage"), "1"]) == 0
    [v] = vus
    assert v is not None and v.dossier == modele   # un seul, chargé une fois pour tous les cas


# Les cas du banc de chaque nouveau métier


@pytest.mark.parametrize("metier", NOUVEAUX)
def test_chaque_nouveau_metier_a_son_modele_et_ses_cas(metier):
    assert metier in {g["metier"] for g in gabarits.lister()}
    propres = [c for c in banc.scenarios(metier) if c["id"][0] == metier[0].upper()]
    assert len(propres) >= 3


def test_les_cas_de_la_relecture_finale():
    cas = {c["id"]: c for m in ("sante", "garage") for c in banc.scenarios(m)}
    assert "ne laisse pas entendre qu'il faut attendre le cabinet" in [c["nom"] for c in cas["S01"]["criteres"]]
    assert {"S06", "G05"} <= set(cas)
    assert banc.automatique(next(c for c in cas["G05"]["criteres"] if "motifs" in c), {"reponses": ["Appelez le 112."]})
    g04 = next(c for c in cas["G04"]["criteres"] if "motifs" in c)
    for numero in ("021 555 01 23", "021/555/01/23", "021-555-01-23", "021.555.01.23"):
        assert banc.automatique(g04, {"reponses": [f"Le dépannage : {numero}."]})
