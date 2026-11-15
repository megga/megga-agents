"""Ni point médian ni tiret long dans ce qu'un agent écrit (règle de Julien).

Repris d'Alix (typographie.js), sans changer un mot :
  deux tirets encadrant un aparté   -> des parenthèses ;
  un tiret entre deux nombres        -> un trait d'union (17:00-20:00) ;
  un tiret seul, un point médian     -> une virgule.
Et la mise en forme de WhatsApp : le gras s'y écrit avec une seule étoile.
"""

from __future__ import annotations

import re

TIRETS = "\u2014\u2013"
_PLAGE = re.compile(rf"(\d)\s?[{TIRETS}]\s?(\d)")
_PAIRE = re.compile(rf"\s?[{TIRETS}]\s?([^{TIRETS}.!?;\n]{{1,220}}?)\s?[{TIRETS}](\s?)")
_SEUL = re.compile(rf"[ \t]?[{TIRETS}][ \t]?")
_POINT = re.compile(r"[ \t]?\u00b7[ \t]?")
_DEBUT = re.compile(rf"^[{TIRETS}][ \t]?", re.M)


def sans_artefacts(texte):
    if not isinstance(texte, str) or not re.search(rf"[{TIRETS}\u00b7]", texte):
        return texte
    t = _PLAGE.sub(r"\1-\2", texte)
    t = _PAIRE.sub(lambda m: f" ({m.group(1).strip()}){m.group(2)}", t)
    t = re.sub(r" \)([,.])", r")\1", t)
    t = re.sub(r"\)(?=[^\W_])", ") ", t)
    t = _DEBUT.sub("", t)
    t = _SEUL.sub(", ", t)
    t = _POINT.sub(", ", t)
    return re.sub(r", ,|,,", ",", t)


def pour_whatsapp(texte):
    if not isinstance(texte, str):
        return texte
    t = re.sub(r"\*\*(\S(?:[^*\n]*\S)?)\*\*", r"*\1*", texte)
    t = re.sub(r"__(\S(?:[^_\n]*\S)?)__", r"_\1_", t)
    t = re.sub(r"^#{1,6}[ \t]+(.+?)[ \t]*$", r"*\1*", t, flags=re.M)
    t = re.sub(r"^[ \t]*[•*][ \t]+", "- ", t, flags=re.M)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def nettoyer(texte):
    """Ce qui part vers WhatsApp : sans artefacts, à la mise en forme de WhatsApp."""
    return pour_whatsapp(sans_artefacts(texte))


def crochet_typographie(run_output) -> None:
    """Crochet de sortie d'Agno : nettoie la réponse avant qu'elle ne parte."""
    if isinstance(getattr(run_output, "content", None), str):
        run_output.content = nettoyer(run_output.content)
