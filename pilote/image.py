"""Les mises à jour de l'image, vues du pilote : la signature, la sauvegarde, et l'exécutant Kubernetes.

La signature : l'image proposée par MEGGA est vérifiée avec la clé publique cosign de MEGGA, dans
l'image (noyau/cosign.pub, copiée de socle/cosign.pub à la construction). Le pilote lit lui-même la
signature dans le registre (le format de cosign 2 : l'étiquette sha256-<empreinte>.sig), sans cosign.
C'est une seconde clé, indépendante de celle des ordres : un ordre signé ne suffit pas, l'image
doit l'être aussi.

La sauvegarde : avant chaque mise à jour, la base entière, par l'export de MEGGA (stockage.exporter),
compressée, dans le dossier des sauvegardes ; les GARDEES plus récentes restent.

L'exécutant Kubernetes : le pilote ne peut que lire et changer l'image de deux Deployments nommés,
celui de l'agent et le sien (un Role limité à ces deux noms, installation/helm). Sous Compose, il
n'a aucun droit : c'est le script de l'hôte qui remplace l'image (installation/compose/mettre_a_jour.sh).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from noyau import pilotage, stockage

DEPOT = "ghcr.io/megga/megga-agents"
CLE_IMAGE = Path(pilotage.__file__).with_name("cosign.pub")
EMPREINTE = re.compile(r"^sha256:[0-9a-f]{64}$")
NOM_DEPOT = re.compile(r"^[a-z0-9]+([.-][a-z0-9]+)*(:[0-9]{1,5})?(/[a-z0-9]+([._-][a-z0-9]+)*)+$")
GARDEES = 3  # les sauvegardes d'avant mise à jour gardées
TYPE_SIGNATURE = "application/vnd.dev.cosign.simplesigning.v1+json"
ANNOTATION = "dev.cosignproject.cosign/signature"
MANIFESTES = ", ".join(("application/vnd.oci.image.manifest.v1+json",
                        "application/vnd.docker.distribution.manifest.v2+json"))


class ImageRefusee(pilotage.PilotageRefuse):
    """L'image ne passe pas : sans signature de MEGGA, ou autre que celle de l'ordre. Définitif."""


class RegistreInjoignable(RuntimeError):
    """Le registre ne répond pas ou refuse l'accès : on réessaie au relevé suivant."""


def empreinte_de(image: str) -> str:
    """L'empreinte (sha256:…) d'une image de MEGGA nommée par un ordre."""
    if not pilotage.IMAGE.fullmatch(image or ""):
        raise ImageRefusee("image : celle de MEGGA, par son empreinte")
    return image.split("@", 1)[1]


def depot(valeur: str | None) -> str:
    """Le dépôt d'où tirer l'image : celui de MEGGA, ou un miroir du client (MEGGA_DEPOT)."""
    v = (valeur or DEPOT).strip().lower()
    if not NOM_DEPOT.fullmatch(v):
        raise RuntimeError("MEGGA_DEPOT : un dépôt d'images, par exemple ghcr.io/megga/megga-agents")
    return v


def reference(image: str, depot_: str) -> str:
    """L'image d'un ordre, tirée du dépôt de l'installation : même empreinte, donc même contenu."""
    return f"{depot_}@{empreinte_de(image)}"


def adresse_registre(depot_: str, url: str | None = None) -> tuple[str, str]:
    """L'adresse HTTPS du registre et le chemin du dépôt. `url` (MEGGA_REGISTRE_URL) : le registre joint
    autrement que par son nom (un essai, un proxy) ; http seulement vers un nom local."""
    hote, chemin = depot_.split("/", 1)
    if not url:
        return f"https://{hote}", chemin
    u = urlsplit(url.strip())
    local = bool(re.fullmatch(r"[a-z][a-z0-9-]{0,62}", u.hostname or "")) or u.hostname == "127.0.0.1"
    if not ((u.scheme == "https" and u.hostname) or (u.scheme == "http" and local)):
        raise RuntimeError("MEGGA_REGISTRE_URL : une adresse https")
    return url.strip().rstrip("/"), chemin


# La signature


def cle_image(pem: bytes | None = None):
    """La clé publique cosign de MEGGA (ECDSA P-256), dans l'image ; sans elle, aucune mise à jour."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    if pem is None:
        if not CLE_IMAGE.exists():
            raise ImageRefusee("clé de signature des images absente de cette image (scripts/cle_signature.sh)")
        pem = CLE_IMAGE.read_bytes()
    try:
        cle = load_pem_public_key(pem)
    except ValueError as e:
        raise ImageRefusee("clé de signature des images illisible") from e
    if not isinstance(cle, ec.EllipticCurvePublicKey):
        raise ImageRefusee("clé de signature des images : une clé cosign (ECDSA) est attendue")
    return cle


class Registre:
    """Juste ce qu'il faut pour lire une signature : un jeton de lecture, un manifeste, un petit blob."""

    def __init__(self, depot_: str, url: str | None = None, compte: str | None = None, jeton: str | None = None,
                 transport=None):
        self.base, self.chemin = adresse_registre(depot_, url)
        self.compte, self.jeton, self.transport = compte, jeton, transport
        self._entete: dict[str, str] = {}

    def _client(self) -> httpx.Client:
        # Le registre directement, jamais par HTTP_PROXY réglé pour joindre MEGGA ; les redirections vers le
        # stockage du registre sont suivies, sans l'en-tête d'accès (httpx le retire d'un hôte à l'autre).
        return httpx.Client(timeout=30, transport=self.transport, follow_redirects=True)

    def _jeton(self, c: httpx.Client, defi: str) -> None:
        """Le jeton Bearer du registre (ghcr.io, registry:2 avec accès) : anonyme, ou avec le compte du client."""
        champs = dict(re.findall(r'(\w+)="([^"]*)"', defi))
        if not defi.lower().startswith("bearer") or not champs.get("realm", "").startswith(("https://", "http://")):
            raise RegistreInjoignable("registre : accès refusé")
        params = {"scope": f"repository:{self.chemin}:pull"}
        if champs.get("service"):
            params["service"] = champs["service"]
        auth = (self.compte or "megga", self.jeton) if self.jeton else None
        r = c.get(champs["realm"], params=params, auth=auth)
        if r.status_code != 200:
            raise RegistreInjoignable(f"registre : jeton refusé ({r.status_code}) ; REGISTRE_JETON est-il juste ?")
        jeton = (r.json() or {}).get("token") or (r.json() or {}).get("access_token")
        if not jeton:
            raise RegistreInjoignable("registre : pas de jeton")
        self._entete = {"authorization": f"Bearer {jeton}"}

    def lire(self, c: httpx.Client, chemin: str, accepte: str | None = None, limite: int = 1 << 20) -> httpx.Response:
        entetes = {"accept": accepte} if accepte else {}
        try:
            r = c.get(f"{self.base}/v2/{self.chemin}/{chemin}", headers={**entetes, **self._entete})
            if r.status_code == 401 and not self._entete:
                self._jeton(c, r.headers.get("www-authenticate", ""))
                r = c.get(f"{self.base}/v2/{self.chemin}/{chemin}", headers={**entetes, **self._entete})
        except httpx.HTTPError as e:
            raise RegistreInjoignable(f"registre injoignable ({type(e).__name__})") from e
        if len(r.content) > limite:
            raise ImageRefusee("signature : réponse du registre trop grosse")
        return r

    def signatures(self, empreinte: str) -> list[tuple[bytes, str]]:
        """Les signatures cosign de cette image : (contenu signé, signature en base64)."""
        with self._client() as c:
            r = self.lire(c, f"manifests/{empreinte.replace(':', '-')}.sig", MANIFESTES)
            if r.status_code == 404:
                raise ImageRefusee("image sans signature de MEGGA")
            if r.status_code != 200:
                raise RegistreInjoignable(f"registre : signature illisible ({r.status_code})")
            try:
                couches = r.json().get("layers") or []
            except ValueError as e:
                raise ImageRefusee("signature mal formée") from e
            sortie = []
            for couche in couches[:10]:
                if not isinstance(couche, dict) or couche.get("mediaType") != TYPE_SIGNATURE:
                    continue
                signature = (couche.get("annotations") or {}).get(ANNOTATION)
                digest = couche.get("digest") or ""
                if not signature or not EMPREINTE.fullmatch(digest):
                    continue
                b = self.lire(c, f"blobs/{digest}", limite=64 * 1024)
                if b.status_code != 200:
                    raise RegistreInjoignable(f"registre : signature illisible ({b.status_code})")
                if "sha256:" + hashlib.sha256(b.content).hexdigest() != digest:
                    raise ImageRefusee("signature : contenu altéré")
                sortie.append((b.content, signature))
            return sortie


def verifier_signature(image: str, depot_: str, cle=None, url: str | None = None, compte: str | None = None,
                       jeton: str | None = None, transport=None) -> str:
    """L'image d'un ordre est-elle signée par MEGGA (cosign, clé dans l'image) ? Rend la référence à tirer.

    Lève ImageRefusee (définitif) ou RegistreInjoignable (à réessayer)."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec

    cle = cle or cle_image()
    empreinte = empreinte_de(image)
    for contenu, signature in Registre(depot_, url, compte, jeton, transport).signatures(empreinte):
        try:
            cle.verify(base64.b64decode(signature, validate=True), contenu, ec.ECDSA(hashes.SHA256()))
            d = json.loads(contenu)
        except (InvalidSignature, ValueError):
            continue
        critique = d.get("critical") if isinstance(d, dict) else None
        if not isinstance(critique, dict) or critique.get("type") != "cosign container image signature":
            continue
        if (critique.get("image") or {}).get("docker-manifest-digest") == empreinte:
            return reference(image, depot_)
    raise ImageRefusee("image sans signature valable de MEGGA")


# La sauvegarde


def sauvegarder(url: str, dossier: str | Path, client: str, version: str, maintenant: float | None = None,
                gardees: int = GARDEES) -> Path:
    """Toute la base dans <dossier>/megga-<client>-<date>-avant-<version>.jsonl.gz ; garde les plus récentes."""
    dossier = Path(dossier)
    if not dossier.is_dir():
        raise RuntimeError(f"dossier des sauvegardes absent : {dossier}")
    quand = time.strftime("%Y%m%d-%H%M%S", time.gmtime(time.time() if maintenant is None else maintenant))
    final = dossier / f"megga-{client}-{quand}-avant-{version}.jsonl.gz"
    provisoire = dossier / f".{final.name}.partiel"  # ni vue ni gardée comme une sauvegarde tant qu'elle n'est pas finie
    try:
        stockage.exporter(url, provisoire, gz=True)
        os.replace(provisoire, final)
    finally:
        provisoire.unlink(missing_ok=True)
    for vieille in sauvegardes(dossier, client)[gardees:]:
        vieille.unlink(missing_ok=True)
    return final


def sauvegardes(dossier: str | Path, client: str) -> list[Path]:
    """Les sauvegardes de ce client, la plus récente d'abord."""
    dossier = Path(dossier)
    if not dossier.is_dir():
        return []
    return sorted(dossier.glob(f"megga-{client}-*.jsonl.gz"), key=lambda p: p.name, reverse=True)


# L'exécutant Kubernetes


class Kubernetes:
    """Lire et changer l'image d'un Deployment, avec le compte de service du pilote (rien d'autre n'est permis)."""

    COMPTE = Path("/var/run/secrets/kubernetes.io/serviceaccount")

    def __init__(self, env: dict, transport=None):
        hote, port = env.get("KUBERNETES_SERVICE_HOST"), env.get("KUBERNETES_SERVICE_PORT") or "443"
        if not hote and transport is None:
            raise RuntimeError("AGENT_DEPLOIEMENT : seulement dans Kubernetes")
        self.url = f"https://{hote or 'kubernetes'}:{port}"
        self.transport = transport
        lire = lambda nom, defaut="": (self.COMPTE / nom).read_text().strip() if (self.COMPTE / nom).exists() else defaut  # noqa: E731
        self.espace = env.get("POD_NAMESPACE") or lire("namespace", "default")
        self._jeton = lambda: lire("token")  # relu à chaque fois : Kubernetes le renouvelle
        self.ca = str(self.COMPTE / "ca.crt") if (self.COMPTE / "ca.crt").exists() else True

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.url, timeout=30, transport=self.transport, verify=self.ca, trust_env=False,
                            headers={"authorization": f"Bearer {self._jeton()}"})

    def _chemin(self, nom: str) -> str:
        return f"/apis/apps/v1/namespaces/{self.espace}/deployments/{nom}"

    def image(self, deploiement: str, conteneur: str) -> str:
        try:
            with self._client() as c:
                r = c.get(self._chemin(deploiement))
        except httpx.HTTPError as e:
            raise RegistreInjoignable(f"Kubernetes injoignable ({type(e).__name__})") from e
        if r.status_code != 200:
            raise RuntimeError(f"Kubernetes : lecture de {deploiement} refusée ({r.status_code})")
        for c in ((r.json().get("spec") or {}).get("template") or {}).get("spec", {}).get("containers") or []:
            if c.get("name") == conteneur:
                return c.get("image") or ""
        raise RuntimeError(f"Kubernetes : pas de conteneur {conteneur} dans {deploiement}")

    def poser(self, deploiement: str, conteneur: str, image: str) -> None:
        corps = {"spec": {"template": {"spec": {"containers": [{"name": conteneur, "image": image}]}}}}
        try:
            with self._client() as c:
                r = c.patch(self._chemin(deploiement), content=json.dumps(corps),
                            headers={"content-type": "application/strategic-merge-patch+json"})
        except httpx.HTTPError as e:
            raise RegistreInjoignable(f"Kubernetes injoignable ({type(e).__name__})") from e
        if r.status_code != 200:
            raise RuntimeError(f"Kubernetes : changement de {deploiement} refusé ({r.status_code})")
