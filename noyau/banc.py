"""Le banc d'essai par pack (lot 9.6) : des scénarios rejoués avant une mise en service, mesurés en pass^k.

La qualité est le premier frein des entreprises, et la régularité compte plus que le meilleur score : un agent qui
répond juste une fois sur deux n'est pas fiable. Le banc rejoue chaque scénario k fois, chaque fois avec une personne
neuve, contre l'agent d'une version (construit comme en service, dans une base d'essai à part, rien ne part sur
WhatsApp). Un essai réussit si tous ses critères tiennent ; un cas compte dans le score s'il réussit à chacun de ses
k essais (pass^k, comme τ-bench). Le score de la version : la part de ses cas tenus à chaque fois.

Les scénarios (`noyau/banc/<métier>.json`, généralisés du banc de parité d'Alix, `parite/`) :
  {"id", "titre", "etapes": [{"texte"}], "faits", "config"?: {réglages ajoutés pour ce cas},
   "documents"?: [{"titre", "texte"}] (rangés dans la base d'essai avant le cas), "criteres": [...]}
Un critère est vérifié sur la trace (« outil », « pas_outil », « motifs », « pas_motif ») ou lu par un juge (« juge »),
un second modèle qui voit la conversation, les outils appelés et les faits du cas.

Les cas qui rangent des documents demandent le modèle de recherche (noyau/connaissances.py) : celui de l'image, ou un
dossier posé par `python socle/modele.py <dossier>` et donné par MEGGA_MODELE_DIR. Sans lui, le banc s'arrête avant de
jouer.

  python -m noyau.banc <configuration.yaml> [k] [--juge claude-sonnet-5-5]
"""

from __future__ import annotations

import asyncio
import json
import re
import tempfile
from pathlib import Path

from .typographie import sans_artefacts

ICI = Path(__file__).resolve().parent / "banc"
K_MAX = 5
TYPO = {"nom": "ni point médian ni tiret long dans ses messages", "pas_motif": "[—–·]"}


def scenarios(metier: str) -> list[dict]:
    """Les scénarios d'un métier : ceux du noyau (tous les agents), puis ceux de son pack."""
    cas = json.loads((ICI / "general.json").read_text(encoding="utf-8"))["cas"]
    propre = ICI / f"{metier}.json"
    if metier != "general" and propre.is_file():
        cas += json.loads(propre.read_text(encoding="utf-8"))["cas"]
    return cas


def automatique(c: dict, trace: dict) -> bool:
    """Un critère vérifié sur la trace : outils appelés, ou motifs dans ce que l'agent a écrit."""
    if "et" in c:
        return all(automatique(x, trace) for x in c["et"])
    if "outil" in c:
        return any(o["nom"] in c["outil"] for o in trace["outils"])
    if "pas_outil" in c:
        return not any(o["nom"] in c["pas_outil"] for o in trace["outils"])
    texte = "\n".join(trace["reponses"])
    if "motifs" in c:
        return all(re.search(m, texte, re.I) for m in c["motifs"])
    if "pas_motif" in c:
        return not re.search(c["pas_motif"], texte, re.I)
    raise ValueError(f"critère inconnu : {c}")


def consigne_du_juge(cas: dict, trace: dict, criteres: list[str]) -> str:
    conversation = "\n".join(f"{qui} : {texte}" for qui, texte in trace["journal"])
    outils = " ; ".join(f"{o['nom']} {json.dumps(o['entree'], ensure_ascii=False)}" for o in trace["outils"]) or "aucun"
    return f"""Tu évalues l'assistant WhatsApp d'une entreprise. Sois exigeant et factuel : un critère n'est tenu que si la conversation le montre clairement.

Cas : {cas['titre']}
Faits connus : {cas.get('faits', '')}
Outils appelés par l'assistant : {outils}
Ce que les outils lui ont rendu (un fait qui en vient n'est pas inventé) :
{chr(10).join(r[:1500] for r in trace['resultats'])[:12000] or 'rien'}

Conversation :
{conversation}

Critères :
{chr(10).join(f'{i}. {c}' for i, c in enumerate(criteres, 1))}

Réponds seulement par un tableau JSON, un objet par critère, dans l'ordre : [{{"ok": true|false, "raison": "une phrase"}}]"""


def juge_anthropic(modele: str, cle: str):
    """Le juge par défaut : un modèle d'Anthropic, un appel par essai, tous les critères « juge » d'un coup."""

    async def juger(cas: dict, trace: dict, criteres: list[str]) -> list[dict]:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=cle)
        r = await client.messages.create(model=modele, max_tokens=2000,
                                         messages=[{"role": "user", "content": consigne_du_juge(cas, trace, criteres)}])
        texte = "".join(getattr(b, "text", "") for b in r.content)
        return json.loads(texte[texte.index("["):texte.rindex("]") + 1])

    return juger


async def jouer(cas: dict, agent, personne: str) -> dict:
    """Un essai d'un cas : ses étapes, une à une, à l'agent ; la trace de ce qu'il a écrit et des outils qu'il a appelés."""
    trace = {"journal": [], "reponses": [], "outils": [], "resultats": [], "erreur": None}
    for etape in cas["etapes"]:
        trace["journal"].append(("personne", etape["texte"]))
        try:
            sortie = await agent.arun(etape["texte"], user_id=personne, session_id=personne)
        except Exception as e:
            trace["erreur"] = f"{type(e).__name__} : {str(e)[:200]}"
            break
        texte = getattr(sortie, "content", None) or ""
        trace["journal"].append(("agent", texte))
        trace["reponses"].append(texte)
        for t in getattr(sortie, "tools", None) or []:
            trace["outils"].append({"nom": t.tool_name, "entree": t.tool_args or {}})
            trace["resultats"].append(str(t.result or ""))
    return trace


async def noter(cas: dict, trace: dict, juger) -> dict:
    """Les critères d'un essai : tenus ou pas, avec la raison du juge ; l'essai réussit si tous tiennent."""
    criteres = [*cas["criteres"], TYPO]
    noms = [c["nom"] for c in criteres if c.get("juge")]
    avis = []
    if noms:
        try:
            v = await juger(cas, trace, noms)
            avis = [{"ok": bool((v[i] or {}).get("ok")), "raison": sans_artefacts(str((v[i] or {}).get("raison", "")))} for i in range(len(noms))]
        except Exception as e:
            avis = [{"ok": False, "raison": f"juge illisible : {str(e)[:120]}"} for _ in noms]
    avis = iter(avis)
    notes = []
    for c in criteres:
        if c.get("juge"):
            notes.append({"nom": c["nom"], "juge": True, **next(avis)})
        else:
            try:
                ok = automatique(c, trace)
            except Exception:
                ok = False
            notes.append({"nom": c["nom"], "juge": False, "ok": ok})
    if trace["erreur"]:
        notes.append({"nom": "le cas s'est joué sans erreur", "juge": False, "ok": False, "raison": trace["erreur"]})
    return {"ok": all(n["ok"] for n in notes), "notes": notes}


async def passer(conf, construire_agent, juger, k: int = 3, cas: list[dict] | None = None) -> dict:
    """Le banc d'une configuration : chaque cas k fois, une personne neuve à chaque fois.

    `construire_agent(conf, dossier)` rend l'agent à essayer (dans une base d'essai à part, sous `dossier`) ; si le
    cas porte des `documents`, `construire_agent(conf, dossier, documents)` les range avant l'essai ;
    `juger(cas, trace, criteres)` rend [{ok, raison}] pour les critères « juge »."""
    from . import config as configuration

    if not 1 <= int(k) <= K_MAX:
        raise ValueError(f"k : de 1 à {K_MAX}")
    cas = cas if cas is not None else scenarios(conf.metier)
    resultats = []
    with tempfile.TemporaryDirectory() as dossier:
        for i, c in enumerate(cas):
            conf_du_cas = configuration.lire({**conf.model_dump(mode="json"), **c["config"]}) if c.get("config") else conf
            place = Path(dossier) / f"cas-{i}"
            agent = construire_agent(conf_du_cas, place, c["documents"]) if c.get("documents") else construire_agent(conf_du_cas, place)
            essais = []
            for n in range(int(k)):
                trace = await jouer(c, agent, f"banc-{c['id']}-{n}")
                essais.append({**await noter(c, trace, juger), "journal": trace["journal"]})
            resultats.append({"id": c["id"], "titre": c["titre"], "pass_k": all(e["ok"] for e in essais),
                              "reussis": sum(e["ok"] for e in essais), "essais": essais})
    tenus = sum(r["pass_k"] for r in resultats)
    return {"k": int(k), "cas": len(resultats), "tenus": tenus, "score": round(tenus / len(resultats), 3) if resultats else None,
            "pass_1": round(sum(r["reussis"] for r in resultats) / (len(resultats) * int(k)), 3) if resultats else None,
            "resultats": resultats}


def agent_d_essai(cles: dict, principal=None, vectoriseur=None):
    """Construit l'agent d'une version comme en service, dans une base d'essai à part (comme l'essai de l'atelier).

    Il a les documents du cas (rangés dans la base d'essai) et les demandes (leads), sans webhook ni alerte."""

    def construire_agent(conf, dossier: Path, documents=None):
        from . import connaissances as savoir, connecteurs, stockage
        from .agent import construire
        from .app import outils_du_client

        dossier.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{dossier}/banc.db"
        base = leads = None
        if "connaissances" in conf.outils:
            base = savoir.Base(stockage.Connaissances(url), vectoriseur)
            for d in documents or []:
                base.ajouter(d["titre"], d["texte"].encode(), "texte")
        if "leads" in conf.outils:
            leads = connecteurs.Leads(stockage.Leads(url))
        outils = outils_du_client(conf, stockage.Rappels(url), connaissances=base, leads=leads)
        if conf.transfert:  # passer la main (lot 9.3) : dans le banc, l'équipe n'est prévenue de rien
            from .reprises import Transfert

            outils += Transfert(stockage.Reprises(url)).outils_pour(None)
        return construire(conf, stockage.base_agno(url), cles, principal=principal, outils=outils)

    return construire_agent


def principal(argv: list[str]) -> int:
    import os
    import sys

    from . import config as configuration

    if not argv:
        print(__doc__.split("\n\n")[-1])
        return 2
    juge = "claude-sonnet-5-5"
    if "--juge" in argv:
        i = argv.index("--juge")
        juge = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    conf = configuration.lire(argv[0])
    k = int(argv[1]) if len(argv) > 1 else 3
    cas = scenarios(conf.metier)
    vectoriseur = None
    if any(c.get("documents") for c in cas):
        # Des cas rangent des documents : sans le modèle de recherche, ils échoueraient en route, après avoir payé les
        # cas d'avant (relecture finale du lot 10, I3). Un seul modèle, chargé une fois pour tous les cas.
        from .connaissances import Vectoriseur

        vectoriseur = Vectoriseur()
        if not vectoriseur.disponible():
            print(f"Le modèle de recherche des documents est absent ({vectoriseur.dossier}) : des cas de ce banc rangent des "
                  "documents. Posez-le avant de lancer le banc (python socle/modele.py <dossier>, puis "
                  "MEGGA_MODELE_DIR=<dossier>), ou lancez le banc dans l'image, qui l'a déjà. Rien n'a été joué.")
            return 2
    cles = {n: os.environ.get(n, "") for n in ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "MISTRAL_API_KEY")}
    r = asyncio.run(passer(conf, agent_d_essai(cles, vectoriseur=vectoriseur), juge_anthropic(juge, cles["ANTHROPIC_API_KEY"]), k, cas))
    for c in r["resultats"]:
        print(f"{'tenu ' if c['pass_k'] else 'RATÉ '} {c['id']} {c['titre']} ({c['reussis']}/{r['k']})")
        for e in c["essais"]:
            for n in e["notes"]:
                if not n["ok"]:
                    print(f"        {n['nom']} : {n.get('raison', '')}")
    print(f"pass^{r['k']} : {r['tenus']}/{r['cas']} ({r['score']:.0%}) ; pass@1 : {r['pass_1']:.0%}")
    sys.stdout.flush()
    return 0 if r["score"] == 1 else 1


if __name__ == "__main__":
    import sys

    raise SystemExit(principal(sys.argv[1:]))
