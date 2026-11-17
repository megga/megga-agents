"""Ce que l'agent dit dans un vocal.

Sa réponse est d'abord écrite pour WhatsApp ; lue telle quelle, elle sonne comme
un e-mail récité. Avant la voix, un modèle la réécrit pour l'oral : mêmes faits,
même langue, dite comme on parle. Repris d'Alix (oral.js), rendu générique : le
nom de l'agent et l'entreprise viennent de la configuration du client.
"""

from __future__ import annotations

import logging

from .config import Config
from .typographie import sans_artefacts
from .voix import balises_permises, d_un_tenant, sans_balises

log = logging.getLogger("megga")

CONSIGNES = """Tu écris ce que {nom} va dire dans un message vocal WhatsApp. {nom} travaille pour {entreprise}. On te donne ce que la personne vient de dire, puis la réponse que {nom} a écrite : tu en fais une réplique parlée, comme une vraie personne au téléphone.

Le fond : exactement les mêmes faits que la réponse écrite, dans la même langue. Rien d'ajouté, rien d'inventé, aucun chiffre changé.

Une parole qui coule :
- Des phrases complètes, de longueur variée, reliées par les mots de la conversation, comme on parle à quelqu'un qu'on connaît. Jamais une suite de petites phrases sèches.
- Un seul paragraphe, sans retour à la ligne, sans points de suspension, sans tirets.
- Jamais d'énumération sèche : au plus trois éléments dans une vraie phrase ; au-delà, dis combien il y en a et les deux plus parlants, et propose d'envoyer le détail par écrit.
- Termine, quand c'est utile, par une seule question simple qui fait avancer, jamais par une formule de politesse.
- Le ton : {ton}.

Selon la situation :
- C'est fait, oui, non : une phrase vivante, parfois deux.
- Une confirmation à demander : ce qui va se passer, puis la question, claire.
- Une réponse écrite longue : seulement l'essentiel, puis propose le détail par écrit.
- Une demande hors de ce que {nom} sait faire : dis simplement, avec chaleur, que tu ne peux pas t'en occuper.
- Une erreur : calme, ce qui n'a pas marché, et la suite.
- Une salutation, un merci : court et chaleureux.

La langue parlée, sans faute : accords justes ; nombres, dates et heures en toutes lettres ; unités comme on les dit (« francs » et non « CHF »). Ne lis jamais un lien, un e-mail ou un numéro de téléphone : dis que tu l'écris.

À bannir : listes, parenthèses, guillemets, deux-points, émojis, formules d'e-mail ou de service client (« n'hésitez pas », « je reste à votre disposition », « certainly », « feel free to »), plus d'une exclamation.

Longueur : 15 à 45 secondes, soit 40 à 110 mots.

Rends seulement le texte à dire, d'un seul paragraphe, sans rien autour."""


REFERENCES = "\n\nNe lis jamais une référence (de bien, de dossier, comme G8LR-2DW8) : dis que tu l'écris, elle partira par écrit après le vocal."

BALISES = ("\n\nTa voix sait jouer des indications entre crochets, en anglais, placées juste avant la phrase qu'elles colorent : {liste}. "
           "Au plus une par réplique, au début d'une phrase, seulement quand elle sert le ton (par exemple [softly] pour une "
           "personne fatiguée, [cheerfully] pour une bonne nouvelle) ; le plus souvent aucune. Jamais d'autre crochet.")


def consignes(config: Config) -> str:
    """La consigne de la réécriture : celle du client (Oral.consignes) ou celle du noyau, avec les références qui ne se
    lisent pas et les indications de jeu de sa voix, s'il en a."""
    base = config.oral.consignes.strip() or CONSIGNES.format(nom=config.nom_agent, entreprise=config.entreprise, ton=config.ton)
    if config.oral.references and not config.oral.consignes.strip():
        base += REFERENCES
    if config.voix.balises:
        base += BALISES.format(liste=", ".join(f"[{b}]" for b in config.voix.balises))
    return base


async def pour_la_voix(reecrire, ecrit: str, entendu: str = "", auditeur: str = "", balises=()) -> str:
    """`reecrire(consigne_utilisateur) -> str` appelle le modèle ; l'écrit reste si quoi que ce soit échoue. `auditeur` :
    ce que l'oral sait de plus de la personne (Role.oral) ; `balises` : les indications de jeu permises (Voix.balises)."""
    if not ecrit:
        return ecrit
    demande = (f"À qui tu parles : {auditeur.strip()}\n" if auditeur.strip() else "") + \
        (f"La personne : « {entendu[:1500]} »\n" if entendu else "") + f"Écrit : « {ecrit} »"
    try:
        dit = str(await reecrire(demande) or "").strip().strip("\"«»\u201c\u201d ").strip()
    except Exception as e:
        log.error("oral : %s", str(e)[:200])
        return ecrit
    if len(dit) < 2 or len(dit) > 1200:
        return ecrit
    dit = balises_permises(dit, balises) if balises else sans_balises(dit)
    return d_un_tenant(sans_artefacts(dit))
