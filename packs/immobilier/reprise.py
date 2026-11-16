"""La reprise des données d'un agent Alix sur Cloudflare (sa route GET /export, en lecture seule) dans la base d'un
client du socle (lot 7.7).

  DATABASE_URL=… CLIENT_CONFIG_FILE=clients/<client>.yaml python -m packs.immobilier.reprise export.json [--encore]

Ce qui se reprend : les partenaires (et leur règle), les numéros bloqués, les demandes des partenaires et leurs choix,
les recherches gardées ; pour chaque gestionnaire, ses souvenirs (la mémoire d'Agno), ses règles de travail, son fil,
ses veilles et ses zones suivies ; le carnet du marché. Une seule fois par base (une marque dans megga_reglages) ;
`--encore` pour la refaire (rien de ce qui existe n'est doublé : les identifiants sont gardés). Les dates de l'export
sont en millisecondes, celles du socle en secondes. Rien ne s'affiche des données elles-mêmes, seulement les comptes ; ils
ne comptent que ce qui est nouveau. Refaite, la reprise ne double rien : chaque souvenir, veille ou zone garde un identifiant
tiré de l'export, et un relevé du carnet déjà présent (le même lien, ou la même nature, le même lieu, le même prix et la
même date) n'est pas noté de nouveau.
"""

from __future__ import annotations

import json
import sys
import time

from noyau import stockage

from .carnet import plat as carnets_plat

FORMAT = 1
MARQUE = "reprise_alix"
SEMAINE = 7 * 86400
FREQUENCES = {"quotidienne": 86400, "hebdomadaire": SEMAINE}


def secondes(ms) -> float | None:
    return float(ms) / 1000 if isinstance(ms, (int, float)) and ms else None


def criteres(c: dict) -> dict:
    """Les critères d'une recherche gardée, dans les noms du socle (packs/immobilier/reseau.py)."""
    c = dict(c or {})
    vue = "lac" if c.pop("vueLac", False) else c.get("vue")
    return {**{k: c.get(k) for k in ("reference", "transaction", "type", "budget", "devise", "periode", "chambres", "surface")},
            "communes": c.get("communes") or [], "vue": vue}


def portee(p: str, sites) -> str:
    """Le site principal d'Alix s'appelait par son pays ; les autres sont des préfixes de sites du socle."""
    if p in ("partout", "personne") or p in sites:
        return p
    return "principal"


def reprendre(donnees: dict, url: str, conf, maintenant: float | None = None, encore: bool = False) -> dict:
    """Reprend l'export dans la base `url` du client `conf` ; rend les comptes de ce qui a été repris."""
    maintenant = time.time() if maintenant is None else maintenant
    if not isinstance(donnees, dict) or donnees.get("format") != FORMAT:
        raise ValueError(f"un export d'Alix au format {FORMAT}")
    reglages = stockage.Reglages(url)
    if reglages.lire(MARQUE) and not encore:
        raise RuntimeError("cette base a déjà été reprise (--encore pour la refaire)")
    sites = tuple(conf.gestion.sites) if conf.gestion else ()
    b = {k: 0 for k in ("partenaires", "bloques", "demandes", "recherches", "souvenirs", "regles", "fils", "veilles", "zones", "releves")}
    registre = donnees.get("registre") or {}
    partenaires, bloques, reseau = stockage.Partenaires(url), stockage.Bloques(url), stockage.Reseau(url)
    actifs = {}
    for p in registre.get("partenaires") or []:
        if p.get("retire"):
            continue
        actifs[p["numero"]] = p
        b["partenaires"] += partenaires.inscrire(p["numero"], p.get("nom") or "", p.get("par") or "", secondes(p.get("ajoute")),
                                                 p.get("famille") or "", p.get("agence") or "")
    for r in registre.get("regles") or []:
        if r.get("numero") in actifs and r.get("regle") in stockage.REGLES_PARTENAIRE:
            partenaires.regle(r["numero"], r["regle"])
    for x in registre.get("bloques") or []:
        b["bloques"] += bloques.bloquer(x["numero"], x.get("par") or "", secondes(x.get("depuis")), x.get("nom") or "")
    suites = {s["demande"]: {"recherche": s["recherche"], "depuis": secondes(s.get("depuis"))} for s in registre.get("suites") or []}
    props: dict[str, list] = {}
    for x in registre.get("propositions") or []:
        bien = x.get("bien")
        props.setdefault(x["demande"], []).append({**x, "bien": json.loads(bien) if isinstance(bien, str) else (bien or {}),
                                                   "decide": secondes(x.get("decide"))})
    for d in registre.get("demandes") or []:
        cree = secondes(d.get("cree")) or maintenant
        if maintenant - cree > stockage.GARDE_DEMANDE:
            continue  # plus d'un mois : elle se serait effacée
        p = actifs.get(d["partenaire"]) or {}
        nom = f"{p.get('nom') or d['partenaire']}{' (' + p['agence'] + ')' if p.get('agence') else ''}"
        b["demandes"] += reseau.reprendre_demande({"id": d["id"], "partenaire": d["partenaire"], "nom": nom, "gestionnaire": d["courtier"],
                                                   "recherche": d.get("recherche"), "cree": cree, "statut": d.get("statut")},
                                                  sorted(props.get(d["id"], []), key=lambda x: x["rang"]), suites.get(d["id"]))
    for r in registre.get("recherches") or []:
        if r.get("close") or r.get("partenaire") not in actifs:
            continue
        c = json.loads(r["criteres"]) if isinstance(r.get("criteres"), str) else r.get("criteres") or {}
        b["recherches"] += reseau.reprendre_recherche({"id": r["id"], "partenaire": r["partenaire"], "criteres": criteres(c), "resume": r["resume"],
                                                       "cree": secondes(r.get("cree")) or maintenant, "derniere": secondes(r.get("derniere")) or maintenant})
    regles, etats, veilles = stockage.Regles(url), stockage.Etats(url), stockage.Veilles(url)
    base = stockage.base_agno(url)
    from agno.db.schemas.memory import UserMemory

    for g in donnees.get("gestionnaires") or []:
        numero = g["numero"]
        for s in g.get("souvenirs") or []:
            ident = f"alix-{numero.lstrip('+')}-{s['id']}"
            nouveau = base.get_user_memory(memory_id=ident, user_id=numero) is None
            base.upsert_user_memory(UserMemory(memory=s["texte"], memory_id=ident, user_id=numero, topics=[s.get("sujet") or "autre"],
                                               created_at=int(secondes(s.get("cree")) or maintenant), updated_at=int(secondes(s.get("modifie")) or maintenant)))
            b["souvenirs"] += nouveau
        for r in g.get("regles") or []:
            try:
                b["regles"] += not regles.apprendre(numero, r["texte"], portee(r.get("portee"), sites), r.get("qui"))["deja"]
            except ValueError:
                pass  # plus de 30 : les premières suffisent
        fil = g.get("fil") or ({"texte": g["filBrut"]["texte"][-1500:], "date": g["filBrut"].get("date")} if g.get("filBrut") else None)
        if fil and fil.get("texte"):
            etats.ecrire(numero, "fil", {"texte": fil["texte"][:1500], "quand": secondes(fil.get("date")) or maintenant, "jusqua": maintenant})
            b["fils"] += 1
        for cle, v in (g.get("veilles") or {}).items():
            fin = secondes(v.get("fin"))
            ident = f"a{cle}"[:16]
            if not fin or fin <= maintenant or veilles.existe(ident):
                continue
            frequence = v.get("frequence") if v.get("frequence") in FREQUENCES else "quotidienne"
            veilles.ajouter(numero, "veille", {"recherche": v.get("recherche", ""), "mode": v.get("mode") or "simple", "region": v.get("region") or "",
                                               "sites": v.get("sites") or [], "pour": v.get("pour") or "", "frequence": frequence, "fin": fin,
                                               "vus": (v.get("vus") or [])[-300:]}, maintenant + FREQUENCES[frequence], ident)
            b["veilles"] += 1
        for cle, z in (g.get("zones") or {}).items():
            fin = secondes(z.get("fin"))
            ident = f"a{cle}"[:16]
            if not fin or fin <= maintenant or veilles.existe(ident):
                continue
            veilles.ajouter(numero, "zone", {"lieu": z.get("lieu", ""), "quartier": z.get("quartier"), "type": z.get("type") or "villa",
                                             "region": z.get("region") or "", "restantes": z.get("restantes") or 1, "fin": fin,
                                             "derniere": z.get("derniere")}, maintenant + SEMAINE, ident)
            b["zones"] += 1
    carnet = stockage.Carnet(url)

    def empreinte(r: dict) -> tuple:
        return (r.get("nature"), carnets_plat(r.get("lieu")), r.get("devise"), round(float(r.get("prix_m2") or 0)), round(float(r.get("date") or 0)))

    deja = {empreinte(r) for r in carnet.releves()}
    for releves in (donnees.get("carnets") or {}).values():
        for r in sorted((releves or {}).get("releves") or [], key=lambda r: r.get("date") or 0):
            r = {**{k: r.get(k) for k in stockage.Carnet.CHAMPS}, "date": secondes(r.get("date")) or maintenant,
                 "note": secondes(r.get("note")) or maintenant, "par": r.get("par")}
            if empreinte(r) in deja:
                continue
            _, nouveau = carnet.noter({k: v for k, v in r.items() if k != "par"}, r["par"])
            deja.add(empreinte(r))
            b["releves"] += nouveau
    reglages.ecrire(MARQUE, {"quand": maintenant, "export": donnees.get("cree"), "bilan": b})
    return b


def principal(argv: list[str]) -> int:
    import os

    from noyau import config as configuration
    from noyau.environnement import charger

    env = charger(dict(os.environ))
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1 or not env.get("DATABASE_URL") or not (env.get("CLIENT_CONFIG") or env.get("CLIENT_CONFIG_FILE")):
        print("usage : DATABASE_URL=… CLIENT_CONFIG_FILE=… python -m packs.immobilier.reprise export.json [--encore]", file=sys.stderr)
        return 2
    conf = configuration.lire(env.get("CLIENT_CONFIG") or env["CLIENT_CONFIG_FILE"])
    stockage.migrer(env["DATABASE_URL"])
    with open(args[0], encoding="utf-8") as f:
        bilan = reprendre(json.load(f), env["DATABASE_URL"], conf, encore="--encore" in argv)
    print(json.dumps(bilan, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
