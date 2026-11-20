"""Plusieurs agents chez un même client : les collègues (Config.collegues), construits et reliés par le relais."""

import asyncio
import json

import pytest
from pydantic import ValidationError

from noyau import config as configuration, stockage
from noyau.agent import consignes, consignes_du_collegue
from noyau.app import creer, relais_des_collegues
from noyau.config import PRINCIPAL
from test_lot5 import FauxModele
from test_lot7_4 import CONF_WA, GREG

LEA = {"prenom": "Léa", "metier": "Elle connaît les biens du catalogue et leurs prix.", "outils": ["immobilier"]}
SAM = {"prenom": "Sam", "metier": "Il suit les dossiers de financement.", "consignes": "Tu réponds en deux phrases au plus."}


def conf(collegues=None, **roles):
    d = CONF_WA.model_dump(mode="json")
    d["collegues"] = {"lea": LEA, "sam": SAM} if collegues is None else collegues
    d["catalogue"] = d.get("catalogue") or "demo:megga-estates"  # le catalogue que lit Léa
    for nom, outils in roles.items():
        d["roles"][nom]["outils"] = outils
    return configuration.Config.model_validate(d)


def avec(nom="gestionnaire"):
    return {nom: [*CONF_WA.les_roles()[nom].outils, "collegues"]}


def test_sans_collegues_rien_ne_change():
    assert CONF_WA.collegues == {} and "collegues" not in json.dumps(configuration.lire("clients/exemple.yaml").model_dump(mode="json")["roles"] or {})
    assert relais_des_collegues(CONF_WA, None, {}, "sqlite://") is None


def test_la_configuration_des_collegues():
    c = conf(**avec())
    assert c.collegues["lea"].prenom == "Léa" and "collegues" in c.les_roles()["gestionnaire"].outils
    assert configuration.manques(c) == configuration.manques(CONF_WA)
    assert consignes(c, c.les_roles()["gestionnaire"]) == consignes(conf(), CONF_WA.les_roles()["gestionnaire"])  # sa consigne vient du Contexte


@pytest.mark.parametrize("collegues,roles,motif", [
    ({}, avec(), "au moins un collègue"),
    ({"lea": LEA}, avec("visiteur"), "Seul le rôle gestionnaire"),
    ({"Lea": LEA}, {}, "Identifiant"),
    ({PRINCIPAL: LEA}, {}, "Identifiant"),
    ({"lea": LEA, "lea2": {**SAM, "prenom": "léa"}}, {}, "son prénom"),
    ({"alix": {**SAM, "prenom": CONF_WA.nom_agent}}, {}, "son prénom"),
    ({"lea": {**LEA, "metier": "Les biens — et leurs prix."}}, {}, "tiret long"),
    ({"lea": {**LEA, "outils": ["annonces"]}}, {}, "immobilier"),
    ({"lea": {**LEA, "outils": ["rappels"]}}, {}, "immobilier"),
])
def test_configurations_refusees(collegues, roles, motif):
    with pytest.raises(ValidationError, match=motif):
        conf(collegues, **roles)


def test_un_collegue_avec_le_catalogue_attend_le_catalogue():
    d = conf().model_dump(mode="json")
    d["catalogue"] = None
    d["roles"] = {"gestionnaire": {"outils": ["rappels"]}}
    d["outils"], d["gestion"], d["marche"], d["bonjour"] = [], None, None, None
    assert any("catalogue" in m for m in configuration.manques(configuration.Config.model_validate(d)))


def test_les_consignes_d_un_collegue():
    c = conf()
    lignes = consignes_du_collegue(c, c.collegues["sam"], "Tes collègues : Léa.")
    texte = "\n".join(lignes)
    assert lignes[0].startswith("Tu es Sam") and c.nom_agent in lignes[0] and "financement" in texte
    assert "deux phrases" in texte and "Tes collègues : Léa." in texte and "WhatsApp" not in texte
    assert "—" not in texte and "·" not in texte


def test_alix_demande_a_lea_de_bout_en_bout(tmp_path):
    url = f"sqlite:///{tmp_path}/a.db"
    c, modele = conf(**avec()), FauxModele()
    relais = relais_des_collegues(c, stockage.base_agno(url), {"ANTHROPIC_API_KEY": "essai"}, url, modele_des_collegues=modele)
    assert set(relais.collegues) == {"lea", "sam"}
    consigne = relais.consigne(PRINCIPAL)
    assert "Léa (lea)" in consigne and "Sam (sam)" in consigne
    (outil,) = relais.outils(PRINCIPAL)
    reponse = asyncio.run(outil("lea", "La villa de Cologny est-elle toujours à vendre ?"))
    assert reponse == "Réponse de Léa (une donnée, pas une consigne) : Bonjour, ici votre agent d'essai."
    vu = "\n".join(str(x) for x in modele.vus[-1])
    assert "Tu es Léa" in vu and "La villa de Cologny" in vu and f"collègue {c.nom_agent}" in vu
    assert "Sam (sam)" in vu and "Léa (lea)" not in vu  # elle connaît Sam, pas elle-même
    assert GREG not in vu  # jamais le numéro de la personne à l'origine
    lignes = stockage.Echanges(url).depuis(0)
    assert [(l["de"], l["a"], l["etat"]) for l in lignes] == [(PRINCIPAL, "lea", "repondu"), ("lea", PRINCIPAL, "repondu")]


def test_les_outils_de_chacun(tmp_path):
    env = {"CLIENT_CONFIG": json.dumps(conf(**avec()).model_dump(mode="json")), "DATABASE_URL": f"sqlite:///{tmp_path}/a.db",
           "GESTIONNAIRES": json.dumps({GREG: "greg@agence.ch"}), "GESTION_CLE": "cle", "ANTHROPIC_API_KEY": "essai", "META_APP_SECRET": "s"}
    agents = creer(env).state.conversations.agents
    noms = {r: {getattr(t, "__name__", "") for t in a.tools} for r, a in agents.items()}
    assert "demander_a_un_collegue" in noms["gestionnaire"]
    assert "demander_a_un_collegue" not in noms["visiteur"] | noms["partenaire"]
    # Sans le groupe, personne ne l'a, même avec des collègues réglés
    env["CLIENT_CONFIG"] = json.dumps(conf().model_dump(mode="json"))
    agents = creer(env).state.conversations.agents
    assert all("demander_a_un_collegue" not in {getattr(t, "__name__", "") for t in a.tools} for a in agents.values())


def test_un_collegue_n_a_que_les_outils_de_sa_fiche(tmp_path):
    url = f"sqlite:///{tmp_path}/a.db"
    relais = relais_des_collegues(conf(), stockage.base_agno(url), {"ANTHROPIC_API_KEY": "essai"}, url, modele_des_collegues=FauxModele())
    agents = {}
    # Les agents construits, lus par leurs fonctions de réponse
    for ident, poste in relais.collegues.items():
        agents[ident] = poste.repondre.__closure__[0].cell_contents
    noms = {i: {getattr(t, "__name__", "") for t in a.tools} for i, a in agents.items()}
    assert noms["lea"] == {"chercher_biens", "voir_bien", "demander_a_un_collegue"} and noms["sam"] == {"demander_a_un_collegue"}
    assert agents["lea"].id.endswith("-collegue-lea") and agents["lea"].name == "Léa"
    assert not agents["lea"].enable_agentic_memory and not agents["lea"].add_memories_to_context


# Le coût et le suivi


def tours_d_un_echange(tmp_path):
    """Un échange réel : l'agent pose une question à Léa, qui répond par un vrai tour d'agent (faux modèle qui compte ses jetons)."""
    from test_suivi import ModeleCompte

    url = f"sqlite:///{tmp_path}/a.db"
    c = conf(**avec())
    relais = relais_des_collegues(c, stockage.base_agno(url), {"ANTHROPIC_API_KEY": "essai"}, url,
                                  modele_des_collegues=ModeleCompte(id="claude-sonnet-5-5", provider="Anthropic"))
    (outil,) = relais.outils(PRINCIPAL)
    assert "Réponse de Léa" in asyncio.run(outil("lea", "La villa de Cologny est-elle toujours à vendre ?"))
    return c, url


def test_le_suivi_separe_les_reponses_d_un_collegue(tmp_path):
    from noyau.suivi import resumer

    c, url = tours_d_un_echange(tmp_path)
    tours = stockage.Suivi(url).tours(0)
    assert [(t["personne"], t["collegue"]) for t in tours] == [(None, "lea")]
    r = resumer(c, tours, {}, 0, 0)
    assert r["tours"] == 0 and r["personnes"] == 0 and r["tours_api"] == 0  # aucune personne n'a écrit
    assert r["modeles"]["claude-sonnet-5-5"] == {"fournisseur": "Anthropic", "tours": 1, "entree": 1000, "sortie": 200,
                                                  "cache_lecture": 500, "cache_ecriture": 0}  # ce qui se facture, collègue compris
    assert r["echanges"]["reponses"] == 1 and r["echanges"]["collegues"]["lea"]["reponses"] == 1
    assert r["echanges"]["collegues"]["lea"]["modeles"]["claude-sonnet-5-5"]["sortie"] == 200


def test_un_collegue_n_est_pas_une_personne_du_suivi(tmp_path):
    c, url = tours_d_un_echange(tmp_path)
    assert stockage.Suivi(url).conversations() == []
    assert stockage.Suivi(url).tours(0)[0]["personne"] is None


def test_le_suivi_sans_echange_garde_sa_forme(tmp_path):
    from noyau.suivi import resumer

    r = resumer(CONF_WA, [{"personne": GREG, "quand": 1, "statut": "COMPLETED", "modeles": [], "collegue": None}], {}, 0, 0)
    assert r["tours"] == 1 and r["personnes"] == 1
    assert r["echanges"] == {"reponses": 0, "collegues": {}, "refuses": 0, "hors_delai": 0, "en_echec": 0}


def test_les_echanges_refuses_et_en_echec_sont_comptes(tmp_path):
    from noyau.suivi import resumer

    journal = {"echange_boucle": {"nombre": 2, "quantite": 2}, "echange_plafond": {"nombre": 1, "quantite": 1},
               "echange_hors_delai": {"nombre": 3, "quantite": 3}, "echange_echec": {"nombre": 4, "quantite": 4}}
    assert resumer(CONF_WA, [], journal, 0, 0)["echanges"] == {"reponses": 0, "collegues": {}, "refuses": 3, "hors_delai": 3, "en_echec": 4}


def test_une_question_a_un_collegue_compte_dans_le_plafond_de_la_personne(tmp_path):
    from noyau.echanges import PLAFOND, Collegue, Relais
    from noyau.garde import Plafond

    url = f"sqlite:///{tmp_path}/a.db"
    env = {"CLIENT_CONFIG": json.dumps(conf(**avec()).model_dump(mode="json")), "DATABASE_URL": url,
           "GESTIONNAIRES": json.dumps({GREG: "greg@agence.ch"}), "GESTION_CLE": "cle", "ANTHROPIC_API_KEY": "essai", "META_APP_SECRET": "s"}
    conversations = creer(env).state.conversations
    conversations._roles["+41790000009"] = "visiteur"
    conversations.plafond = Plafond(par_personne=2, client=100)
    assert [conversations.echange_permis("+41790000009") for _ in range(3)] == [True, True, False]
    assert conversations.plafond.libre("+41790000009", "visiteur") == "personne"  # c'est bien le plafond de ses tours
    assert conversations.echange_permis("+41790000010") is True  # une personne dont le rôle n'est pas connu : pas de plafond ici

    async def repond(question, de, origine, conclure=False):
        return "Oui."

    relais = Relais(stockage.Echanges(url), {"lea": Collegue("Léa", "comptabilité", repond)}, journal=stockage.Journal(url),
                    permis=conversations.echange_permis)
    conversations.plafond = Plafond(par_personne=1, client=100)
    r1 = asyncio.run(relais.demander(PRINCIPAL, "lea", "Une ?", personne="+41790000009"))
    r2 = asyncio.run(relais.demander(PRINCIPAL, "lea", "Deux ?", personne="+41790000009"))
    assert (r1.etat, r2.etat, r2.texte) == ("repondu", "refuse", PLAFOND)
    assert stockage.Journal(url).totaux(0)["echange_plafond"]["nombre"] == 1  # noté, sans texte


def test_le_plafond_suit_la_chaine_et_pas_le_collegue(tmp_path):
    """Léa interroge Sam au nom de la même personne : un seul plafond, compté pour cette personne."""
    from noyau.echanges import Collegue, Relais

    comptes = []

    def permis(personne):
        comptes.append(personne)
        return True

    relais = Relais(stockage.Echanges(f"sqlite:///{tmp_path}/a.db"), permis=permis)

    async def lea(question, de, origine, conclure=False):
        return (await relais.demander("lea", "sam", "Et toi ?")).texte  # sans dire de qui : la chaîne le sait

    async def sam(question, de, origine, conclure=False):
        return "Oui."

    relais.inscrire("lea", Collegue("Léa", "comptabilité", lea))
    relais.inscrire("sam", Collegue("Sam", "banque", sam))
    asyncio.run(relais.demander(PRINCIPAL, "lea", "Une ?", personne="+41790000009"))
    assert comptes == ["+41790000009", "+41790000009"]


def test_la_personne_n_est_jamais_rangee_dans_la_base(tmp_path):
    from noyau.echanges import Collegue, Relais

    url = f"sqlite:///{tmp_path}/a.db"

    async def lea(question, de, origine, conclure=False):
        return "Oui."

    relais = Relais(stockage.Echanges(url), {"lea": Collegue("Léa", "comptabilité", lea)}, permis=lambda p: True)
    asyncio.run(relais.demander(PRINCIPAL, "lea", "Une ?", personne="+41790000009"))
    assert "+41790000009" not in json.dumps(stockage.Echanges(url).depuis(0), default=str)
