"""Le transfert vers un humain (lot 9.3) : l'agent confie une conversation à l'équipe, puis la reprend.

- L'outil `passer_la_main(motif, resume)` (Config.transfert) : quand la personne demande un humain, quand c'est
  sensible (plainte, litige, urgence), ou quand l'agent ne peut pas l'aider. La conversation est confiée à l'équipe
  (stockage.Reprises) ; chaque gestionnaire la reçoit sur WhatsApp, avec le résumé et « Je la prends ».
- Tant qu'elle est en cours, l'agent ne répond plus à cette personne. Ses messages vont au fil (la console les lit)
  et, si un gestionnaire l'a prise, lui sont relayés sur WhatsApp.
- L'équipe répond du numéro de l'entreprise : dans la console, ou sur WhatsApp en le demandant à son propre agent
  (outils du gestionnaire : `conversations_transmises`, `repondre_en_reprise`, `rendre_la_main`).
- Rendue (ou sans personne pour la prendre en 24 heures, ou sans message de l'équipe en 72 heures), l'agent
  reprend, et lit pendant un jour ce que l'équipe a dit et ce que la personne a écrit depuis (le Contexte). À
  l'expiration, la personne reçoit un mot d'excuse, et le gestionnaire qui l'avait prise en est prévenu.

Par API, pas de transfert : le logiciel ne recevrait pas les réponses de l'équipe ; l'outil le dit à l'agent.
87 % des clients exigent de pouvoir parler à un humain (Gartner, août 2026) : c'est la condition de leur confiance.
"""

from __future__ import annotations

import asyncio
import logging
import re

from agno.run import RunContext

from .garde import masquer_secrets

log = logging.getLogger("megga")

PREFIXE = "tr:"
_CHOIX = re.compile(r"^tr:(\d{1,10}):(prendre|rendre)$")
ACTIONS = ("prendre", "message", "rendre")
CONSIGNE = ("Si la personne demande à parler à quelqu'un de l'équipe, si c'est sensible (réclamation, litige, urgence) "
            "ou si tu ne peux pas l'aider, passe la main (passer_la_main) avec un résumé clair, puis dis-lui qu'un membre "
            "de l'équipe va lui répondre.")
# Ce que la personne reçoit quand personne de l'équipe ne lui a répondu à temps (son agent le sait au tour suivant).
EXCUSES = {"fr": "Toutes nos excuses : personne de l'équipe n'a pu vous répondre à temps. Je reprends votre demande, "
                 "écrivez-moi ici pour continuer.",
           "en": "We are sorry: no one from the team was able to reply in time. I am taking your request back, "
                 "write to me here to continue."}


def _qui(personne: str) -> str:
    """Une personne telle que l'équipe la lit : son numéro avec « + », ou son identifiant de logiciel."""
    return personne if personne.startswith(("api:", "+")) else f"+{personne}"


def _sur_whatsapp(par: str | None) -> bool:
    """Celui qui a pris la conversation est un gestionnaire sur WhatsApp (pas la console)."""
    return bool(par) and par != "console" and not par.startswith("api:")


class Transfert:
    """Les conversations confiées à l'équipe d'un client. `reprises` : stockage.Reprises ; `fil` : stockage.Fil ;
    `gestionnaires` : leurs numéros, comme les conversations les nomment (« +41… ») ; `conversations` (noyau/tour.py) est posé une fois créé."""

    def __init__(self, reprises, fil=None, gestionnaires=(), nom_agent: str = "L'agent", langue: str = "fr"):
        self.reprises = reprises
        self.fil = fil
        self.gestionnaires = list(gestionnaires)
        self.nom_agent = nom_agent
        self.excuse = EXCUSES.get(langue, EXCUSES["fr"])
        self.conversations = None

    # Les outils

    def outils_pour(self, role: str | None) -> list:
        """Les outils d'un agent : ceux de l'équipe pour le gestionnaire, passer la main pour tous les autres."""
        return self._outils_equipe() if role == "gestionnaire" else [self._passer_la_main(role or "public")]

    def _passer_la_main(self, role: str):
        transfert = self

        async def passer_la_main(motif: str, resume: str, run_context: RunContext) -> str:
            """Confie la conversation à un membre de l'équipe : quand la personne le demande, quand c'est sensible
            (réclamation, litige, urgence), ou quand tu ne peux pas l'aider. Ensuite, tu ne lui réponds plus :
            l'équipe prend le relais et te rendra la main.

            Args:
                motif: pourquoi, en quelques mots (« demande un humain », « réclamation »).
                resume: ce que l'équipe doit savoir pour reprendre sans tout relire : la demande, ce qui a été dit, ce qui reste.
            """
            personne = getattr(run_context, "user_id", None) or ""
            if not personne or personne.startswith("api:") or not transfert.gestionnaires:
                return "Le transfert à l'équipe n'est pas possible dans cette conversation : propose plutôt un contact direct."
            motif, resume = " ".join(str(motif).split())[:300], masquer_secrets(str(resume).strip())[:2000]
            ident, nouvelle = await asyncio.to_thread(transfert.reprises.ouvrir, personne, role, motif or "sans motif", resume)
            await asyncio.to_thread(transfert.reprises.prevenir_une_fois, ident)  # l'agent le lui dit maintenant
            if nouvelle:
                transfert._prevenir_equipe(ident, personne, motif, resume)
            return (f"Conversation transmise à l'équipe (n° {ident}). Dis à la personne, simplement, qu'un membre de l'équipe "
                    "va lui répondre ici ; ensuite, tu ne lui réponds plus jusqu'à ce que l'équipe te rende la main.")

        return passer_la_main

    def _outils_equipe(self) -> list:
        transfert = self

        def conversations_transmises() -> str:
            """Les conversations confiées à l'équipe qui attendent ou sont en cours, avec leur numéro et leur résumé."""
            lignes = transfert.reprises.lister("ouverte") + transfert.reprises.lister("prise")
            if not lignes:
                return "Aucune conversation transmise en ce moment."
            return "\n".join(f"{r['id']} : {_qui(r['personne'])}, {r['motif']} ({'prise' if r['etat'] == 'prise' else 'à prendre'}). "
                             f"{r['resume'][:300]}" for r in sorted(lignes, key=lambda r: r["id"]))

        async def repondre_en_reprise(conversation: int, texte: str, run_context: RunContext) -> str:
            """Envoie, du numéro de l'entreprise, la réponse du gestionnaire à une conversation transmise (son numéro).

            Args:
                conversation: le numéro de la conversation transmise.
                texte: la réponse, telle que le gestionnaire veut qu'elle parte.
            """
            return await transfert.repondre(int(conversation), str(texte), getattr(run_context, "user_id", None) or "equipe")

        async def rendre_la_main(conversation: int, run_context: RunContext) -> str:
            """Rend une conversation transmise à l'agent, quand l'équipe a fini.

            Args:
                conversation: le numéro de la conversation transmise.
            """
            return await transfert._rendre_par(int(conversation), getattr(run_context, "user_id", None) or "equipe")

        return [conversations_transmises, repondre_en_reprise, rendre_la_main]

    # L'équipe

    def _prevenir_equipe(self, ident: int, personne: str, motif: str, resume: str) -> None:
        """Chaque gestionnaire reçoit la conversation, une fois fini le tour de la personne (la réponse de l'agent part d'abord)."""
        if self.conversations is None:
            return
        corps = f"{self.nom_agent} vous transmet une conversation (n° {ident}) avec {_qui(personne)} : {motif}.\n{resume}"
        message = {"liste": {"corps": corps, "bouton": "Répondre", "section": f"Conversation {ident}", "lignes": [
            {"id": f"{PREFIXE}{ident}:prendre", "titre": "Je la prends", "description": "ses messages vous arriveront ici"},
            {"id": f"{PREFIXE}{ident}:rendre", "titre": "Rendre à l'agent"}]}}
        for n in self.gestionnaires:
            self.conversations.apres_le_tour(personne, lambda n=n: self.conversations.envoyer_de_soi_meme(
                n, [message], "transfert", variables=[self.nom_agent, motif]))

    async def choix(self, personne: str, role: str, charge: str) -> str:
        """Le choix touché d'un gestionnaire (« tr:12:prendre »), traité sans le modèle."""
        if role != "gestionnaire":
            return "Seule l'équipe peut prendre cette conversation."
        m = _CHOIX.fullmatch(charge)
        if m is None:
            return "Je n'ai pas compris ce choix."
        if m[2] == "rendre":
            return await self._rendre_par(int(m[1]), personne)
        r = await asyncio.to_thread(self.reprises.prendre, int(m[1]), personne)
        if r is None:
            avant = await asyncio.to_thread(self.reprises.une, int(m[1]))
            deja = avant and avant["etat"] == "prise" and avant["par"] == personne
            return (f"Vous avez déjà la conversation {m[1]}." if deja else
                    f"La conversation {m[1]} n'est plus à prendre ({avant['etat'] if avant else 'inconnue'}).")
        return (f"La conversation {m[1]} est à vous : ses messages vous arrivent ici. Pour lui répondre, dites-moi "
                f"« réponds à la conversation {m[1]} : … » ; « rends la main pour la {m[1]} » quand c'est fini.")

    async def repondre(self, ident: int, texte: str, par: str) -> dict:
        """La réponse de l'équipe, envoyée du numéro de l'entreprise ; la conversation est prise par celui qui écrit."""
        texte = texte.strip()
        if not texte:
            raise ValueError("texte : la réponse à envoyer")
        r = await asyncio.to_thread(self.reprises.ecrite, ident, par)
        if r is None:
            raise ValueError(f"la conversation {ident} n'est plus en cours")
        envoi = await self.conversations.envoyer_de_soi_meme(r["personne"], [{"texte": texte[:4000], "usage": "reprise"}], "reprise",
                                                             variables=[self.nom_agent])
        return {"id": ident, "envoi": envoi}

    async def rendre(self, ident: int, par: str = "console") -> dict | None:
        """Rendue à l'agent ; une conversation prise ne se rend que par celui qui l'a prise, ou par la console."""
        return await asyncio.to_thread(self.reprises.rendre, ident, None if par == "console" else par)

    async def _rendre_par(self, ident: int, par: str) -> str:
        if await self.rendre(ident, par):
            return f"La conversation {ident} est rendue à l'agent."
        avant = await asyncio.to_thread(self.reprises.une, ident)
        if avant and avant["etat"] == "prise":
            return (f"La conversation {ident} a été prise par un autre membre de l'équipe : seule la personne qui l'a prise, "
                    "ou la console, peut la rendre à l'agent.")
        return f"La conversation {ident} n'est plus en cours."

    async def echeance(self, maintenant: float) -> float | None:
        """À l'heure dite (/interne/rappels) : les conversations oubliées reviennent à l'agent ; la personne reçoit le mot
        d'excuse, le gestionnaire qui l'avait prise en est prévenu. Rend l'heure de la prochaine expiration."""
        for r in await asyncio.to_thread(self.reprises.expirer, maintenant):
            try:
                await self.conversations.envoyer_de_soi_meme(r["personne"], [{"texte": self.excuse}], "reprise_fin",
                                                             variables=[self.nom_agent])
                if _sur_whatsapp(r["par"]):
                    await self.conversations.envoyer_de_soi_meme(r["par"], [{"texte": (
                        f"Sans message de l'équipe depuis trois jours, la conversation {r['id']} avec {_qui(r['personne'])} "
                        f"revient à {self.nom_agent}.")}], "reprise_fin", variables=[self.nom_agent])
            except Exception as e:
                log.warning("fin de reprise non annoncée : %s", str(e)[:200])
        return await asyncio.to_thread(self.reprises.prochaine)

    async def prendre(self, ident: int, par: str) -> dict | None:
        return await asyncio.to_thread(self.reprises.prendre, ident, par)

    # Le tour d'une personne

    async def garde(self, personne: str, messages: list) -> bool:
        """Au début d'un tour : vrai si un humain a la conversation (l'agent ne répond pas). Ses messages vont au fil,
        et à celui qui l'a prise sur WhatsApp."""
        r = await asyncio.to_thread(self.reprises.en_cours, personne)
        if r is None:
            return False
        textes, rang = [], 0
        for m in messages:
            genre = "vocal" if getattr(m, "vocal", None) else (m.media.genre if getattr(m, "media", None) else "texte")
            texte = getattr(m, "texte", "") or getattr(m, "choix", "") or ""
            if genre not in ("vocal", "texte"):  # numéroté comme au tour de l'agent : la console et l'équipe le retrouvent
                rang += 1
                texte = f"[média {await self.conversations._numeroter(personne, m.media, rang)}] {texte}".strip()
            self.conversations._noter_fil(personne, "recu", genre, texte)
            textes.append(texte or f"[{genre}]")
        if r["etat"] == "prise" and _sur_whatsapp(r["par"]):
            try:
                await self.conversations.envoyer_de_soi_meme(
                    r["par"], [{"texte": f"Message de {_qui(personne)} (conversation {r['id']}) : {' / '.join(textes)}"}],
                    "reprise_message", variables=[_qui(personne)])
            except Exception as e:  # l'humain garde la main : la console lit le message dans le fil
                log.warning("message non relayé à l'équipe : %s", str(e)[:200])
        return True

    async def contexte(self, personne: str) -> str:
        """Ce que l'agent doit savoir d'une conversation que l'équipe lui a rendue (le Contexte, pendant un jour) : ce que
        l'équipe a dit, ce que la personne a écrit depuis ; pourquoi elle lui revient, au premier tour."""
        if not personne:
            return ""
        r = await asyncio.to_thread(self.reprises.a_relire, personne)
        if r is None:
            return ""
        dits, ecrits = [], []
        if self.fil is not None:
            fil = [m for m in await asyncio.to_thread(self.fil.messages, personne, 50) if (m.get("quand") or 0) >= r["cree"]]
            dits = [m for m in fil if m.get("genre") == "reprise"][-10:]
            depuis = dits[-1]["quand"] if dits else r["cree"]
            ecrits = [m["texte"] for m in fil if m.get("sens") == "recu" and m.get("genre") != "bouton"
                      and depuis < m["quand"] <= r["fin"]][-10:]
        pourquoi = "l'équipe te l'a rendue" if r["etat"] == "rendue" else "personne de l'équipe n'a pu lui répondre à temps"
        if not r["relue"] and r["etat"] == "expiree":
            pourquoi += (" ; elle a reçu un mot d'excuse, aide-la de ton mieux" if r["prevenue"] == 2
                         else " : excuse-toi et aide-la de ton mieux")
        lignes = [f"Cette conversation avait été confiée à l'équipe ({r['motif']}) ; {pourquoi}."]
        if dits:
            lignes.append("Ce que l'équipe a écrit à la personne : " + " | ".join(f"« {d['texte'][:400]} »" for d in dits))
        if ecrits:
            lignes.append("Ce que la personne a écrit ensuite, sans réponse : " + " | ".join(f"« {e[:400]} »" for e in ecrits))
        return "<reprise>\n" + "\n".join(lignes) + "\n</reprise>"
