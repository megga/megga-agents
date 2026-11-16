"""Les rappels, seulement à la demande : « rappelle-moi jeudi à 9 h de relancer M. X ».

Jamais de message spontané. Pas de rappels dans une conversation par API (noyau/api.py) : personne ne les recevrait. Chaque outil agit pour la personne qui parle
(run_context.user_id, posé par le noyau) et ne voit jamais les rappels d'une autre.
À l'heure dite, la porte réveille le conteneur, qui envoie le rappel :
dans les 24 heures de WhatsApp, un message libre ; au-delà, le modèle Meta
« rappel » s'il est configuré ; sinon il part avant la réponse au prochain message.
"""

from __future__ import annotations

import datetime as dt
import time
from zoneinfo import ZoneInfo

from agno.run import RunContext

MAX_TEXTE = 500
MAX_PAR_PERSONNE = 50
UN_AN = 366 * 24 * 3600


def lire_quand(quand: str, fuseau: str, maintenant: float | None = None) -> float:
    """Une date et une heure ISO (« 2026-11-20T09:00 ») ; sans fuseau, celle du client."""
    try:
        d = dt.datetime.fromisoformat(str(quand).strip())
    except ValueError:
        raise ValueError("date illisible : donne-la au format AAAA-MM-JJTHH:MM") from None
    if d.tzinfo is None:
        d = d.replace(tzinfo=ZoneInfo(fuseau))
    t = d.timestamp()
    maintenant = maintenant or time.time()
    if t < maintenant + 60:
        raise ValueError("cette heure est déjà passée")
    if t > maintenant + UN_AN:
        raise ValueError("plus d'un an à l'avance : trop loin")
    return t


def outils(rappels, fuseau: str):
    """Les outils de rappel pour l'agent, liés à la table et au fuseau du client."""
    tz = ZoneInfo(fuseau)

    def _qui(run_context: RunContext) -> str:
        if not run_context or not run_context.user_id:
            raise ValueError("personne inconnue")
        if run_context.user_id.startswith("api:"):
            # Par API, personne ne recevrait le rappel (un appel vers le logiciel viendra s'il le faut).
            raise ValueError("les rappels ne sont pas disponibles dans cette conversation : dis-le simplement")
        return run_context.user_id

    def rappeler(quand: str, quoi: str, run_context: RunContext) -> str:
        """Programme un rappel demandé par la personne.

        Args:
            quand: la date et l'heure du rappel, au format AAAA-MM-JJTHH:MM, à l'heure locale du client.
            quoi: ce qu'il faut rappeler, en quelques mots.
        """
        personne = _qui(run_context)
        texte = " ".join(str(quoi).split())[:MAX_TEXTE]
        if not texte:
            raise ValueError("rien à rappeler")
        if len(rappels.lister(personne)) >= MAX_PAR_PERSONNE:
            raise ValueError("trop de rappels en attente : annule-en d'abord")
        t = lire_quand(quand, fuseau)
        ident = rappels.ajouter(personne, t, texte)
        heure = dt.datetime.fromtimestamp(t, tz).strftime("%d.%m.%Y à %H:%M")
        return f"Rappel {ident} programmé le {heure} : {texte}"

    def mes_rappels(run_context: RunContext) -> str:
        """Liste les rappels en attente de la personne."""
        lignes = rappels.lister(_qui(run_context))
        if not lignes:
            return "Aucun rappel en attente."
        return "\n".join(
            f"{l['id']} : {dt.datetime.fromtimestamp(l['quand'], tz).strftime('%d.%m.%Y à %H:%M')}, {l['texte']}" for l in lignes
        )

    def annuler_rappel(identifiant: str, run_context: RunContext) -> str:
        """Annule un rappel de la personne, d'après son identifiant (donné par mes_rappels).

        Args:
            identifiant: l'identifiant du rappel.
        """
        if rappels.annuler(_qui(run_context), str(identifiant).strip()):
            return "Rappel annulé."
        return "Aucun rappel en attente avec cet identifiant."

    return [rappeler, mes_rappels, annuler_rappel]
