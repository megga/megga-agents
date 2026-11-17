"""Les phrases du noyau et ce qu'il dit au modèle autour d'un tour (parité avec Alix FSP, relecture du 17.11.2026).

- Les phrases fixes (excuse, vocal non compris, rappel ; « trop de messages » est dans garde.py), au vouvoiement ou
  au tutoiement selon le rôle (Role.tutoiement, M4).
- Une réponse vide ou coupée au milieu d'une phrase : un dernier appel, sans outil (agent.js d'Alix : FINIR, REPRENDRE ;
  M1, M2).
- Le vocal : la transcription marquée, la réponse qui sera dite, l'écrit demandé ou accepté (conversation.js ; M5).
"""

from __future__ import annotations

import re

# (vouvoiement, tutoiement)
EXCUSE = ("Je rencontre un petit souci technique. Je reviens vers vous dès que possible.",
          "Je n'ai pas pu traiter ta demande. Réessaie dans un instant.")
NON_COMPRIS = ("Je n'ai pas pu écouter ce vocal. Pouvez-vous me l'écrire ?",
               "Je n'ai pas pu écouter ce vocal. Tu peux me l'écrire ?")


def phrase(paire: tuple[str, str], tutoiement: bool) -> str:
    return paire[1] if tutoiement else paire[0]


def rappel(quoi: str, tutoiement: bool) -> str:
    """Le texte d'un rappel, tel qu'il part : « Rappel : … » ; au tutoiement, comme Alix FSP le disait (initiative.js)."""
    quoi = str(quoi or "").strip()
    if tutoiement:
        return f"Rappel, comme tu me l'avais demandé : {quoi.rstrip('. ')}."
    return f"Rappel : {quoi}"


# Une réponse doit finir ses phrases (Julien, 14.11.2026 : « Oui je transmets votre », puis plus rien).
_LIAISON = re.compile(r"\b(le|la|les|l'|un|une|des|du|de|d'|votre|vos|ton|ta|tes|son|sa|ses|mon|ma|mes|notre|nos|leur|et|ou|mais|"
                      r"pour|par|avec|dans|sur|à|au|aux|en|que|qui|je|tu|il|elle|nous|vous|the|a|an|your|our|and|or|to|of|for|"
                      r"with|el|los|las|su|sus|y|o|para|con)$", re.I)
_FIN_PROPRE = re.compile(r"[.!?…»\")\]*_~]$|[\U0001F000-\U0001FAFF☀-➿]️?$")
_LIEN_FINAL = re.compile(r"https?://\S+$|www\.\S+$")


def inacheve(texte: str) -> bool:
    """Vrai si un texte s'arrête au milieu d'une phrase (vide compris)."""
    t = str(texte or "").strip()
    if not t:
        return True
    if _LIEN_FINAL.search(t) or _FIN_PROPRE.search(t):
        return False
    return bool(_LIAISON.search(t)) or t[-1] in ",;:-" or t[-1].isalpha()


FINIR = ("[Consigne du système : réponds maintenant à la personne, en un message complet, sans outil. Chaque phrase va jusqu'au "
         "bout et se termine par un point, un point d'interrogation ou d'exclamation.]")
REPRENDRE = ("[Consigne du système : ta dernière réponse s'arrête au milieu d'une phrase. Réécris-la en entier, dans la même "
             "langue, avec les mêmes faits, en phrases complètes et bien construites, sans outil.]")

# Le vocal (conversation.js d'Alix FSP). Après un vocal, l'écrit ne suit que sur demande (Julien, 12.11.2026 : « si
# j'envoie un vocal, vocal seul ») : « envoie-le par écrit », ou un oui à la proposition du vocal précédent.
PAR_ECRIT = re.compile(r"\b(?:par|en) [ée]crit\b|\b[ée]cri(?:s|vez)[- ]?(?:le|la|les|moi)\b|\ben texte\b|\btexto\b|\bin writing\b|"
                       r"\bwrite (?:it|that|them) (?:down|out)?|\btext (?:me|it)\b|\bpor escrito\b", re.I)
OUI = re.compile(r"^\W*(?:oui|ouais|volontiers|vas-y|allez-y|d'accord|ok|okay|avec plaisir|yes|yeah|sure|please|s[ií]|claro|vale)\b", re.I)
OFFRE_ECRIT = re.compile(r"(?:par [ée]crit|in writing|por escrito)[^.!?]*\?", re.I)

TRANSCRIT = "[Message vocal, transcrit automatiquement :] "
NON_TRANSCRIT = "[Un message vocal, qui n'a pas pu être transcrit.]"
VOCAL_DIT = "[Ta réponse sera dite dans un message vocal : va à l'essentiel, comme au téléphone.]"
VOCAL_ECRIT = "[La personne veut le détail par écrit : donne-le en entier et bien présenté ; il partira aussi par écrit, après le vocal.]"
ECRIT_ACCEPTE = "[La personne accepte le détail par écrit que tu lui as proposé : donne-le en entier et bien présenté.]"


def piece(genre_lu: str) -> str:
    """Une pièce que l'agent ne peut pas ouvrir (une position, un autocollant), telle que le modèle la lit (D13)."""
    return f"[La personne a envoyé {genre_lu}, que tu ne peux pas ouvrir.]"
