"""Autour d'un tour (une partie des Conversations, noyau/tour.py) : la voix (écouter, réécrire pour l'oral, dire,
l'écrit proposé par un vocal), les réactions d'humeur, la description des photos, la conversation en cours
(Historique.inactivite) et le Contexte que le noyau ajoute à chaque tour."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time

from . import accueil as accueils
from . import humeur as humeurs
from .oral import pour_la_voix
from .typographie import nettoyer

log = logging.getLogger("megga")

DECRIRE = 20.0  # secondes pour décrire les photos, au plus
OFFRE_VALIDE = 12 * 3600  # l'écrit proposé par un vocal vaut douze heures


def _borner(d: dict, n: int = 5000) -> None:
    if len(d) > n:  # oublie les plus anciens
        for p in list(d)[:1000]:
            del d[p]


class Autour:
    """Mélangé aux Conversations : il en utilise conf, exp, voie, reecrire, etats, rappels, memoire, juger, decrire."""

    def _humeur_du_tour(self, personne: str, role: str, texte: str, etat: dict) -> asyncio.Task | None:
        """Le juge des réactions d'humeur, lancé pendant que le modèle répond ; au moins trois tours entre deux (M7)."""
        genre = self._humeur(role)
        if self.juger is None or genre == "aucune" or not texte.strip() or not etat.get("id"):
            return None
        if self._depuis_reaction.get(personne, humeurs.ECART) < humeurs.ECART:
            self._depuis_reaction[personne] = self._depuis_reaction.get(personne, 0) + 1
            return None

        async def juger():
            try:
                emoji = await asyncio.wait_for(self.juger(texte, genre), humeurs.DELAI)
            except Exception as e:
                log.warning("réaction d'humeur : %s", str(e)[:200])
                emoji = ""
            if emoji and not etat["fini"]:
                etat["humeur"] = True
                await self._sans_echec(self.exp.reaction(personne, etat["id"], emoji))
            self._depuis_reaction[personne] = 0 if etat["humeur"] else self._depuis_reaction.get(personne, humeurs.ECART) + 1
            _borner(self._depuis_reaction)

        return asyncio.create_task(juger())

    async def _offre(self, personne: str) -> bool:
        """L'écrit proposé par le dernier vocal attend-il un oui ? Lu une seule fois."""
        if self.voie is None or not self.voie.parle:
            return False
        quand = self._offres.pop(personne, None)
        if quand is None and self.etats is not None:
            with contextlib.suppress(Exception):
                quand = await asyncio.to_thread(self.etats.lire, personne, "offre_ecrit")
        if quand:
            await self._garder_offre(personne, False)
        return bool(quand) and time.time() - float(quand) < OFFRE_VALIDE

    async def _garder_offre(self, personne: str, offerte: bool) -> None:
        if offerte:
            self._offres[personne] = time.time()
            _borner(self._offres)
        if self.etats is not None:
            await self._sans_echec(asyncio.to_thread(self.etats.ecrire, personne, "offre_ecrit", time.time() if offerte else None))

    async def _decrire_photos(self, parties: list[str], photos: list[tuple[int, int]], images: list) -> None:
        """Ce qu'on voit sur chaque photo, en une ligne, ajouté à sa mention : l'historique le garde pour les tours suivants (D6)."""
        if not photos or self.decrire is None or not self.conf.photos.decrire:
            return
        try:
            lignes = await asyncio.wait_for(self.decrire(images[:len(photos)]), DECRIRE)
        except Exception as e:
            log.warning("photos non décrites (%s) : %s", self.conf.id, str(e)[:200])
            return
        if not lignes or len(lignes) != len(photos):
            return
        for (i, n), ligne in zip(photos, lignes):
            ligne = " ".join(str(ligne or "").split())[:160]
            if ligne:
                parties[i] = parties[i].replace(f"[Photo reçue : média {n}]", f"[Photo reçue : média {n}, on y voit : {ligne}]", 1)

    async def _session(self, personne: str) -> str:
        """La conversation en cours de cette personne (session d'Agno) : la même, sauf après Historique.inactivite heures
        sans tour, où elle repart à neuf (ce qui s'y disait rejoint le fil, noyau/fil.py). D1."""
        heures = self.conf.historique.inactivite
        if not heures or self.etats is None:
            return personne
        maintenant = time.time()
        s = self._sessions.get(personne)
        if s is None:
            try:
                s = await asyncio.to_thread(self.etats.lire, personne, "session") or {}
            except Exception as e:
                log.warning("session illisible : %s", str(e)[:200])
                return personne
        s = dict(s)
        if s.get("derniere") and maintenant - float(s["derniere"]) > heures * 3600:
            s = {"id": f"{personne}:{int(maintenant)}", "debut": maintenant}
        s = {"id": s.get("id") or personne, "debut": s.get("debut") or 0, "derniere": maintenant}
        self._sessions[personne] = s
        _borner(self._sessions)
        await self._sans_echec(asyncio.to_thread(self.etats.ecrire, personne, "session", s))
        return s["id"]

    async def contexte(self, personne: str) -> str:
        """Ce que le noyau ajoute au Contexte de chaque tour : le prénom du profil (Role.prenom_du_profil), les rappels
        prévus (ReglageRappels.contexte), les souvenirs utiles (Memoire.outils), le vocal envoyé de soi-même."""
        lignes = []
        r = self._role_conf(self._roles.get(personne))
        if r is not None and r.prenom_du_profil:
            lignes.append(accueils.ligne_profil(self._profils.get(personne), self.conf.nom_agent))
        if self.conf.rappels.contexte and self.rappels is not None:
            from .rappels import contexte as rappels_prevus

            lignes.append(await rappels_prevus(self.rappels, self.conf.fuseau)(personne))
        if self.memoire is not None:
            lignes.append(await self.memoire.contexte(personne, self._entendus.get(personne, "")))
        lignes.append(await self._vocal_dit(personne))
        return "\n".join(l for l in lignes if l)

    async def _ecouter(self, media_id: str) -> str:
        if self.voie is None or not self.voie.ecoute:
            return ""
        try:
            texte = await self.voie.transcrire(await self.exp.telecharger(media_id))
            self.noter_journal("vocal_entendu")
            return texte
        except Exception as e:
            log.error("vocal illisible (%s) : %s", self.conf.id, str(e)[:200])
            self.noter_journal("vocal_illisible", detail=type(e).__name__)
            return ""

    async def _dire(self, personne: str, reponse: str, entendu: str, role: str | None = None) -> str | None:
        """La réponse réécrite pour l'oral (Oral, Role.oral), puis dite : le texte dit, ou None si la voix a échoué."""
        r = self._role_conf(role)
        dit = await pour_la_voix(self.reecrire, nettoyer(reponse), entendu, r.oral if r is not None else "",
                                 self.conf.voix.balises) if self.reecrire else reponse
        if self.conf.oral.references:  # une référence ne se lit jamais : elle part par écrit
            dit = re.sub(r"[ \t]{2,}", " ", re.sub(self.conf.oral.references, "", dit)).strip()
        return dit if await self._parler(personne, dit) else None

    async def _parler(self, personne: str, texte: str, genre: str = "vocal") -> bool:
        """Un vocal de l'agent : vrai s'il est parti."""
        try:
            dit = self.remplaceur.texte(texte)
            audio, ogg = await self.voie.dire(dit)
            self.noter_journal("voix_caracteres", len(dit))
            await self.exp.vocal(personne, audio, ogg)
            self._noter_fil(personne, "envoye", genre, dit)
            return True
        except Exception as e:
            log.error("voix en échec (%s), réponse écrite : %s", self.conf.id, str(e)[:200])
            self.noter_journal("voix_echec", detail=type(e).__name__)
            return False
