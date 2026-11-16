"""L'accueil d'un rôle (Role.accueil) : le premier message à une personne, mot pour mot (repris d'accueil.js
d'Alix FSP).

Le noyau l'envoie lui-même au premier message d'une conversation (rien d'elle depuis douze heures), dès que sa
langue est sûrement l'une de celles de l'accueil ; sinon le modèle le traduit (sa consigne le dit). Seule retouche
permise : son prénom, celui du nom de son profil WhatsApp s'il ressemble à un vrai prénom. À une simple
salutation, l'accueil seul ; à une vraie demande, l'accueil puis la réponse, sans rien qui le redise.
"""

from __future__ import annotations

import re
import unicodedata

INACTIVITE = 12 * 3600  # une conversation recommence après douze heures sans message de la personne
APRES_ACCUEIL = ("[L'accueil vient de partir tel quel, envoyé par le système : ne le redis pas et ne salue pas de nouveau ; "
                 "réponds seulement à sa demande.]")

_ENTREPRISE = re.compile(r"\b(immo\w*|real\s*estate|propert\w*|realty|homes?|invest\w*|group|groupe|agency|agence|consult\w*|capital|"
                         r"holding|sarl|s\.?a\.?|ltd|llc|gmbh|inc|ag|official|shop|store|services?|studio|team|office|bureau|hotel|"
                         r"restaurant|travel|luxury|estates?|international|management|partners?|associ\w*|company|compagnie|"
                         r"foundation|fondation)\b", re.I)
_PAS_UN_PRENOM = {"mr", "mrs", "ms", "mme", "mlle", "m", "dr", "monsieur", "madame", "sir", "papa", "maman", "mom", "mum", "dad", "boss",
                  "chef", "love", "amour", "bebe", "bébé", "baby", "moi", "me", "admin", "contact", "info", "client", "whatsapp", "user",
                  "test", "ok", "hello", "bonjour", "hi", "the", "le", "la", "les", "mister", "miss"}
_MOTS = {
    "fr": re.compile(r"[àâçéèêëîïôûùüÿœ]|\b(le|la|les|des|du|est|vous|je|nous|une|pour|avec|dans|sur|pas|bonjour|bonsoir|salut|coucou|"
                     r"merci|c'est|j'ai|cherche|appartement|maison|acheter|louer|vendre)\b", re.I),
    "en": re.compile(r"\b(the|and|you|your|is|are|for|with|this|that|hello|hi|hey|good morning|good afternoon|good evening|thanks|"
                     r"thank you|it's|i'm|i am|have|will|looking|want|buy|rent|sell|house|flat|apartment)\b", re.I),
}
_AUTRES = re.compile(r"[¿¡ñßäöåøæąęłńśźżčřšž]|\b(hola|gracias|buenos|buenas|quiero|busco|una|el|los|las|ciao|buongiorno|grazie|cerco|"
                     r"guten|hallo|ich|und|suche|danke|ola|olá|obrigad[oa]|privet|merhaba|salam|marhaba)\b", re.I)
_SALUT = re.compile(r"^[\W_]*(hi|hello|hey|hola|bonjour|bonsoir|salut|coucou|good (morning|afternoon|evening)|buenos d[ií]as|"
                    r"buenas( tardes| noches)?)\b[\W_]*(\w{2,12})?[\W_]*$", re.I)
_SALUT_EN_TETE = re.compile(r"^(good (morning|afternoon|evening)|hello|hi|hey|bonjour|bonsoir|salut)\b[^,.!?\n]{0,30}[,.!]\s*", re.I)


def prenom_du_profil(nom: str | None) -> str | None:
    """Le prénom tiré du nom d'un profil WhatsApp, ou None : des lettres seulement, quatre mots au plus, ni une
    entreprise, ni un titre, ni un surnom courant, ni une initiale. « marc dupont » donne Marc."""
    t = " ".join(unicodedata.normalize("NFC", str(nom or "")).split())
    if not t or len(t) > 60 or _ENTREPRISE.search(t):
        return None
    if not all(c.isalpha() or c in " '’.-" or unicodedata.category(c).startswith("M") for c in t) or not t[0].isalpha():
        return None
    mots = t.split(" ")
    premier = mots[0]
    if len(mots) > 4 or "." in premier or len(premier.replace("-", "")) < 2 or len(premier) > 20:
        return None
    if premier.lower() in _PAS_UN_PRENOM:
        return None
    return "-".join(p[:1].upper() + p[1:].lower() for p in premier.split("-"))


def langue_sure(texte: str, langues) -> str | None:
    """La langue du message si elle est sûrement l'une de celles-ci (français ou anglais), sinon None."""
    comptes = {l: len(_MOTS[l].findall(texte or "")) for l in langues if l in _MOTS}
    if not comptes:
        return None
    autres = len(_AUTRES.findall(texte or ""))
    meilleure = max(comptes, key=comptes.get)
    if comptes[meilleure] == 0 or autres >= comptes[meilleure] or list(comptes.values()).count(comptes[meilleure]) > 1:
        return None
    return meilleure


def est_salutation(texte: str) -> bool:
    """Une simple salutation (« Hello », « Bonjour Alix ! ») : l'accueil y répond seul."""
    return bool(_SALUT.match((texte or "").strip()))


def texte_accueil(accueil: dict[str, str], langue: str, prenom: str | None) -> str:
    """L'accueil dans cette langue, avec le prénom après son premier mot (« Bonjour Marc, … »)."""
    t = accueil[langue]
    if not prenom:
        return t
    return re.sub(r"^(\w+)([,!])", lambda m: f"{m.group(1)} {prenom}{m.group(2)}", t, count=1)


def apres_accueil(reponse: str, accueil: str) -> str:
    """La réponse du modèle après l'accueil envoyé : sans les paragraphes qui le redisent, sans salutation en tête."""
    def plat(p: str) -> str:
        return " ".join(re.sub(r"[^\w\s]", " ", p.lower()).split())

    redits = {plat(p) for p in re.split(r"\n\s*\n", accueil) if p.strip()}
    paragraphes = [p.strip() for p in re.split(r"\n\s*\n", reponse or "") if p.strip()]
    gardes = [p for p in paragraphes if plat(p) not in redits and not any(r and r in plat(p) for r in redits)]
    if gardes:
        reste = _SALUT_EN_TETE.sub("", gardes[0], count=1)
        gardes[0] = reste[:1].upper() + reste[1:] if reste != gardes[0] else reste
    return "\n\n".join(p for p in gardes if p)
