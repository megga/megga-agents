"""Le pilotage à distance d'une installation hors Cloudflare (chez le client, puis la zone suisse).

Toujours sortant : le pilote de l'installation (pilote/) appelle MEGGA en HTTPS ; rien n'entre
chez le client. Deux clés Ed25519, une par sens :
  - l'installation signe ses requêtes de sa propre clé, créée chez le client et jamais transmise ;
    MEGGA n'en garde que la partie publique, enregistrée à la mise en service ;
  - MEGGA signe ses ordres de la clé de pilotage de l'atelier, dont la partie publique est dans
    l'image (noyau/pilotage.pub). Elle est distincte de la clé des licences, qui reste hors ligne.

Un ordre est borné : une version de configuration de l'atelier (« config ») ou une version
d'image (« image », installée par le pilote si le client l'a permis). Aucune commande libre. L'installation le
vérifie (signature, client, numéro, échéance, contenu) avant de le noter.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from pydantic import ValidationError

from .config import Config, manques

CLE_PUBLIQUE = Path(__file__).with_name("pilotage.pub")
FORMAT = 1
GENRES = ("config", "image")
DUREE_ORDRE = 7 * 86400  # un ordre qui n'a pas servi dans la semaine ne vaut plus
FENETRE = 300  # l'heure d'une requête signée, à 5 minutes près
ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
NONCE = re.compile(r"^[0-9a-f]{32}$")
HEURE = re.compile(r"^[0-9]{1,12}$")
IMAGE = re.compile(r"^ghcr\.io/megga/megga-agents@sha256:[0-9a-f]{64}$")
VERSION_IMAGE = re.compile(r"^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}$")


class PilotageRefuse(ValueError):
    """Un ordre, une clé ou une requête qui ne passe pas ; le message dit pourquoi, sans rien de secret."""


def _b64(octets: bytes) -> str:
    return base64.urlsafe_b64encode(octets).decode().rstrip("=")


def _de_b64(texte: str) -> bytes:
    return base64.urlsafe_b64decode(texte + "=" * (-len(texte) % 4))


# Les clés


def cle_privee(texte: str):
    """Une clé privée Ed25519 : en PEM, ou sur une ligne en base64 (PKCS8, comme
    `openssl genpkey -algorithm ed25519 -outform DER | base64`, ou ses 32 octets bruts)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import load_der_private_key, load_pem_private_key

    texte = (texte or "").strip()
    try:
        if texte.startswith("-----BEGIN"):
            cle = load_pem_private_key(texte.encode(), password=None)
        else:
            brut = base64.b64decode(texte, validate=True)
            cle = Ed25519PrivateKey.from_private_bytes(brut) if len(brut) == 32 else load_der_private_key(brut, password=None)
    except Exception as e:  # base64, DER, PEM ou algorithme : une clé illisible, sans dire ce qu'elle contient
        raise PilotageRefuse("clé privée illisible : une clé Ed25519 est attendue") from e
    if not isinstance(cle, Ed25519PrivateKey):
        raise PilotageRefuse("clé privée : une clé Ed25519 est attendue")
    return cle


def cle_publique(texte: str):
    """Une clé publique Ed25519 : en PEM, ou sur une ligne en base64 (SubjectPublicKeyInfo, ou ses 32 octets)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.hazmat.primitives.serialization import load_der_public_key, load_pem_public_key

    texte = (texte or "").strip() if isinstance(texte, str) else ""
    try:
        if texte.startswith("-----BEGIN"):
            cle = load_pem_public_key(texte.encode())
        else:
            brut = base64.b64decode(texte, validate=True)
            cle = Ed25519PublicKey.from_public_bytes(brut) if len(brut) == 32 else load_der_public_key(brut)
    except Exception as e:
        raise PilotageRefuse("clé publique illisible : une clé Ed25519 est attendue") from e
    if not isinstance(cle, Ed25519PublicKey):
        raise PilotageRefuse("clé publique : une clé Ed25519 est attendue")
    return cle


def en_texte(cle) -> str:
    """Une clé publique sur une ligne (base64 de son SubjectPublicKeyInfo), à remettre ou à garder."""
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    return base64.b64encode(cle.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)).decode()


def empreinte(ligne: str) -> str:
    """L'empreinte courte d'une clé publique : pour la reconnaître des deux côtés, sans la recopier."""
    return hashlib.sha256(base64.b64decode(ligne)).hexdigest()[:16]


def cle_megga(pem: bytes | None = None):
    """La clé publique de pilotage de MEGGA, dans l'image ; sans elle, aucun ordre n'est accepté."""
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if pem is None:
        if not CLE_PUBLIQUE.exists():
            raise PilotageRefuse("clé publique de pilotage absente de l'image (scripts/pilotage.py cle)")
        pem = CLE_PUBLIQUE.read_bytes()
    try:
        cle = load_pem_public_key(pem)
    except ValueError as e:
        raise PilotageRefuse("clé publique de pilotage illisible") from e
    if not isinstance(cle, Ed25519PublicKey):
        raise PilotageRefuse("clé publique de pilotage : une clé Ed25519 est attendue")
    return cle


# Les ordres de MEGGA


def signer(donnees: dict, cle) -> str:
    """Un jeton signé, comme une licence : « <données>.<signature> », en base64."""
    brut = json.dumps(donnees, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return f"{_b64(brut)}.{_b64(cle.sign(brut))}"


def contenu(jeton: str) -> dict:
    """Les données d'un jeton, SANS vérifier sa signature : pour l'afficher, jamais pour agir."""
    try:
        d = json.loads(_de_b64(str(jeton).split(".")[0]))
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def ordre(client: str, numero: int, genre: str, donnees: dict, cle, quand: float) -> str:
    """Un ordre signé par MEGGA (dans l'atelier seulement)."""
    if genre not in GENRES:
        raise ValueError(f"genre d'ordre inconnu : {genre}")
    return signer({"format": FORMAT, "client": client, "numero": numero, "genre": genre, "cree": int(quand),
                   "expire": int(quand) + DUREE_ORDRE, "contenu": donnees}, cle)


def ouvrir_ordre(jeton: str, client: str, cle=None) -> dict:
    """Un ordre signé par MEGGA pour ce client : signature, format, client et numéro vérifiés."""
    from cryptography.exceptions import InvalidSignature

    if not isinstance(jeton, str) or jeton.count(".") != 1:
        raise PilotageRefuse("ordre mal formé")
    cle = cle or cle_megga()
    partie, signature = jeton.split(".")
    try:
        brut = _de_b64(partie)
        cle.verify(_de_b64(signature), brut)
        d = json.loads(brut)
    except InvalidSignature as e:
        raise PilotageRefuse("ordre non signé par MEGGA") from e
    except ValueError as e:
        raise PilotageRefuse("ordre mal formé") from e
    if not isinstance(d, dict) or d.get("format") != FORMAT:
        raise PilotageRefuse("format d'ordre inconnu")
    if d.get("client") != client:
        raise PilotageRefuse("ordre pour un autre client")
    for k in ("numero", "cree", "expire"):
        if isinstance(d.get(k), bool) or not isinstance(d.get(k), int) or d[k] < 1:
            raise PilotageRefuse(f"ordre sans {k} valable")
    return d


def valider_ordre(d: dict, base: Config, maintenant: float | None = None) -> None:
    """Un ordre ouvert est-il recevable ici : son genre, son contenu borné et, si `maintenant`, son échéance."""
    if maintenant is not None and maintenant > d["expire"]:
        raise PilotageRefuse("ordre expiré")
    if d.get("genre") == "config":
        config_de(d, base)
    elif d.get("genre") == "image":
        c = d.get("contenu") if isinstance(d.get("contenu"), dict) else {}
        if not (isinstance(c.get("version"), str) and VERSION_IMAGE.fullmatch(c["version"])
                and isinstance(c.get("image"), str) and IMAGE.fullmatch(c["image"])):
            raise PilotageRefuse("image proposée : une version et l'image de MEGGA, par son empreinte")
    else:
        raise PilotageRefuse("genre d'ordre inconnu")


def lire_ordre(jeton: str, base: Config, cle=None, maintenant: float | None = None) -> dict:
    """Un ordre de MEGGA pour cette installation, entièrement vérifié."""
    d = ouvrir_ordre(jeton, base.id, cle)
    valider_ordre(d, base, maintenant)
    return d


def config_de(ordre: dict, base: Config) -> tuple[int, Config]:
    """La version et la configuration d'un ordre « config » : validée par le noyau, complète,
    du même client et de la même zone que l'installation (changer de zone, c'est déménager)."""
    c = ordre.get("contenu") if isinstance(ordre.get("contenu"), dict) else {}
    version = c.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise PilotageRefuse("ordre sans numéro de version")
    try:
        conf = Config.model_validate(c.get("config"))
    except ValidationError as e:
        raise PilotageRefuse("configuration invalide") from e
    if conf.id != base.id:
        raise PilotageRefuse("configuration d'un autre client")
    if conf.zone != base.zone:
        raise PilotageRefuse(f"configuration de la zone {conf.zone}, installation en zone {base.zone}")
    if manques(conf):
        raise PilotageRefuse("configuration incomplète : " + "; ".join(manques(conf)))
    return version, conf


def config_a_envoyer(conf: Config) -> dict:
    """La configuration d'un ordre : sans les réglages laissés à leur valeur par défaut, pour qu'une installation
    restée sur l'image précédente l'accepte encore quand un réglage facultatif s'ajoute (deux versions soutenues).
    Règle qui va avec : ne jamais changer une valeur par défaut sans changer VERSION."""
    return {"version": conf.version, **conf.model_dump(mode="json", exclude_defaults=True)}


def configuration_servie(base: Config, servie: dict | None, cle=None) -> tuple[Config, dict | None, str | None]:
    """La configuration que l'agent sert : la dernière poussée par MEGGA et acceptée, revérifiée, sinon le
    fichier du client. Rend aussi sa source ({version, ordre}, ou None pour le fichier) et, si l'ordre
    ne passe plus la vérification, pourquoi."""
    if not servie:
        return base, None, None
    try:
        o = lire_ordre(servie["jeton"], base, cle)
        if o["genre"] != "config":
            raise PilotageRefuse("ordre sans configuration")
        version, conf = config_de(o, base)
        return conf, {"version": version, "ordre": o["numero"]}, None
    except PilotageRefuse as e:
        return base, None, str(e)


# Les requêtes signées de l'installation


def _a_signer(methode: str, chemin: str, client: str, heure: str, nonce: str, corps: bytes) -> bytes:
    """Ce que signe l'installation : la requête, l'installation qu'elle dit être, l'heure, le nonce et le corps."""
    return "\n".join((methode.upper(), chemin, client, heure, nonce, hashlib.sha256(corps).hexdigest())).encode()


def entetes(client: str, cle, methode: str, chemin: str, corps: bytes, maintenant: float | None = None) -> dict[str, str]:
    """Les en-têtes d'une requête signée par l'installation : qui, quand, un nonce, la signature."""
    heure = str(int(time.time() if maintenant is None else maintenant))
    nonce = secrets.token_hex(16)
    return {"x-megga-installation": client, "x-megga-heure": heure, "x-megga-nonce": nonce,
            "x-megga-signature": _b64(cle.sign(_a_signer(methode, chemin, client, heure, nonce, corps)))}


def verifier_requete(en_tetes: Mapping[str, str], methode: str, chemin: str, corps: bytes,
                     cle_de: Callable[[str], Any], maintenant: float | None = None) -> tuple[str, str]:
    """Le client et le nonce d'une requête signée par une installation enregistrée ; lève PilotageRefuse sinon.

    Reste à l'appelant de refuser un nonce déjà vu : une requête rejouée dans la fenêtre a le même.
    """
    from cryptography.exceptions import InvalidSignature

    client = en_tetes.get("x-megga-installation") or ""
    heure = en_tetes.get("x-megga-heure") or ""
    nonce = en_tetes.get("x-megga-nonce") or ""
    signature = en_tetes.get("x-megga-signature") or ""
    if not (ID.fullmatch(client) and HEURE.fullmatch(heure) and NONCE.fullmatch(nonce) and signature):
        raise PilotageRefuse("requête non signée")
    if abs((time.time() if maintenant is None else maintenant) - int(heure)) > FENETRE:
        raise PilotageRefuse("heure de la requête hors fenêtre : l'horloge de l'installation est-elle juste ?")
    cle = cle_de(client)
    if cle is None:
        raise PilotageRefuse("installation inconnue ou révoquée")
    try:
        cle.verify(_de_b64(signature), _a_signer(methode, chemin, client, heure, nonce, corps))
    except (InvalidSignature, ValueError) as e:
        raise PilotageRefuse("signature refusée") from e
    return client, nonce


def sans_donnees(texte: Any) -> str:
    """Un détail technique qui sort de l'installation : secrets masqués, et aucun numéro (8 chiffres ou plus)."""
    from .garde import masquer_secrets

    return re.sub(r"\+?\d(?: ?\d){7,}", "[numéro]", masquer_secrets(str(texte or "")))[:200]
