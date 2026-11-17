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


# Un lien ou une adresse e-mail ne se touche pas : « gregory.x@agence.ch » reste joignable.
_INTOUCHABLE = re.compile(r"https?://\S+|www\.\S+|[\w.+-]+@[\w-]+\.[\w.-]+", re.I)
# Les champs techniques d'un message pour Meta : destinataire, identifiants, liens, charges.
_TECHNIQUES = {"to", "id", "link", "url", "message_id", "payload", "flow_id", "flow_token", "messaging_product", "type",
               "recipient_type", "code", "name", "sub_type", "index", "status", "screen", "flow_action", "flow_message_version"}


class Remplaceur:
    """Les remplacements au point d'envoi (Config.remplacements) : chaque texte qui part, sans exception (Alix FSP,
    meta.js : jamais un nom de famille, ni dans un texte, ni dans une variable de modèle, une légende ou une liste).
    Sans remplacement, rien ne change."""

    def __init__(self, regles=()):
        self._regles = [(re.compile(r.motif, re.I), r.par) for r in regles]

    def __bool__(self) -> bool:
        return bool(self._regles)

    def _un(self, texte: str) -> str:
        for motif, par in self._regles:
            texte = motif.sub(par, texte)
        if any(not par for _, par in self._regles):  # ce qui disparaît ne laisse ni double espace ni espace avant la ponctuation
            texte = re.sub(r"[ \t]{2,}", " ", texte)
            texte = re.sub(r"[ \t]+([,.!?;:])", r"\1", texte)
        return texte

    def texte(self, texte):
        if not self._regles or not isinstance(texte, str) or not texte:
            return texte
        morceaux, fin = [], 0
        for m in _INTOUCHABLE.finditer(texte):
            morceaux += [self._un(texte[fin:m.start()]), m.group(0)]
            fin = m.end()
        return "".join([*morceaux, self._un(texte[fin:])])

    def profond(self, valeur, cle: str = ""):
        """Chaque texte d'un message, à toute profondeur, sauf les champs techniques (destinataire, liens, identifiants)."""
        if not self._regles:
            return valeur
        if isinstance(valeur, str):
            return valeur if cle in _TECHNIQUES else self.texte(valeur)
        if isinstance(valeur, list):
            return [self.profond(v, cle) for v in valeur]
        if isinstance(valeur, dict):
            return {k: self.profond(v, k) for k, v in valeur.items()}
        return valeur
