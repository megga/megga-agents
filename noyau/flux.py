"""La réponse au fil de l'eau, par Server-Sent Events : le texte de l'agent part par morceaux, ses outils
s'annoncent, et l'événement « fin » porte la réponse complète, nettoyée, qui fait foi.

  event: texte   data: {"texte": "Bonjour, "}
  event: outil   data: {"outil": "chercher_biens", "etat": "debut"}     (puis "fin")
  event: fin     data: {"reponse": "Bonjour, ..."}
  event: erreur  data: {"erreur": "...", "statut": 503, "reponse": "..."}

Les crochets de sortie d'Agno (garde.crochet_secrets, typographie.crochet_typographie) ne s'appliquent qu'à la
réponse finale : les morceaux du flux sortent bruts du modèle. Ils passent donc ici par le même masque des
secrets avant de partir (Masque). Leur typographie est corrigée morceau par morceau ; la réponse de « fin »,
nettoyée en entier, reste celle qui compte (un logiciel peut remplacer ce qu'il a affiché par elle).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from fastapi.responses import StreamingResponse

from .garde import masquer_secrets
from .typographie import sans_artefacts

ATTENTE = 15.0  # secondes sans événement (un outil qui cherche longtemps) avant un commentaire qui garde la ligne ouverte
PING = ": attente\n\n"
TYPE = "text/event-stream"


def evenement(genre: str, donnees: dict) -> str:
    """Un événement SSE : son genre, ses données en JSON sur une ligne."""
    return f"event: {genre}\ndata: {json.dumps(donnees, ensure_ascii=False)}\n\n"


def demande(accept: str | None) -> bool:
    """Le logiciel demande-t-il la réponse au fil de l'eau (en-tête Accept) ?"""
    return TYPE in (accept or "")


def decouper(tampon: str) -> tuple[str, str]:
    """Ce qui peut partir maintenant, et ce qui attend la suite : (à envoyer, à garder), avec
    à_envoyer + à_garder == tampon.

    La règle à tenir : un secret (clé, jeton, adresse de base, voir garde._SECRETS) peut arriver coupé entre deux
    morceaux du modèle ; aucune partie d'un secret ne doit partir avant que masquer_secrets l'ait vu en entier.
    Plus on garde, plus c'est sûr et moins c'est « en direct ».

    La coupe se fait au dernier blanc (espace, tabulation, retour à la ligne) : aucun motif de garde._SECRETS ne
    contient de blanc, un secret tient donc toujours dans un seul mot, et un mot ne part qu'une fois complet. Le
    texte part ainsi mot par mot ; un long passage sans blanc (une adresse web) attend le blanc suivant ou la fin.
    """
    coupe = max(tampon.rfind(blanc) for blanc in " \t\n\r")
    if coupe < 0:
        return "", tampon
    return tampon[: coupe + 1], tampon[coupe + 1 :]


class Masque:
    """Les morceaux d'une réponse, masqués avant de partir ; ce qui pourrait être le début d'un secret attend."""

    def __init__(self):
        self._tampon = ""

    def ajouter(self, morceau: str) -> str:
        """Un morceau du modèle ; rend ce qui peut partir tout de suite (peut-être rien)."""
        self._tampon += morceau
        sur, self._tampon = decouper(self._tampon)
        return self._propre(sur)

    def finir(self) -> str:
        """La fin du tour : tout ce qui restait, masqué."""
        reste, self._tampon = self._tampon, ""
        return self._propre(reste)

    @staticmethod
    def _propre(texte: str) -> str:
        return sans_artefacts(masquer_secrets(texte)) if texte else ""


class Relais:
    """Relaie les événements d'un tour vers `sur_evenement` (async f(genre, valeur)), le texte passé par le Masque.
    `finir()` à la fin du tour envoie ce qui restait."""

    def __init__(self, sur_evenement):
        self._sur_evenement, self._masque = sur_evenement, Masque()

    async def __call__(self, genre: str, valeur) -> None:
        if genre != "texte":
            await self._sur_evenement(genre, valeur)
        elif propre := self._masque.ajouter(valeur):
            await self._sur_evenement("texte", propre)

    async def finir(self) -> None:
        if reste := self._masque.finir():
            await self._sur_evenement("texte", reste)


@dataclass
class SortieDuFlux:
    """La sortie d'un tour en flux quand Agno ne l'a pas rendue elle-même."""

    content: str
    status: str = "COMPLETED"


async def suivre(evenements, sur_evenement):
    """Les événements d'un tour d'Agno en flux (`arun(stream=True, stream_events=True, yield_run_output=True)`) :
    les morceaux de texte, bruts, et les appels d'outils (leur nom seulement, jamais leurs arguments) partent à
    `sur_evenement` ; rend la sortie finale, celle qui a passé les crochets de sortie."""
    sortie, morceaux = None, []
    async for ev in evenements:
        genre = getattr(ev, "event", None)
        if genre is None:  # la sortie finale (RunOutput)
            sortie = ev
        elif genre == "RunContent" and isinstance(getattr(ev, "content", None), str) and ev.content:
            morceaux.append(ev.content)
            await sur_evenement("texte", ev.content)
        elif genre in ("ToolCallStarted", "ToolCallCompleted"):
            nom = getattr(getattr(ev, "tool", None), "tool_name", None)
            if nom:
                await sur_evenement("outil", {"outil": nom, "etat": "debut" if genre == "ToolCallStarted" else "fin"})
        elif genre == "RunError":
            sortie = SortieDuFlux("", "ERROR")
    return sortie if sortie is not None else SortieDuFlux("".join(morceaux))


_TACHES: set = set()


def _lancer(coro) -> asyncio.Task:
    """Une tâche gardée jusqu'à sa fin (asyncio ne garde qu'une référence faible)."""
    t = asyncio.create_task(coro)
    _TACHES.add(t)
    t.add_done_callback(_TACHES.discard)
    return t


async def diffuser(tour, conclure, lancer=_lancer):
    """Les événements SSE d'un tour.

    `tour(sur_evenement)` : la coroutine du tour, qui ne lève pas ; elle est lancée à part (`lancer`) pour aller au
    bout même si le logiciel raccroche. `conclure(resultat)` : le dernier événement, « fin » ou « erreur ».
    """
    file: asyncio.Queue = asyncio.Queue()

    async def sur_evenement(genre, valeur):
        await file.put((genre, valeur))

    async def tourner():
        await file.put(("", await tour(sur_evenement)))

    lancer(tourner())
    while True:
        try:
            genre, valeur = await asyncio.wait_for(file.get(), ATTENTE)
        except asyncio.TimeoutError:
            yield PING
            continue
        if genre == "texte":
            yield evenement("texte", {"texte": valeur})
        elif genre == "outil":
            yield evenement("outil", valeur)
        else:
            yield conclure(valeur)
            return


def en_reponse(evenements) -> StreamingResponse:
    """La réponse HTTP d'un flux : jamais gardée par un cache ni retenue par un relais."""
    return StreamingResponse(evenements, media_type=TYPE, headers={"cache-control": "no-store", "x-accel-buffering": "no"})
