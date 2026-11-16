"""Lot 7.7 : la parité et la bascule. La reprise des données d'Alix (un export produit par son vrai code, tests/donnees)."""

import json
import time

import pytest

from noyau import config as configuration, stockage
from packs.immobilier.reprise import reprendre
from test_lot6_api import base_neuve  # noqa: F401, F811 (la base d'essai, SQLite et Postgres)

CONF = configuration.lire("clients/four-seasons-properties.yaml")
GREG, MARC, SOPHIE = "+41791252627", "+41795550101", "+41795550303"
EXPORT = json.load(open("tests/donnees/export_alix.json", encoding="utf-8"))


def test_la_reprise_des_donnees_d_alix(base_neuve):  # noqa: F811
    url = base_neuve
    stockage.migrer(url)
    b = reprendre(EXPORT, url, CONF)
    assert b == {"partenaires": 2, "bloques": 1, "demandes": 2, "recherches": 1, "souvenirs": 2, "regles": 3, "fils": 1, "veilles": 1, "zones": 1,
                 "releves": 2}
    # Les partenaires (le retiré ne revient pas), leur règle, le bloqué
    p = stockage.Partenaires(url)
    assert [(x["personne"], x["nom"], x["agence"], x["regle"]) for x in p.lister()] == [
        (SOPHIE, "Sophie Bernard", "", ""), (MARC, "Marc Dupont", "Riviera Immobilier", "lignes")]
    assert stockage.Bloques(url).bloque("+41780000000")
    # Les demandes, leurs choix, la suite d'une recherche gardée
    r = stockage.Reseau(url)
    attente = {d["partenaire"]: d for d in r.en_attente(GREG, 0)}
    attend = attente[SOPHIE]
    assert set(attente) == {MARC, SOPHIE} and attend["partenaire"] == SOPHIE and attend["suite"] and attend["propositions"][0]["bien"]["reference"] == "G8LR2DW8"
    marc = r.de_partenaire(MARC, 0)[0]
    assert [(x["reference"], x["choix"], x["etat"]) for x in marc["propositions"]] == [("G8LR2DW8", "lignes", "livree"), ("MBOL1E00", None, None)]
    assert marc["nom"] == "Marc Dupont (Riviera Immobilier)"
    (rech,) = r.recherches()
    assert rech["criteres"]["vue"] == "lac" and rech["criteres"]["communes"] == ["Cologny"] and "vueLac" not in rech["criteres"]
    # La mémoire, les règles, le fil, les veilles, les zones de Greg
    souvenirs = sorted(m.memory for m in stockage.base_agno(url).get_user_memories(user_id=GREG))
    assert souvenirs == ["Greg préfère les vocaux le matin", "Les Martin cherchent une villa à Cologny, 5 chambres, budget CHF 10 M"]
    assert [(x["portee"], x["qui"]) for x in stockage.Regles(url).de(GREG)] == [("marbella", None), ("principal", None), ("personne", "Marc Dupont")]
    assert stockage.Etats(url).lire(GREG, "fil")["texte"] == "Greg attend la plaquette de la villa Olie."
    v = stockage.Veilles(url)
    (veille,) = v.de(GREG, "veille")  # celle qui est finie ne revient pas
    assert veille["donnees"]["pour"] == "les Martin" and veille["donnees"]["fin"] > time.time() and veille["donnees"]["vus"]
    assert v.de(GREG, "zone")[0]["donnees"]["derniere"] == {"n": 6, "mediane": 28000}
    releves = stockage.Carnet(url).releves()
    assert {x["nature"] for x in releves} == {"avis", "annonce"} and all(x["date"] < 10**11 for x in releves)  # en secondes
    # Une seule fois ; --encore ne double rien
    with pytest.raises(RuntimeError, match="déjà été reprise"):
        reprendre(EXPORT, url, CONF)
    encore = reprendre(EXPORT, url, CONF, encore=True)
    assert all(n == 0 for k, n in encore.items() if k != "fils"), encore  # rien de nouveau, rien de doublé
    assert len(stockage.Partenaires(url).lister()) == 2 and len(stockage.Carnet(url).releves()) == 2
    assert len(stockage.base_agno(url).get_user_memories(user_id=GREG)) == 2 and len(stockage.Veilles(url).de(GREG)) == 2
    with pytest.raises(ValueError, match="format"):
        reprendre({"format": 2}, url, CONF, encore=True)


# Le banc de parité : les cas neutres et leur notation (sans modèle)


def test_les_cas_neutres():
    doc = json.load(open("parite/cas.json", encoding="utf-8"))
    assert len(doc["cas"]) == 36 and len({c["id"] for c in doc["cas"]}) == 36
    for c in doc["cas"]:
        assert c["etapes"] and c["criteres"] and c["faits"], c["id"]
        for e in c["etapes"]:
            assert e.get("avancer") or (e["de"] in ("greg", c.get("visiteur")) and e["texte"]), c["id"]


def test_la_notation_automatique():
    from parite import noter

    greg, visiteur = "+41791252627", "+41780000006"
    trace = {"journal": [{"de": "Greg", "a": "agent", "numero": greg, "texte": "Retiens Keller"},
                         {"de": "agent", "a": greg, "numero": greg, "texte": "C'est noté."},
                         {"de": "agent", "a": greg, "numero": greg, "texte": "Keller cherche un attique, 4 millions, 3 chambres."},
                         {"de": "agent", "a": visiteur, "numero": visiteur, "texte": "Greg vous rappelle — bientôt."}],
             "outils": [{"nom": "update_user_memory", "entree": {"task": "M. Keller cherche un attique"}},
                        {"nom": "noter_marche", "entree": {"nature": "avis"}}, {"nom": "rappeler", "entree": {"quand": f"{noter.jeudi_prochain()}T09:00"}}],
             "resultats": ["Règle 1 apprise. Confirme-la en une ligne."], "gestion": [{"methode": "PUT", "chemin": "/api/gestion/annonces/marbella-villa-sienna"}],
             "marque": 2}
    t = noter.champs(trace, greg, visiteur)
    assert t["dernier_pour_greg"].startswith("Keller") and t["apres_avance"].startswith("Keller") and t["pour_visiteur"].startswith("Greg")
    a = lambda c: noter.automatique(c, trace, t)  # noqa: E731
    assert a({"outil": ["retenir", "update_user_memory"], "entree_motif": "(?i)keller"})
    assert a({"outil": ["rappeler"], "entree_motif": "{jeudi}T09:00"})
    assert not a({"outil": ["noter_marche"], "entree": {"nature": "vente"}}) and a({"outil": ["noter_marche"], "entree": {"nature": "avis"}})
    assert not a({"outil": ["noter_marche"], "min": 2})
    assert not a({"et": [{"outil": ["noter_marche"]}, {"outil": ["comparer_bien"]}]})
    assert a({"pas_outil": ["apprendre_regle"]}) and not a({"pas_outil": ["rappeler"]})
    assert not a({"gestion_aucune": {"methode_pas": "GET", "chemin": "annonces/marbella-villa-sienna"}}) and a({"gestion_aucune": {"methode": "DELETE"}})
    assert not a({"resultat_pas": r"^Règle \d+ apprise"})
    assert a({"champ": "dernier_pour_greg", "motifs": ["(?i)attique", r"\b4\b", r"\b3\b"]})
    assert not a(noter.TYPO)  # le tiret long envoyé au visiteur
    assert a({"champ": "pour_greg", "pas_motif": "15550000004"})


def test_variables_des_modeles_sur_une_ligne():
    from noyau.whatsapp import en_ligne

    assert en_ligne("Prix en hausse.\nLe suivi s'arrête.\t  Fin") == "Prix en hausse. Le suivi s'arrête. Fin"


def test_le_repli_en_anglais_pour_qui_parle_anglais(tmp_path):
    from test_lot7_4 import CONF_WA, VISITEUR, FauxExp, run
    from test_lot7_6 import FauxAgent

    from noyau.tour import Conversations

    url = f"sqlite:///{tmp_path}/m.db"
    conf = configuration.Config.model_validate({**CONF_WA.model_dump(mode="json"), "modeles_meta": {
        "message": {"nom": "fsp_socle_message"}, "message_en": {"nom": "fsp_socle_message", "langue": "en"}}})
    exp, langues = FauxExp(), []

    async def modele(vers, nom, langue, variables):
        langues.append((nom, langue))

    exp.modele = modele
    c = Conversations(conf, FauxAgent(), exp, contacts=stockage.Contacts(url), differes=stockage.Differes(url), rappels=stockage.Rappels(url))
    assert run(c.envoyer_de_soi_meme(VISITEUR, [{"texte": "Here is the villa."}], "reponse_visiteur", ["Here is"], "en")) == "modele"
    assert run(c.envoyer_de_soi_meme("+41790000099", [{"texte": "Voici la villa."}], "reponse_visiteur", ["Voici"])) == "modele"
    assert langues == [("fsp_socle_message", "en"), ("fsp_socle_message", "fr")]
