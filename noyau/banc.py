"""Le banc d'essai par pack (lot 9.6) : des scénarios rejoués avant une mise en service, mesurés en pass^k.

La qualité est le premier frein des entreprises, et la régularité compte plus que le meilleur score : un agent qui
répond juste une fois sur deux n'est pas fiable. Le banc rejoue chaque scénario k fois, chaque fois avec une personne
neuve, contre l'agent d'une version (construit comme en service, dans une base d'essai à part, rien ne part sur
WhatsApp). Un essai réussit si tous ses critères tiennent ; un cas compte dans le score s'il réussit à chacun de ses
k essais (pass^k, comme τ-bench). Le score de la version : la part de ses cas tenus à chaque fois.

Les scénarios (`noyau/banc/<métier>.json`, généralisés du banc de parité d'Alix, `parite/`) :
  {"id", "titre", "etapes": [{"texte"}], "faits", "config"?: {réglages ajoutés pour ce cas}, "criteres": [...]}
Un critère est vérifié sur la trace (« outil », « pas_outil », « motifs », « pas_motif ») ou lu par un juge (« juge »),
un second modèle qui voit la conversation, les outils appelés et les faits du cas.

  python -m noyau.banc <configuration.yaml> [k] [--juge claude-sonnet-5-5]
"""

from __future__ import annotations

import asyncio
import json
import re
import tempfile
from collections import Counter
from pathlib import Path

from .tour import en_echec
from .typographie import sans_artefacts

ICI = Path(__file__).resolve().parent / "banc"
K_MAX = 5
JUGE_DELAI = 60.0  # secondes par appel au juge (le client d'Anthropic en attend 600 par défaut)
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
    echecs = " ; ".join(f"{o['nom']} ({o['resultat']})" for o in trace.get("echecs", [])) or "aucun"
    return f"""Tu évalues l'assistant WhatsApp d'une entreprise. Sois exigeant et factuel : un critère n'est tenu que si la conversation le montre clairement.

Cas : {cas['titre']}
Faits connus : {cas.get('faits', '')}
Outils appelés par l'assistant : {outils}
Outils qui ont échoué ou ont été refusés (rien n'a été fait) : {echecs}
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

        client = anthropic.AsyncAnthropic(api_key=cle, timeout=JUGE_DELAI, max_retries=1)
        r = await client.messages.create(model=modele, max_tokens=2000,
                                         messages=[{"role": "user", "content": consigne_du_juge(cas, trace, criteres)}])
        texte = "".join(getattr(b, "text", "") for b in r.content)
        return json.loads(texte[texte.index("["):texte.rindex("]") + 1])

    return juger


class Refus:
    """Le journal d'audit du banc (noyau/approbations.py) : par personne, les appels d'outils que le gardien n'a pas
    faits (refusés, ou en attente d'un accord qui ne viendra pas)."""

    def __init__(self):
        from .approbations import Gardien

        self.gardien = Gardien(audit=self)
        self.non_faits: dict[str, Counter] = {}

    def noter(self, personne, outil, regle, issue, duree, detail=""):
        if issue in ("refuse", "attente"):
            self.non_faits.setdefault(personne, Counter())[outil] += 1

    async def lire(self, personne: str) -> Counter:
        await self.gardien.vider(5)
        return self.non_faits.pop(personne, Counter())


async def jouer(cas: dict, agent, personne: str) -> dict:
    """Un essai d'un cas : ses étapes, une à une, à l'agent ; la trace de ce qu'il a écrit et des outils qu'il a appelés
    (ceux qui ont échoué ou que le gardien a refusés à part : rien n'a été fait)."""
    trace = {"journal": [], "reponses": [], "outils": [], "echecs": [], "resultats": [], "erreur": None}
    refus = getattr(agent, "refus_du_banc", None)
    for etape in cas["etapes"]:
        trace["journal"].append(("personne", etape["texte"]))
        try:
            sortie = await agent.arun(etape["texte"], user_id=personne, session_id=personne)
        except Exception as e:
            trace["erreur"] = f"{type(e).__name__} : {str(e)[:200]}"
            break
        texte = getattr(sortie, "content", None) or ""
        if en_echec(sortie):  # Agno ne lève pas : un statut d'erreur, et son message à la place de la réponse
            trace["erreur"] = f"le modèle a échoué : {texte[:200]}"
            break
        trace["journal"].append(("agent", texte))
        trace["reponses"].append(texte)
        non_faits = await refus.lire(personne) if refus is not None else Counter()
        for t in getattr(sortie, "tools", None) or []:
            appel = {"nom": t.tool_name, "entree": t.tool_args or {}}
            echec = bool(getattr(t, "tool_call_error", None))
            if not echec and non_faits[t.tool_name] > 0:
                non_faits[t.tool_name] -= 1
                echec = True
            if echec:
                trace["echecs"].append({**appel, "resultat": str(t.result or "")[:300]})
                continue
            trace["outils"].append(appel)
            trace["resultats"].append(str(t.result or ""))
    return trace


async def noter(cas: dict, trace: dict, juger) -> dict:
    """Les critères d'un essai : tenus ou pas, avec la raison du juge ; l'essai réussit si tous tiennent.
    `incomplet` : pourquoi l'essai ne mesure pas l'agent (le modèle ou le juge en panne), sinon None."""
    criteres = [*cas["criteres"], TYPO]
    noms = [c["nom"] for c in criteres if c.get("juge")]
    avis, incomplet = [], trace["erreur"]
    if noms and incomplet:  # l'essai s'est arrêté : rien à juger, pas d'appel payé pour rien
        avis = [{"ok": False, "raison": "non jugé : l'essai s'est arrêté sur une erreur"} for _ in noms]
    elif noms:
        try:
            v = await juger(cas, trace, noms)
            avis = [{"ok": (v[i] or {}).get("ok") is True, "raison": sans_artefacts(str((v[i] or {}).get("raison", "")))} for i in range(len(noms))]
        except Exception as e:
            avis = [{"ok": False, "raison": f"juge illisible : {str(e)[:120]}"} for _ in noms]
            incomplet = avis[0]["raison"]
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
    return {"ok": all(n["ok"] for n in notes), "notes": notes, "incomplet": incomplet}


async def passer(conf, construire_agent, juger, k: int = 3, cas: list[dict] | None = None) -> dict:
    """Le banc d'une configuration : chaque cas k fois, une personne neuve à chaque fois.

    `construire_agent(conf, dossier)` rend l'agent à essayer (dans une base d'essai à part, sous `dossier`) ;
    `juger(cas, trace, criteres)` rend [{ok, raison}] pour les critères « juge ». Au premier essai incomplet (le modèle
    ou le juge en panne), le banc s'arrête : son rapport est marqué `incomplet`, sans score."""
    from . import config as configuration

    if not 1 <= int(k) <= K_MAX:
        raise ValueError(f"k : de 1 à {K_MAX}")
    cas = cas if cas is not None else scenarios(conf.metier)
    resultats, incomplet = [], None
    with tempfile.TemporaryDirectory() as dossier:
        for i, c in enumerate(cas):
            conf_du_cas = configuration.lire({**conf.model_dump(mode="json"), **c["config"]}) if c.get("config") else conf
            agent = construire_agent(conf_du_cas, Path(dossier) / f"cas-{i}")
            essais = []
            for n in range(int(k)):
                trace = await jouer(c, agent, f"banc-{c['id']}-{n}")
                essais.append({**await noter(c, trace, juger), "journal": trace["journal"]})
                if incomplet := essais[-1]["incomplet"]:
                    break
            resultats.append({"id": c["id"], "titre": c["titre"], "pass_k": all(e["ok"] for e in essais),
                              "reussis": sum(e["ok"] for e in essais), "essais": essais})
            if incomplet:
                break
    tenus = sum(r["pass_k"] for r in resultats)
    mesure = bool(resultats) and not incomplet
    return {"k": int(k), "cas": len(resultats), "tenus": tenus, "score": round(tenus / len(resultats), 3) if mesure else None,
            "pass_1": round(sum(r["reussis"] for r in resultats) / (len(resultats) * int(k)), 3) if mesure else None,
            "incomplet": incomplet, "resultats": resultats}


def agent_d_essai(cles: dict, principal=None):
    """Construit l'agent d'une version comme en service, dans une base d'essai à part (comme l'essai de l'atelier) :
    avec des rôles, celui qui sert une personne nouvelle (le visiteur, noyau/roles.py)."""

    def construire_agent(conf, dossier: Path):
        from atelier.essai import role_d_essai

        from . import stockage
        from .agent import construire
        from .app import outils_du_client

        dossier.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{dossier}/banc.db"
        nom_role = role_d_essai(conf, None)
        role = conf.les_roles().get(nom_role) if nom_role else None
        groupes = tuple(g for g in role.outils if g == "rappels") if role is not None else None
        outils = outils_du_client(conf, stockage.Rappels(url), groupes)
        if conf.transfert:  # passer la main (lot 9.3) : dans le banc, l'équipe n'est prévenue de rien
            from .reprises import Transfert

            outils += Transfert(stockage.Reprises(url)).outils_pour(nom_role)
        refus = Refus()
        agent = construire(conf, stockage.base_agno(url), cles, principal=principal, outils=outils, role=role,
                           nom_role=nom_role, gardien=refus.gardien)
        agent.refus_du_banc = refus
        return agent

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
    cles = {n: os.environ.get(n, "") for n in ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "MISTRAL_API_KEY")}
    r = asyncio.run(passer(conf, agent_d_essai(cles), juge_anthropic(juge, cles["ANTHROPIC_API_KEY"]), k))
    if r["incomplet"]:
        print(f"banc incomplet, sans score : {r['incomplet']}")
    for c in r["resultats"]:
        print(f"{'tenu ' if c['pass_k'] else 'RATÉ '} {c['id']} {c['titre']} ({c['reussis']}/{r['k']})")
        for e in c["essais"]:
            for n in e["notes"]:
                if not n["ok"]:
                    print(f"        {n['nom']} : {n.get('raison', '')}")
    if not r["incomplet"]:
        print(f"pass^{r['k']} : {r['tenus']}/{r['cas']} ({r['score']:.0%}) ; pass@1 : {r['pass_1']:.0%}")
    sys.stdout.flush()
    return 0 if r["score"] == 1 else 1


if __name__ == "__main__":
    import sys

    raise SystemExit(principal(sys.argv[1:]))
