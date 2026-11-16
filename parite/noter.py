"""La notation du banc de parité : les mêmes critères et le même juge pour les traces des deux agents (parite/alix.mjs,
parite/socle.py). Un critère automatique se vérifie sur la trace ; un critère « juge » est lu par un second modèle, qui
voit la conversation, les outils appelés, ce qu'ils ont rendu et les faits du cas. La note d'un cas : la part de ses
critères tenus ; la note du banc : la moyenne, sur 100.

  .venv/bin/python -m parite.noter <traces d'Alix> <traces du socle> <rapport.md> [--juge claude-sonnet-5-5]
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from noyau.typographie import sans_artefacts

ICI = Path(__file__).resolve().parent
TYPO = {"nom": "ni point médian ni tiret long dans ses messages", "champ": "tout", "pas_motif": "[\u2014\u2013\u00b7]"}


def jeudi_prochain(maintenant: dt.datetime | None = None) -> str:
    d = (maintenant or dt.datetime.now(ZoneInfo("Europe/Zurich"))).date()
    return (d + dt.timedelta(days=(3 - d.weekday()) % 7 or 7)).isoformat()


def remplir(t: str) -> str:
    return t.replace("{jeudi}", jeudi_prochain())


def champs(trace: dict, greg: str, visiteur: str | None) -> dict:
    """Les textes d'une trace : ce que l'agent a envoyé à Greg, au visiteur, en tout, après le temps avancé."""
    de_l_agent = [e for e in trace["journal"] if e["de"] == "agent"]

    def pour(n):
        return [e["texte"] for e in de_l_agent if n and e.get("numero") == n]

    marque = trace.get("marque")
    apres = [e["texte"] for e in trace["journal"][marque:] if e["de"] == "agent"] if marque is not None else []
    return {"pour_greg": "\n".join(pour(greg)), "dernier_pour_greg": (pour(greg) or [""])[-1], "pour_visiteur": "\n".join(pour(visiteur)),
            "dernier_pour_visiteur": (pour(visiteur) or [""])[-1], "tout": "\n".join(e["texte"] for e in de_l_agent), "apres_avance": "\n".join(apres)}


def outil_tenu(trace: dict, c: dict) -> bool:
    noms = c["outil"]
    trouves = [o for o in trace["outils"] if o["nom"] in noms]
    if c.get("entree"):
        trouves = [o for o in trouves if all(str((o.get("entree") or {}).get(k)) == str(v) for k, v in c["entree"].items())]
    if c.get("entree_motif"):
        trouves = [o for o in trouves if re.search(remplir(c["entree_motif"]), json.dumps(o.get("entree") or {}, ensure_ascii=False))]
    if c.get("entree_existe"):
        trouves = [o for o in trouves if (o.get("entree") or {}).get(c["entree_existe"])]
    return len(trouves) >= c.get("min", 1)


def automatique(c: dict, trace: dict, textes: dict) -> bool:
    """Un critère automatique, sur une trace."""
    if "et" in c:
        return all(automatique(x, trace, textes) for x in c["et"])
    if "outil" in c:
        return outil_tenu(trace, c)
    if "pas_outil" in c:
        return not any(o["nom"] in c["pas_outil"] for o in trace["outils"])
    if "gestion_aucune" in c:
        g = c["gestion_aucune"]
        return not any((not g.get("methode") or x["methode"] == g["methode"]) and (not g.get("methode_pas") or x["methode"] != g["methode_pas"])
                       and (not g.get("chemin") or re.search(g["chemin"], x["chemin"])) for x in trace["gestion"])
    if "resultat_pas" in c:
        return not any(re.search(c["resultat_pas"], r) for r in trace["resultats"])
    t = textes[c["champ"]]
    if "motifs" in c:
        return all(re.search(remplir(m), t) for m in c["motifs"])
    if "pas_motif" in c:
        return not re.search(c["pas_motif"], t)
    if "pas_motifs" in c:
        return not any(re.search(m, t) for m in c["pas_motifs"])
    raise ValueError(f"critère inconnu : {c}")


def lisible(journal: list) -> str:
    return "\n".join(f"{e['de']} → {e['a']} : {('[touche ' + e['touche'] + ']') if e.get('touche') else e['texte']}" for e in journal)


def juger(client, modele: str, cas: dict, trace: dict, criteres: list[str]) -> list[dict]:
    """Le juge : un appel, tous les critères « juge » du cas, une réponse JSON."""
    if not criteres:
        return []
    consigne = f"""Tu évalues l'assistante WhatsApp d'un agent immobilier (Greg). Sois exigeant et factuel : un critère n'est tenu que si la conversation le montre clairement.

Cas : {cas['titre']}
Faits connus : {remplir(cas['faits'])}
Outils appelés par l'assistante : {' ; '.join(o['nom'] + ' ' + json.dumps(o.get('entree') or {}, ensure_ascii=False) for o in trace['outils']) or 'aucun'}
Ce que les outils lui ont rendu (un fait qui en vient n'est pas inventé) :
{chr(10).join(r[:1500] for r in trace['resultats'])[:16000] or 'rien'}

Conversation :
{lisible(trace['journal'])}

Critères :
{chr(10).join(f'{i}. {c}' for i, c in enumerate(criteres, 1))}

Réponds seulement par un tableau JSON, un objet par critère, dans l'ordre : [{{"ok": true|false, "raison": "une phrase"}}]"""
    try:
        r = client.messages.create(model=modele, max_tokens=2000, messages=[{"role": "user", "content": consigne}])
        texte = "".join(getattr(b, "text", "") for b in r.content)
        v = json.loads(texte[texte.index("["):texte.rindex("]") + 1])
        return [{"ok": bool((v[i] or {}).get("ok")), "raison": sans_artefacts(str((v[i] or {}).get("raison", "")))} for i in range(len(criteres))]
    except Exception as e:
        return [{"ok": False, "raison": f"juge illisible : {str(e)[:120]}"} for _ in criteres]


def noter(cas: dict, trace: dict, greg: str, client, juge: str) -> dict:
    textes = champs(trace, greg, cas.get("visiteur"))
    criteres = [*cas["criteres"], TYPO]
    avis = iter(juger(client, juge, cas, trace, [c["nom"] for c in criteres if c.get("juge")]))
    notes = []
    for c in criteres:
        if c.get("juge"):
            a = next(avis)
            notes.append({"nom": c["nom"], "juge": True, **a})
        else:
            try:
                ok = automatique(c, trace, textes)
            except Exception:
                ok = False
            notes.append({"nom": c["nom"], "juge": False, "ok": ok, "raison": ""})
    if trace.get("erreur"):
        notes.append({"nom": "le cas s'est joué sans erreur", "juge": False, "ok": False, "raison": trace["erreur"]})
    return {"note": sum(n["ok"] for n in notes) / len(notes), "notes": notes}


def principal(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    import anthropic

    from parite.socle import cle_anthropic

    juge = argv[argv.index("--juge") + 1] if "--juge" in argv else "claude-sonnet-5-5"
    client = anthropic.Anthropic(api_key=cle_anthropic())
    doc = json.loads((ICI / "cas.json").read_text(encoding="utf-8"))
    dossiers = {"Alix": Path(args[0]), "Socle": Path(args[1])}
    lignes, details, totaux = [], [], {k: [] for k in dossiers}
    for cas in doc["cas"]:
        par = {}
        for nom, d in dossiers.items():
            f = d / f"{cas['id']}.json"
            if f.exists():
                par[nom] = noter(cas, json.loads(f.read_text(encoding="utf-8")), doc["greg"], client, juge)
                totaux[nom].append(par[nom]["note"])
        if not par:
            continue
        cellule = lambda n: f"{round(par[n]['note'] * 100)} %" if n in par else "pas joué"  # noqa: E731
        lignes.append(f"| {cas['id']} | {cellule('Alix')} | {cellule('Socle')} | {cas['titre']} |")
        details.append(f"## {cas['id']}. {cas['titre']}")
        for nom, r in par.items():
            details.append(f"\n**{nom}** : {round(r['note'] * 100)} %")
            details += [f"- {'tenu' if n['ok'] else '**raté**'} : {n['nom']}{' (juge)' if n['juge'] else ''}{'. ' + n['raison'] if n['raison'] else ''}" for n in r["notes"]]
        details.append("")
    moyenne = {k: round(sum(v) / len(v) * 100) if v else None for k, v in totaux.items()}
    quand = dt.datetime.now(ZoneInfo("Europe/Zurich")).strftime("%d.%m.%Y %H:%M")
    md = [f"# Banc de parité : Alix {moyenne['Alix']} / 100, socle {moyenne['Socle']} / 100", "",
          f"{quand}. Les {len(lignes)} cas de parite/cas.json, joués sur les deux agents avec le vrai Claude ; juge {juge}.", "",
          "| Cas | Alix | Socle | Titre |", "|---|---|---|---|", *lignes, "", *details]
    Path(args[2]).write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Alix {moyenne['Alix']} / 100, socle {moyenne['Socle']} / 100 ({len(lignes)} cas) : {args[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
