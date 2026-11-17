"""Un faux service de Claude (API Messages, réduite), lancé dans un conteneur à côté de l'agent.

Il note une demande (enregistrer_lead) à chaque message de la personne, puis répond par ce que
l'outil a rendu. Chaque appel est écrit en une ligne JSON sur la sortie : outils proposés, consignes.
"""

import itertools
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

compteur = itertools.count(1)


def texte_de(contenu):
    if isinstance(contenu, str):
        return contenu
    return " ".join(b.get("text", "") for b in contenu if isinstance(b, dict))


class Faux(BaseHTTPRequestHandler):
    def do_POST(self):
        d = json.loads(self.rfile.read(int(self.headers["content-length"])))
        if self.path.endswith("count_tokens"):
            return self.repondre({"input_tokens": 10})
        outils = [t.get("name") for t in d.get("tools", [])]
        systeme = d.get("system") or ""
        systeme = systeme if isinstance(systeme, str) else texte_de(systeme)
        dernier = d["messages"][-1]
        blocs = dernier["content"] if isinstance(dernier["content"], list) else []
        resultats = [b for b in blocs if isinstance(b, dict) and b.get("type") == "tool_result"]
        n = next(compteur)
        print(json.dumps({"appel": n, "outils": outils, "systeme": systeme, "resultat": bool(resultats)}), flush=True)
        if resultats:
            contenu = [{"type": "text", "text": "Noté. " + texte_de(resultats[0].get("content", ""))}]
            fin = "end_turn"
        elif "enregistrer_lead" in outils:
            question = texte_de(dernier["content"])
            contenu = [{"type": "tool_use", "id": f"toolu_{n:04d}", "name": "enregistrer_lead",
                        "input": {"besoin": question[:200], "score": 3, "nom": "M. Martin"}}]
            fin = "tool_use"
        else:
            contenu = [{"type": "text", "text": "Bonjour."}]
            fin = "end_turn"
        self.repondre({"id": f"msg_{n}", "type": "message", "role": "assistant", "model": d.get("model"),
                       "content": contenu, "stop_reason": fin, "stop_sequence": None,
                       "usage": {"input_tokens": 12, "output_tokens": 6}})

    def repondre(self, corps):
        b = json.dumps(corps).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *_):
        pass


ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1])), Faux).serve_forever()
