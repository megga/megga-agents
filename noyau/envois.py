"""Ce que l'agent envoie de lui-même, sans qu'on vienne de lui écrire (une partie des Conversations, noyau/tour.py) :
rappels, messages gardés hors des 24 heures, modèles Meta, échéances des packs, et le vocal demandé par l'équipe.

Dans les 24 heures de WhatsApp, un message libre ; au-delà, le modèle Meta de l'usage, sinon le modèle « message »
qui annonce que quelque chose attend : ce qui était gardé part au prochain message de la personne.
"""

from __future__ import annotations

import asyncio
import logging
import time

from . import phrases
from .typographie import nettoyer
from .whatsapp import fenetre_ouverte

log = logging.getLogger("megga")

REESSAI_RAPPEL = 300  # secondes avant de retenter un rappel en échec
GARDE_JOURNAL = 400 * 86400  # le journal du noyau (échecs, volumes) : un peu plus d'un an
ABANDON_RAPPEL = 24 * 3600  # un rappel encore en échec un jour après son heure est abandonné (noté au journal)
ANNONCE_VALIDE = 12 * 3600  # un modèle « message » vaut pour ce qui s'ajoute pendant douze heures, tant que la personne n'a pas répondu
VOCAL_RETENU = 24 * 3600  # le vocal envoyé de soi-même reste dans le Contexte un jour
# Ce que l'agent envoie de lui-même (un rappel, un modèle Meta, un message gardé) n'entre pas dans son historique : il reste
# deux jours dans le Contexte, les huit derniers (audit du 17.11.2026 : un rappel parti à 9 h 01, que l'agent a cru raté et
# « reprogrammé » à 13 h, sans qu'on le lui demande).
ENVOI_RETENU = 48 * 3600
ENVOIS_RETENUS = 8
GENRES_DE_SOI = {"rappel": "le rappel", "modele": "un modèle WhatsApp", "bonjour": "le mot du matin", "differe": "un message gardé",
                 "document": "un document"}
CHARGE_VOCAL = "vocal"  # ce que rend le bouton du modèle Meta « vocal » (« Écouter le message »)


class Envois:
    """Mélangé aux Conversations : il en utilise conf, exp, contacts, differes, rappels, etats, voie, journal, fil."""

    async def ecrire_de_soi_meme(self, personne: str, texte: str, usage: str, variable: str | None = None) -> str:
        """Un message que l'agent envoie sans qu'on vienne de lui écrire (rappel, relance). Hors des 24 heures, le modèle
        Meta de cet usage reçoit `variable` (le texte lui-même, sans elle).

        Rend « libre » (dans les 24 heures), « modele » (par le modèle Meta de cet
        usage) ou « attente » (ni l'un ni l'autre : à remettre au prochain message).
        """
        dernier = await asyncio.to_thread(self.contacts.dernier, personne) if self.contacts else None
        texte = self.remplaceur.texte(nettoyer(texte))
        if fenetre_ouverte(dernier):
            await self.exp.texte(personne, texte)
            self._noter_fil(personne, "envoye", usage, texte)
            await self._retenir_envoi(personne, usage, texte)
            return "libre"
        modele = self.conf.modeles_meta.get(usage)
        if modele:
            try:
                await self.exp.modele(personne, modele.nom, modele.langue, [nettoyer(variable or texte)[:1000]])
                self._noter_fil(personne, "envoye", "modele", texte[:1000])
                await self._retenir_envoi(personne, usage, texte)
                return "modele"
            except Exception as e:
                # Un modèle suspendu, reclassé ou refusé : le rappel attend le prochain message, sans boucler toutes les
                # 5 minutes (relecture du 16.11.2026, I10).
                log.error("modèle « %s » refusé (%s) : %s", usage, self.conf.id, str(e)[:200])
                self.noter_journal("envoi_echec", detail="modele")
        # Sans modèle de cet usage (ou refusé) : le modèle « message » annonce que quelque chose attend (le rappel part
        # au message suivant).
        await self._annoncer(personne)
        return "attente"

    async def envoyer_de_soi_meme(self, personne: str, messages: list[dict], usage: str, variables: list[str] | None = None,
                                  langue: str = "", garder: bool = True) -> str:
        """Des messages que l'agent envoie de lui-même à une personne (une demande pour un gestionnaire, une fiche
        pour un partenaire, une réponse pour un visiteur). `messages` : {"texte", "apercu"?}, {"document", "nom", "legende"}
        (un identifiant chez Meta), {"liste": {corps, bouton, section, lignes}} ou {"vocal": texte}.

        Dans les 24 heures, ils partent. Au-delà, ils sont gardés pour son prochain message (stockage.Differes, sauf `garder` faux),
        et le modèle Meta de cet usage (« <usage>_<langue> » d'abord) l'annonce s'il est réglé, avec `variables`.
        Rend « libre », « modele », « attente », ou « aucune » (pas de WhatsApp, ou une personne venue par API).
        """
        if self.conf.whatsapp is None or personne.startswith("api:"):
            return "aucune"
        dernier = await asyncio.to_thread(self.contacts.dernier, personne) if self.contacts else None
        if fenetre_ouverte(dernier):
            await self._envoyer_messages(personne, messages, usage)
            return "libre"
        if garder and self.differes is not None:
            await asyncio.to_thread(self.differes.garder, personne, messages)
        modele = self.conf.modeles_meta.get(f"{usage}_{langue}") or self.conf.modeles_meta.get(usage)
        if modele:
            try:
                charge = CHARGE_VOCAL if usage == "vocal" else ""
                await self.exp.modele(personne, modele.nom, modele.langue, [nettoyer(v)[:1000] for v in (variables or [])],
                                      **({"charge": charge} if charge else {}))
                self._noter_fil(personne, "envoye", "modele", " | ".join(variables or []))
                await self._retenir_envoi(personne, "modele", f"{usage} : {' | '.join(variables or [])}")
                return "modele"
            except Exception as e:
                log.error("modèle refusé (%s) : %s", self.conf.id, str(e)[:200])
                self.noter_journal("envoi_echec", detail="modele")
        # Le repli : le modèle « message » (« Vous avez un message de… ») annonce ce qui est gardé.
        if garder and self.differes is not None and await self._annoncer(personne, langue):
            return "modele"
        return "attente"

    async def vocal_de_soi_meme(self, personne: str, texte: str) -> str:
        """Un vocal que l'agent dit de lui-même, à la demande de l'équipe (route /vocal, noyau/app.py ; repris de la méthode
        `vocal` de conversation.js d'Alix FSP) : jamais en texte. Dans les 24 heures, il part ; sinon il attend le prochain
        message de la personne, et le modèle Meta « vocal » (sinon « message ») l'annonce. Il rejoint le Contexte des tours
        suivants, pour que l'agent sache de quoi on lui parle. Rend « parti », « attente », « echec » (la voix en panne,
        rien n'est parti) ou « sans voix »."""
        if self.voie is None or not self.voie.parle:
            return "sans voix"
        texte = " ".join(str(texte or "").split())[:4000]
        async with self._a_son_tour(personne):
            dernier = await asyncio.to_thread(self.contacts.dernier, personne) if self.contacts else None
            if fenetre_ouverte(dernier):
                if not await self._parler(personne, texte, "vocal"):
                    return "echec"
                await self._retenir_vocal(personne, texte)
                return "parti"
            if self.differes is None:
                return "echec"
            await self.envoyer_de_soi_meme(personne, [{"vocal": texte}], "vocal", [self.conf.nom_agent])
            return "attente"

    async def _retenir_envoi(self, personne: str, genre: str, texte: str) -> None:
        """Ce que l'agent vient d'envoyer de lui-même, gardé deux jours pour le Contexte (ENVOI_RETENU)."""
        if self.etats is None or not personne or personne.startswith("api:"):
            return

        async def garder():
            maintenant = time.time()
            avant = await asyncio.to_thread(self.etats.lire, personne, "de_soi") or []
            gardes = [e for e in avant if isinstance(e, dict) and maintenant - float(e.get("quand") or 0) < ENVOI_RETENU]
            gardes.append({"quand": maintenant, "genre": genre, "texte": " ".join(str(texte or "").split())[:300]})
            await asyncio.to_thread(self.etats.ecrire, personne, "de_soi", gardes[-ENVOIS_RETENUS:])

        await self._sans_echec(garder())

    async def _envois_de_soi(self, personne: str) -> str:
        """Pour le Contexte : ce que l'agent a envoyé de lui-même ces deux derniers jours, qui n'est pas dans son historique."""
        if self.etats is None or not personne:
            return ""
        try:
            gardes = await asyncio.to_thread(self.etats.lire, personne, "de_soi") or []
        except Exception as e:
            log.warning("envois de soi-même illisibles : %s", str(e)[:200])
            return ""
        from .rappels import date_longue

        maintenant = time.time()
        lignes = [f"{date_longue(float(e['quand']), self.conf.fuseau)}, {GENRES_DE_SOI.get(e.get('genre'), 'un message')} : « {e['texte']} »"
                  for e in gardes if isinstance(e, dict) and e.get("texte") and maintenant - float(e.get("quand") or 0) < ENVOI_RETENU]
        if not lignes:
            return ""
        return ("Ce que tu as envoyé de toi-même à cette personne ces deux derniers jours, hors de ta conversation : "
                + " ; ".join(lignes) + ". Ces messages sont bien partis : ne les renvoie pas, ne les reprogramme pas, "
                "ne dis pas qu'ils ont manqué.")

    async def _retenir_vocal(self, personne: str, texte: str) -> None:
        if self.etats is not None:
            await self._sans_echec(asyncio.to_thread(self.etats.ecrire, personne, "vocal_dit", {"texte": texte, "quand": time.time()}))

    async def _vocal_dit(self, personne: str) -> str:
        """Le vocal envoyé de soi-même ces dernières 24 heures, pour le Contexte."""
        if self.etats is None:
            return ""
        v = await asyncio.to_thread(self.etats.lire, personne, "vocal_dit")
        if not v or time.time() - float(v.get("quand") or 0) > VOCAL_RETENU:
            return ""
        return ("Tu as envoyé de toi-même à cette personne, à la demande de ton équipe, ce message vocal : "
                f"« {str(v.get('texte') or '')[:1500]} ». Elle peut t'en parler.")

    async def _annoncer(self, personne: str, langue: str = "") -> bool:
        """Le modèle Meta « message » (« message_<langue> » d'abord), s'il est réglé : il annonce un message qui attend, sa
        réponse rouvre les 24 heures et ce qui était gardé part aussitôt. Sa variable : le nom de l'agent."""
        modele = self.conf.modeles_meta.get(f"message_{langue}") or self.conf.modeles_meta.get("message")
        if modele is None:
            return False
        # Déjà annoncé depuis son dernier message, il y a moins de douze heures : ce qui s'ajoute partira avec le reste.
        deja = self._annonces.get(personne)
        if deja is None and self.etats is not None:
            try:
                deja = await asyncio.to_thread(self.etats.lire, personne, "annonce")
            except Exception as e:
                log.warning("annonce illisible : %s", str(e)[:200])
        dernier = await asyncio.to_thread(self.contacts.dernier, personne) if self.contacts else None
        if deja and time.time() - deja < ANNONCE_VALIDE and (dernier is None or deja > dernier):
            return True
        try:
            await self.exp.modele(personne, modele.nom, modele.langue, [self.conf.nom_agent])
            self._noter_fil(personne, "envoye", "modele", "un message attend")
            self._annonces[personne] = time.time()
            if self.etats is not None:
                await self._sans_echec(asyncio.to_thread(self.etats.ecrire, personne, "annonce", self._annonces[personne]))
            if len(self._annonces) > 5000:
                for p in list(self._annonces)[:1000]:
                    del self._annonces[p]
            return True
        except Exception as e:
            log.error("modèle « message » refusé (%s) : %s", self.conf.id, str(e)[:200])
            self.noter_journal("envoi_echec", detail="modele")
            return False

    async def peut_ecrire(self, personne: str, usage: str, langue: str = "") -> bool:
        """Un message libre (dans les 24 heures) ou le modèle Meta de cet usage peut-il partir à cette personne ?"""
        if self.conf.whatsapp is None or personne.startswith("api:"):
            return False
        if self.conf.modeles_meta.get(f"{usage}_{langue}") or self.conf.modeles_meta.get(usage):
            return True
        if self.differes is not None and self.conf.modeles_meta.get("message"):
            return True
        return fenetre_ouverte(await asyncio.to_thread(self.contacts.dernier, personne) if self.contacts else None)

    async def _envoyer_messages(self, personne: str, messages: list[dict], usage: str) -> None:
        for m in messages:
            if m.get("vocal"):  # un vocal gardé hors des 24 heures (vocal_de_soi_meme) : en vocal seulement
                if not await self._parler(personne, m["vocal"], "vocal"):
                    raise RuntimeError("vocal non parti")
                await self._retenir_vocal(personne, m["vocal"])
            elif m.get("document"):
                await self.exp.document(personne, m.get("nom") or "document.pdf", media_id=m["document"], legende=m.get("legende", ""))
                self._noter_fil(personne, "envoye", "document", m.get("legende") or m.get("nom") or "")
                await self._retenir_envoi(personne, "document", m.get("legende") or m.get("nom") or "")
            elif m.get("liste"):
                l = m["liste"]
                await self.exp.liste(personne, nettoyer(l["corps"]), l["bouton"], l["section"], l["lignes"])
                self._noter_fil(personne, "envoye", "liste", nettoyer(l["corps"]))
                await self._retenir_envoi(personne, usage, nettoyer(l["corps"]))
            elif m.get("texte"):
                texte = m["texte"] if m.get("secret") else self.remplaceur.texte(nettoyer(m["texte"]))
                if m.get("apercu"):  # la carte d'une annonce : son lien avec son aperçu
                    await self.exp.texte(personne, texte, apercu=True)
                else:
                    await self.exp.texte(personne, texte)
                # Un mot de passe ne se range jamais dans le fil (relu par la console et par le résumé du fil).
                self._noter_fil(personne, "envoye", usage, "(mot de passe envoyé)" if m.get("secret") else texte)
                await self._retenir_envoi(personne, usage, "(mot de passe envoyé)" if m.get("secret") else texte)

    async def _rappels_differes(self, personne: str, livres: dict | None = None, role: str | None = None) -> None:
        """Les rappels échus hors des 24 heures, sans modèle Meta, et les messages gardés : ils partent maintenant.
        `livres["n"]` : combien sont partis."""
        livres = {"n": 0} if livres is None else livres
        if self.differes is not None:
            # Chaque ligne gardée se retire une fois envoyée : un conteneur qui tombe en route ne perd rien.
            for ligne in await asyncio.to_thread(self.differes.a_envoyer, personne):
                rates = []
                for m in ligne["messages"]:
                    try:
                        await self._envoyer_messages(personne, [m], "differe")
                        livres["n"] += 1
                    except Exception as e:
                        # Retenté au message suivant, sans rajeunir (effacé après un mois) ni retenir ceux qui suivent.
                        log.error("message gardé non envoyé (%s) : %s", self.conf.id, str(e)[:200])
                        self.noter_journal("envoi_echec", detail="differe")
                        rates.append(m)
                if rates:
                    await asyncio.to_thread(self.differes.garder, personne, rates, ligne["quand"])
                await asyncio.to_thread(self.differes.retirer, ligne["ligne"])
        if self.rappels is None:
            return
        tutoie = self._tutoie(role if role is not None else await self._role_de(personne))
        for r in await asyncio.to_thread(self.rappels.differes, personne):
            texte = self.remplaceur.texte(nettoyer(phrases.rappel(r["texte"], tutoie)))
            await self.exp.texte(personne, texte)
            self._noter_fil(personne, "envoye", "rappel", texte)
            await self._retenir_envoi(personne, "rappel", texte)
            await asyncio.to_thread(self.rappels.marquer, r["id"], "envoye")
            livres["n"] += 1

    async def envoyer_rappels_echus(self, maintenant: float) -> dict:
        """Appelé par la porte à l'heure d'un rappel : envoie ce qui est échu, rend le prochain."""
        bilan = {"libre": 0, "modele": 0, "attente": 0, "echec": 0}
        # Les réglages que le client change lui-même (le mot du matin, la voix…) avant ce qui part à l'heure dite.
        if self.avant_le_tour is not None:
            await self._sans_echec(self.avant_le_tour())
        if self.journal is not None and maintenant >= self._purge_le:  # le journal ne grossit pas sans fin
            self._purge_le = maintenant + 86400
            await self._sans_echec(asyncio.to_thread(self.journal.purger, maintenant - GARDE_JOURNAL))
        if self.rappels is None:
            return {"prochain": await self._echeances(maintenant), **bilan}
        # Les rappels d'abord : une échéance d'un pack (une recherche sur les portails) peut prendre du temps.
        for r in await asyncio.to_thread(self.rappels.echus, maintenant):
            if self.conf.whatsapp is None:
                # Un agent sans WhatsApp (seulement par API) ne peut rien envoyer : un rappel d'avant est
                # annulé, au lieu d'échouer à chaque passage.
                await asyncio.to_thread(self.rappels.marquer, r["id"], "annule")
                self.noter_journal("rappel_echec", detail="sans WhatsApp")
                bilan["echec"] += 1
                continue
            try:
                texte = phrases.rappel(r["texte"], self._tutoie(await self._role_de(r["personne"])))
                async with self._a_son_tour(r["personne"]):  # jamais au milieu d'une réponse en route
                    voie = await self.ecrire_de_soi_meme(r["personne"], texte, "rappel", str(r["texte"]).strip().rstrip("."))
                await asyncio.to_thread(self.rappels.marquer, r["id"], "differe" if voie == "attente" else "envoye")
                bilan[voie] += 1
            except Exception as e:
                log.error("rappel en échec (%s) : %s", self.conf.id, str(e)[:200])
                if maintenant - float(r["quand"]) > ABANDON_RAPPEL:  # un jour d'échecs : abandonné, plus retenté
                    await asyncio.to_thread(self.rappels.marquer, r["id"], "echec")
                    self.noter_journal("rappel_echec", detail="abandonné après un jour")
                    continue
                self.noter_journal("rappel_echec", detail=type(e).__name__)
                bilan["echec"] += 1
        prochain = await asyncio.to_thread(self.rappels.prochain)
        if bilan["echec"] and prochain is not None:
            # Un rappel en échec reste à envoyer : il est retenté dans 5 minutes, pas en boucle.
            prochain = max(prochain, maintenant + REESSAI_RAPPEL)
        suivant = await self._echeances(maintenant)
        if suivant is not None:
            prochain = suivant if prochain is None else min(prochain, suivant)
        return {"prochain": prochain, **bilan}

    async def _echeances(self, maintenant: float) -> float | None:
        """Ce que les packs ont à faire à l'heure dite ; rend la plus proche des prochaines heures. Une échéance en
        échec est retentée dans 5 minutes."""
        prochaines = []
        for f in self.echeances:
            try:
                p = await f(maintenant)
            except Exception as e:
                log.error("échéance en échec (%s) : %s", self.conf.id, str(e)[:200])
                self.noter_journal("echeance_echec", detail=type(e).__name__)
                p = maintenant + REESSAI_RAPPEL
            if p is not None:
                prochaines.append(p)
        return min(prochaines) if prochaines else None
