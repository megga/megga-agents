"""Le joueur du socle pour le banc de parité : joue les cas neutres (parite/cas.json) sur l'agent de Four Seasons tel que
le socle le construit (noyau.app.creer : ses rôles, ses outils, sa base), avec le vrai Claude, la vraie gestion du site
servie en local (parite/gestion.mjs, la donnée du dépôt du site) et WhatsApp simulé ; écrit une trace par cas, au même
format que celles d'Alix (parite/alix.mjs). La notation est commune (parite/noter.py).

  .venv/bin/python -m parite.socle <dépôt fourseasonsproperties> <sortie> [--cas G01,V03]

La clé Anthropic se lit dans ANTHROPIC_API_KEY ou ~/.config/alix-essai/anthropic.key, jamais affichée. Une base SQLite
neuve et une gestion neuve par cas. L'horloge n'avance pas : « 13 heures plus tard » marque seulement le moment, car
le socle ne vide pas l'historique avec le temps (il relit les douze derniers tours, puis le fil).
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent
CLE_GESTION = "k" * 40
COMPTE = "gl@fourseasonsgroup.ch"
NUMERO_ID = "100000000000042"


def cle_anthropic() -> str:
    cle = os.environ.get("ANTHROPIC_API_KEY") or (Path.home() / ".config" / "alix-essai" / "anthropic.key").read_text().strip()
    if not cle:
        raise SystemExit("clé Anthropic absente")
    return cle


def port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Meta:
    """WhatsApp simulé : tout ce que l'agent envoie, dans l'ordre, au journal du cas."""

    def __init__(self, journal: list):
        self.journal = journal
        self.n = 0

    def _noter(self, vers, texte, **autres):
        self.journal.append({"de": "agent", "a": vers, "numero": vers, "texte": texte or "", "touche": None, **autres})
        self.n += 1
        return {"messages": [{"id": f"wamid.{self.n}"}]}

    async def texte(self, vers, texte, apercu=False):
        return self._noter(vers, texte)

    async def liste(self, vers, corps, bouton, section, lignes):
        return self._noter(vers, f"{corps}\n[{' | '.join(l['titre'] for l in lignes)}]")

    async def boutons(self, vers, corps, boutons):
        return self._noter(vers, corps)

    async def carrousel(self, vers, corps, cartes):
        return self._noter(vers, corps + "\n" + "\n".join(str(c.get("corps") or c.get("texte") or "") for c in cartes))

    async def document(self, vers, nom, media_id="", lien="", legende=""):
        return self._noter(vers, f"[PDF {nom}] {legende}")

    async def image(self, vers, media_id="", lien="", legende=""):
        return self._noter(vers, f"[image] {legende}")

    async def video(self, vers, media_id="", lien="", legende=""):
        return self._noter(vers, f"[vidéo] {legende}")

    async def modele(self, vers, nom, langue, variables):
        return self._noter(vers, f"[modèle {nom}] {' | '.join(variables)}")

    async def formulaire(self, vers, flow_id, corps, bouton, jeton, ecran):
        return self._noter(vers, corps)

    async def vocal(self, vers, audio, ogg):
        return self._noter(vers, "[vocal]")

    async def televerser(self, octets, type_, nom):
        return f"media-{len(octets)}"

    async def telecharger(self, media_id, maximum=0):
        raise RuntimeError("aucun média dans le banc")

    async def lu(self, message_id):
        return {}

    async def reaction(self, vers, message_id, emoji):
        return {}


async def jouer(cas: dict, depot: str, greg: str, cle: str) -> dict:
    from noyau import config as configuration
    from noyau.app import creer
    from noyau.whatsapp import Entrant

    port = port_libre()
    serveur = subprocess.Popen(["node", str(ICI / "gestion.mjs"), depot, str(port)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        if not (serveur.stdout.readline() or "").startswith("pret"):
            raise RuntimeError("la gestion locale ne démarre pas")
        conf = configuration.lire(str(RACINE / "clients" / "four-seasons-properties.yaml")).model_dump(mode="json")
        conf = {**conf, "whatsapp": {"numero_id": NUMERO_ID}, "modeles_meta": {"demande": {"nom": "fsp_demande_information"}}}
        base = tempfile.mkdtemp()
        journal, outils, resultats, gestion = [], [], [], []
        env = {"CLIENT_CONFIG": json.dumps(conf), "DATABASE_URL": f"sqlite:///{base}/banc.db", "ANTHROPIC_API_KEY": cle, "DEEPSEEK_API_KEY": "",
               "GESTIONNAIRES": json.dumps({greg: COMPTE}), "GESTION_CLE": CLE_GESTION, "META_APP_SECRET": "s", "INTERNE_TOKEN": "i"}
        app = creer(env, expediteur=Meta(journal), attente=0.01, seuil_regard=10_000)
        g = app.state.gestion
        g._url = f"http://127.0.0.1:{port}"
        appel = g.appel

        async def noter_appel(compte, methode, chemin, **options):
            gestion.append({"methode": methode.upper(), "chemin": f"/api/gestion{chemin}"})
            return await appel(compte, methode, chemin, **options)

        g.appel = noter_appel
        c = app.state.conversations
        for nom, agent in list(c.agents.items()):
            def emballer(agent):
                original = agent.arun

                async def arun(texte, **options):
                    sortie = await original(texte, **options)
                    for t in getattr(sortie, "tools", None) or []:
                        outils.append({"nom": t.tool_name, "entree": t.tool_args or {}})
                        if t.result is not None:
                            resultats.append(str(t.result)[:1500])
                    return sortie

                agent.arun = arun
            emballer(agent)
        await asyncio.to_thread(c.contacts.noter, greg, time.time())  # Greg a écrit récemment : on peut lui écrire
        erreur, marque, n = None, None, 0
        try:
            for e in cas["etapes"]:
                if e.get("avancer"):
                    marque = len(journal)
                    continue
                de = greg if e["de"] == "greg" else e["de"]
                n += 1
                journal.append({"de": "Greg" if de == greg else de, "a": "agent", "numero": de, "texte": e["texte"], "touche": None})
                role = await asyncio.to_thread(app.state.personnes.role, de)
                c.recevoir(Entrant(id=f"w{n}", de=de, texte=e["texte"], envoye=time.time(), genre="text"), role)
                await asyncio.sleep(0.05)
                while c.taches:
                    await asyncio.gather(*list(c.taches), return_exceptions=True)
        except Exception as ex:
            erreur = str(ex)[:300]
        return {"id": cas["id"], "plateforme": "socle", "modele": conf["modeles"]["principal"], "journal": journal, "outils": outils,
                "resultats": resultats, "gestion": gestion, "appels": None, "erreur": erreur, "marque": marque}
    finally:
        serveur.terminate()


def principal(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    depot, sortie = args[0], Path(args[1])
    choix = argv[argv.index("--cas") + 1].split(",") if "--cas" in argv else None
    doc = json.loads((ICI / "cas.json").read_text(encoding="utf-8"))
    cle = cle_anthropic()
    sortie.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("AGNO_TELEMETRY", "false")
    for cas in doc["cas"]:
        if choix and cas["id"] not in choix:
            continue
        t = asyncio.run(jouer(cas, depot, doc["greg"], cle))
        (sortie / f"{cas['id']}.json").write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{cas['id']} joué sur le socle : {len(t['outils'])} outil(s){', erreur : ' + t['erreur'] if t['erreur'] else ''}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
