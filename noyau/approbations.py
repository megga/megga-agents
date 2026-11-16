"""Les approbations et le journal d'audit des outils (lot 9.1).

Chaque appel d'outil passe par un crochet d'Agno (tool_hooks), qui sait quel outil, avec quels arguments et pour
quelle personne (run_context) :
- il est inscrit au journal d'audit (stockage.Audit) : l'outil, la personne, la règle, l'issue, la durée ;
- « interdit » : l'outil n'est pas proposé au modèle (filtrer) ; appelé quand même, il est refusé ;
- « approbation » : l'action n'est pas faite tout de suite. La demande (l'outil et ses arguments) est gardée
  (stockage.Approbations) et part aux gestionnaires sur WhatsApp, avec Accepter et Refuser ; la console peut aussi
  décider. Accordée, elle est faite au nom de la personne qui l'a demandée, qui en est prévenue et dont l'agent
  connaît l'issue au tour suivant (le Contexte). Refusée, ou sans réponse en 48 heures, elle ne se fait pas.

Pourquoi : un agent WhatsApp lit les messages d'inconnus, voit les données du client et peut agir. Une consigne
glissée dans un message (injection) peut lui faire appeler n'importe quel outil, et aucun filtre ne la détecte de
façon fiable. L'accord d'une personne de l'entreprise sur les actions qui comptent est la défense qui tient.

Sur WhatsApp, seul un gestionnaire (noyau/roles.py) décide, par un choix touché traité sans le modèle
(Conversations.choix, préfixe « ap: »).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import time

from agno.run import RunContext

from .garde import masquer_secrets

log = logging.getLogger("megga")

PREFIXE = "ap:"
AUTO, APPROBATION, INTERDIT = "auto", "approbation", "interdit"
CONTEXTE_MAX = 600  # ce que l'agent relit du résultat d'une action accordée
_INJECTES = ("run_context", "agent", "team", "images", "videos", "audios", "files")
_CHOIX = re.compile(r"^ap:(\d{1,10}):(oui|non)$")


def regles_pour(conf, role=None) -> dict[str, str]:
    """Les règles des outils pour un rôle : celles de la configuration, puis celles du rôle par-dessus."""
    return {**conf.approbations, **(role.approbations if role is not None else {})}


def equipe(gestionnaires) -> list[str]:
    """Les gestionnaires tels que les conversations les nomment (« +41… ») : c'est sous ce nom que leur fenêtre de
    24 heures se retrouve (noyau/tour.py, envoyer_de_soi_meme) ; sous un autre, le message attendrait au lieu de partir."""
    from .whatsapp import chiffres

    return [f"+{chiffres(n)}" for n in (gestionnaires or {})]


def nom(outil) -> str | None:
    return getattr(outil, "name", None) or getattr(outil, "__name__", None)


def filtrer(outils, regles: dict[str, str]) -> list:
    """Les outils proposés au modèle : sans ceux qui sont interdits."""
    return [o for o in outils if regles.get(nom(o) or "") != INTERDIT]


def apercu(arguments: dict) -> str:
    """Les arguments d'une action, lisibles et masqués, pour la personne qui décide."""
    morceaux = [f"{k} : {v}" for k, v in arguments.items() if k not in _INJECTES]
    return masquer_secrets(" ; ".join(morceaux))[:500] or "sans précision"


class Gardien:
    """Le crochet des outils d'un client, et les décisions sur ses demandes.

    `audit` : stockage.Audit ; `demandes` : stockage.Approbations (sans elles, une action à approuver est refusée) ;
    `notifier` : async f(demande) qui prévient l'équipe ; `prevenir` : async f(demande, etat) qui prévient la personne
    de l'issue. Le journal s'écrit en arrière-plan : il ne retarde ni ne fait échouer un tour."""

    def __init__(self, audit=None, demandes=None, notifier=None, prevenir=None):
        self.audit = audit
        self.demandes = demandes
        self.notifier = notifier
        self.prevenir = prevenir
        self._outils: dict[tuple[str, str], object] = {}
        self._boites: dict[str, list] = {}  # les boîtes d'outils (serveurs MCP) d'un rôle : leurs fonctions viennent à la connexion
        self._taches: set[asyncio.Task] = set()

    def connaitre(self, outils, role: str = "public") -> None:
        """Les outils d'un rôle, par nom : ce qu'une demande accordée fera (le même nom peut servir à deux rôles)."""
        for o in outils:
            if hasattr(o, "functions") and not callable(o):  # une boîte d'outils (un serveur MCP)
                self._boites.setdefault(role, []).append(o)
                continue
            n = nom(o)
            fonction = getattr(o, "entrypoint", o)
            if n and callable(fonction):
                self._outils[(role, n)] = fonction

    def _noter(self, personne: str, outil: str, regle: str, issue: str, debut: float, detail: str = "") -> None:
        if self.audit is None:
            return
        duree = time.monotonic() - debut

        async def ecrire():
            try:
                await asyncio.to_thread(self.audit.noter, personne, outil, regle, issue, duree, detail)
            except Exception as e:
                log.warning("audit non écrit : %s", str(e)[:200])

        try:
            t = asyncio.get_running_loop().create_task(ecrire())
        except RuntimeError:  # hors d'une boucle (un outil appelé d'un fil) : écrit tout de suite
            asyncio.run(ecrire())
            return
        self._taches.add(t)
        t.add_done_callback(self._taches.discard)

    async def vider(self, delai: float) -> int:
        """Attend les écritures du journal encore en route (à l'arrêt, ou à la fin d'un essai) : `delai` secondes au
        plus. Une écriture encore dans la file des fils quand la boucle se ferme serait annulée sans être faite.
        Rend le nombre d'écritures restées en route."""
        restantes = set(self._taches)
        if restantes:
            _, restantes = await asyncio.wait(restantes, timeout=delai)
        return len(restantes)

    def crochet(self, regles: dict[str, str], role: str = "public"):
        """Le crochet d'Agno (tool_hooks) d'un agent : `regles` {outil: règle}, `role` celui de ses personnes."""

        async def crochet(function_name: str, function_call, arguments: dict, run_context=None):
            personne = getattr(run_context, "user_id", None) or "?"
            regle = regles.get(function_name, AUTO)
            debut = time.monotonic()
            if regle == INTERDIT:
                self._noter(personne, function_name, regle, "refuse", debut)
                return "Cet outil n'est pas permis ici : dis simplement à la personne que tu ne peux pas le faire."
            if regle == APPROBATION:
                return await self._demander(personne, role, function_name, dict(arguments or {}), debut)
            try:
                resultat = function_call(**(arguments or {}))
                if inspect.isawaitable(resultat):
                    resultat = await resultat
            except Exception as e:
                self._noter(personne, function_name, regle, "erreur", debut, type(e).__name__)
                raise
            self._noter(personne, function_name, regle, "fait", debut)
            return resultat

        return crochet

    async def _demander(self, personne: str, role: str, outil: str, arguments: dict, debut: float) -> str:
        if self.demandes is None or personne == "?":
            self._noter(personne, outil, APPROBATION, "refuse", debut, "sans demandes")
            return "Cette action demande l'accord de l'équipe, qui ne peut pas être demandé ici : dis-le simplement."
        propres = {k: v for k, v in arguments.items() if k not in _INJECTES}
        try:
            ident = await asyncio.to_thread(self.demandes.demander, personne, role, outil, propres)
        except ValueError as e:
            self._noter(personne, outil, APPROBATION, "refuse", debut, "trop")
            return f"{e} : dis à la personne qu'il faut d'abord attendre les réponses de l'équipe."
        self._noter(personne, outil, APPROBATION, "attente", debut, f"demande {ident}")
        if self.notifier is not None:
            try:
                await self.notifier({"id": ident, "personne": personne, "role": role, "outil": outil, "arguments": propres})
            except Exception as e:
                log.warning("équipe non prévenue de la demande %s : %s", ident, str(e)[:200])
        return (f"Demande {ident} envoyée à l'équipe : cette action ({outil}) attend l'accord d'un responsable et n'est pas "
                "encore faite. Dis-le simplement à la personne ; elle sera prévenue de la réponse.")

    async def decider(self, ident: int, accord: bool, par: str) -> dict:
        """Accorde (et fait) ou refuse une demande : {id, etat, resultat?}. Une ValueError si elle n'attend plus."""
        if self.demandes is None:
            raise ValueError("pas de demandes ici")
        d = await asyncio.to_thread(self.demandes.decider, ident, accord, par)
        if d is None:
            avant = await asyncio.to_thread(self.demandes.une, ident)
            raise ValueError(f"la demande {ident} n'attend plus de réponse ({avant['etat'] if avant else 'inconnue'})")
        debut = time.monotonic()
        if not accord:
            self._noter(d["personne"], d["outil"], APPROBATION, "refuse", debut, f"demande {ident}")
            issue = {"id": ident, "etat": "refusee"}
        else:
            etat, texte = await self._faire(d)
            await asyncio.to_thread(self.demandes.finir, ident, etat, texte)
            self._noter(d["personne"], d["outil"], APPROBATION, "fait" if etat == "faite" else "erreur", debut, f"demande {ident}")
            issue = {"id": ident, "etat": etat, "resultat": texte}
        if self.prevenir is not None:
            try:
                await self.prevenir(d, issue["etat"])
            except Exception as e:
                log.warning("personne non prévenue de la demande %s : %s", ident, str(e)[:200])
        return issue

    async def _faire(self, d: dict) -> tuple[str, str]:
        """L'action accordée, au nom de la personne qui l'a demandée : (faite ou echec, ce que l'outil a rendu)."""
        fonction = self._outils.get((d["role"], d["outil"]))
        for boite in self._boites.get(d["role"], []) if fonction is None else []:
            if hasattr(boite, "connect"):  # un serveur MCP : sa session du tour est fermée, on la rouvre pour l'action
                try:
                    await boite.connect(force=True)
                except Exception as e:
                    log.warning("serveur MCP injoignable pour la demande %s : %s", d["id"], str(e)[:200])
                    continue
            trouvee = (getattr(boite, "functions", None) or {}).get(d["outil"])
            if trouvee is not None:
                fonction = getattr(trouvee, "entrypoint", trouvee)
                break
        if fonction is None:
            return "echec", "outil introuvable dans cette version de l'agent"
        arguments = dict(d["arguments"])
        if "run_context" in inspect.signature(fonction).parameters:
            arguments["run_context"] = RunContext(run_id=f"approbation-{d['id']}", session_id=d["personne"], user_id=d["personne"])
        try:
            resultat = fonction(**arguments)
            if inspect.isawaitable(resultat):
                resultat = await resultat
            return "faite", masquer_secrets(str(resultat if resultat is not None else "fait"))[:2000]
        except Exception as e:
            log.warning("demande %s accordée, action en échec : %s", d["id"], str(e)[:200])
            return "echec", masquer_secrets(f"{type(e).__name__} : {str(e)[:300]}")

    async def choix(self, personne: str, role: str, charge: str) -> str:
        """Le choix touché d'un gestionnaire sur une demande (« ap:12:oui »), traité sans le modèle."""
        if role != "gestionnaire":
            return "Seule l'équipe peut répondre à cette demande."
        m = _CHOIX.fullmatch(charge)
        if m is None:
            return "Je n'ai pas compris ce choix."
        try:
            issue = await self.decider(int(m[1]), m[2] == "oui", personne)
        except ValueError as e:
            return f"C'est déjà réglé : {e}."
        if issue["etat"] == "faite":
            return f"Demande {issue['id']} accordée, c'est fait. {issue['resultat'][:300]}"
        if issue["etat"] == "echec":
            return f"Demande {issue['id']} accordée, mais l'action n'a pas pu se faire : {issue['resultat'][:300]}"
        return f"Demande {issue['id']} refusée : la personne en sera prévenue."

    async def contexte(self, personne: str) -> str:
        """Ce que l'agent doit savoir des demandes de cette personne décidées depuis son dernier message (le Contexte)."""
        if self.demandes is None or not personne:
            return ""
        lignes = await asyncio.to_thread(self.demandes.a_relire, personne)
        textes = []
        for d in lignes:
            quoi = f"La demande {d['id']} ({d['outil']})"
            if d["etat"] == "faite":
                textes.append(f"{quoi} a été accordée par l'équipe et faite : {(d['resultat'] or '')[:CONTEXTE_MAX]}")
            elif d["etat"] == "echec":
                textes.append(f"{quoi} a été accordée, mais l'action n'a pas pu se faire : {(d['resultat'] or '')[:CONTEXTE_MAX]}")
            elif d["etat"] == "refusee":
                textes.append(f"{quoi} a été refusée par l'équipe : ne la refais pas, propose autre chose.")
            else:
                textes.append(f"{quoi} n'a pas eu de réponse à temps : propose de la redemander si c'est encore utile.")
        if not textes:
            return ""
        return "<approbations>\n" + "\n".join(textes) + "\n</approbations>"
