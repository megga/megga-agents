"""L'entrée par API de bout en bout, sans réseau ni secret : un faux service de Claude, le vrai agent
(Agno, mémoire, garde-fous, base SQLite), la vraie porte devant lui (tests/api/porte.mjs).

  .venv/bin/python tests/api/essai_bout_en_bout.py

Le faux Claude répond par le nombre de messages qu'il reçoit : la mémoire se voit au second tour.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parents[2]
CLIENT = "cabinet-essai"


def port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FauxClaude(BaseHTTPRequestHandler):
    """L'API Messages d'Anthropic, réduite : la réponse dit ce que le modèle a reçu."""

    vus: list = []

    def do_POST(self):
        d = json.loads(self.rfile.read(int(self.headers["content-length"])))
        tours = [m for m in d.get("messages", []) if m.get("role") == "user"]
        dernier = tours[-1]["content"] if tours else ""
        # Le texte de la personne seul : le Contexte du tour (l'heure, ses demandes) le suit dans un bloc à part.
        blocs = [dernier] if isinstance(dernier, str) else [b.get("text", "") for b in dernier if isinstance(b, dict)]
        texte = " ".join(b for b in blocs if not b.startswith("<additional context>"))
        FauxClaude.vus.append(texte)
        reponse = {"id": "msg_essai", "type": "message", "role": "assistant", "model": d.get("model"),
                   "content": [{"type": "text", "text": f"Reçu {len(tours)} message(s) de vous."}],
                   "stop_reason": "end_turn", "stop_sequence": None, "usage": {"input_tokens": 12, "output_tokens": 6}}
        corps = json.dumps(reponse).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *_):
        pass


def main() -> int:
    dossier = Path(tempfile.mkdtemp(prefix="megga-essai-api-"))
    claude = ThreadingHTTPServer(("127.0.0.1", port_libre()), FauxClaude)
    threading.Thread(target=claude.serve_forever, daemon=True).start()
    conf = yaml.safe_load((RACINE / "clients" / "exemple.yaml").read_text())
    conf.pop("whatsapp")  # un client branché seulement par API
    conf.update(id=CLIENT, modeles={"principal": "claude-sonnet-5-5", "secours": None})
    port = port_libre()
    env = {**os.environ, "CLIENT_CONFIG": json.dumps(conf), "DATABASE_URL": f"sqlite:///{dossier}/client.db", "PORT": str(port),
           "ANTHROPIC_API_KEY": "essai", "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{claude.server_address[1]}",
           "AGNO_TELEMETRY": "false", "INTERNE_TOKEN": "interne"}
    agent = subprocess.Popen([sys.executable, "-m", "noyau"], cwd=RACINE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/sante", timeout=1) as r:
                    if json.load(r)["ok"]:
                        break
            except OSError:
                time.sleep(0.2)
        else:
            raise SystemExit("l'agent ne démarre pas")
        sortie = subprocess.run([sys.executable, "-m", "noyau.cles", "creer", "dossier", "3"], cwd=RACINE, env=env,
                                capture_output=True, text=True, check=True).stdout.splitlines()
        cle = sortie[-1]
        print("Agent démarré, clé créée (python -m noyau.cles) ; la porte transmet :")
        lignes = subprocess.run(["node", "--import", "./test/bouchons/enregistrer.js", "../tests/api/porte.mjs", str(port), cle, CLIENT],
                                cwd=RACINE / "porte", capture_output=True, text=True, check=True).stdout.splitlines()
        r = [json.loads(l) for l in lignes]
        for x in r:
            print(" ", x["statut"], x["corps"])
        assert r[0] == {"statut": 200, "retry": None, "corps": {"reponse": "Reçu 1 message(s) de vous."}}, r[0]
        # Le second tour voit le premier : la mémoire de la conversation
        assert r[1]["statut"] == 200 and r[1]["corps"]["reponse"] == "Reçu 2 message(s) de vous.", r[1]
        assert r[2]["statut"] == 400 and "téléphone" in r[2]["corps"]["erreur"], r[2]
        assert r[3]["statut"] == 401, r[3]
        # Débit de la clé : 3 tours par minute (les refus ne comptent pas), le quatrième est refusé
        assert r[4]["statut"] == 200, r[4]
        assert r[5]["statut"] == 429 and r[5]["retry"], r[5]
        assert FauxClaude.vus[:2] == ["Bonjour, je m'appelle Jeanne.", "Comment je m'appelle ?"], FauxClaude.vus
        # Le suivi les compte à part, et le fil se lit
        requete = urllib.request.Request(f"http://127.0.0.1:{port}/interne/suivi", headers={"x-megga-interne": "interne"})
        with urllib.request.urlopen(requete) as s:
            suivi = json.load(s)
        assert (suivi["tours"], suivi["tours_api"], suivi["personnes"]) == (3, 3, 2), suivi
        assert suivi["journal"]["api_debit"]["nombre"] == 1, suivi["journal"]
        print("Essai réussi.")
        return 0
    finally:
        agent.terminate()
        try:
            _, erreurs = agent.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            agent.kill()
            erreurs = b""
        if erreurs and sys.exc_info()[0] is not None:
            print(erreurs.decode()[-3000:])
        claude.shutdown()
        import shutil

        shutil.rmtree(dossier, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
