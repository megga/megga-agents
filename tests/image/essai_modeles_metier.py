"""Les modèles par métier de bout en bout, sur la vraie image (lot 10), sans réseau ni secret.

  python3 tests/image/essai_modeles_metier.py [image]     (par défaut megga-agents:essai, celle de la CI)

Trois conteneurs sur un réseau Docker à part, disque en lecture seule comme en production : un faux service de
Claude (tests/image/faux_claude.py), l'atelier, et un agent Garage. L'atelier crée un client depuis chacun des
modèles du dépôt (atelier/gabarits/) ; l'agent Garage sert ensuite le client d'après sa version, par l'entrée API.
Ce qu'on attend se lit dans les fichiers des modèles : un modèle ajouté est essayé sans toucher à ce fichier.

Le parcours : les modèles dans l'ordre et leur source ; un client par modèle, son métier, ses outils, ses consignes
dans les bornes ; santé refusé pour la zone États-Unis, un modèle inconnu refusé ; l'agent reçoit le socle d'accueil
et le bloc de son métier, avec les outils pour noter, chercher et passer la main ; une demande notée, complétée par
la même personne au lieu d'être doublée, une autre pour une autre personne ; un journal sans erreur.
Tout est effacé à la fin, réussite ou échec.
"""

import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
ICI = Path(__file__).resolve().parent
GABARITS = RACINE / "atelier" / "gabarits"
ADMIN = "essai-admin"
INTERNE = "essai-interne"
CONSIGNES_MAX = 8000  # Config (noyau/config.py)


def modeles_du_depot() -> list[dict]:
    """Les modèles tels que le dépôt les décrit, dans leur ordre : id, métier, source ou non, première ligne du bloc."""
    modeles = []
    for f in GABARITS.glob("[a-z]*.md"):
        _, tete, bloc = f.read_text(encoding="utf-8").split("---\n", 2)
        champs = dict(re.findall(r"^(\w+):[ \t]*(.*)$", tete, re.M))
        modeles.append({"id": f.stem, "metier": champs["metier"], "ordre": int(champs["ordre"]),
                        "source": champs["source"] != "null", "premiere": bloc.strip().splitlines()[0]})
    return sorted(modeles, key=lambda m: m["ordre"])


def docker(*args, check=True) -> str:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check).stdout.strip()


def http(methode, url, corps=None, entetes=None):
    donnees = json.dumps(corps).encode() if corps is not None else None
    r = urllib.request.Request(url, data=donnees, method=methode, headers={"content-type": "application/json", **(entetes or {})})
    try:
        with urllib.request.urlopen(r, timeout=130) as rep:
            return rep.status, json.loads(rep.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def attendre(url, nom):
    for _ in range(120):
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if json.load(r).get("ok", True):
                    return
        except (OSError, ValueError):
            time.sleep(0.5)
    raise AssertionError(f"{nom} ne démarre pas")


def ok(etape, condition, detail=None):
    if not condition:
        raise AssertionError(etape + ("" if detail is None else f" : {detail}"))
    print(f"  ok : {etape}")


def main() -> int:
    image = sys.argv[1] if len(sys.argv) > 1 else "megga-agents:essai"
    modeles = modeles_du_depot()
    s = uuid.uuid4().hex[:6]
    reseau, claude, atelier, agent = f"megga-essai-{s}", f"essai-claude-{s}", f"essai-atelier-{s}", f"essai-agent-{s}"

    def lancer(nom, env, commande=(), port=True, volumes=()):
        args = ["run", "-d", "--name", nom, "--network", reseau, "--read-only", "--tmpfs", "/tmp", "-e", "HOME=/tmp"]
        args += ["-p", "127.0.0.1::8080"] if port else []
        for v in volumes:
            args += ["-v", v]
        for k, v in env.items():
            args += ["-e", f"{k}={v}"]
        docker(*args, image, *commande)
        return "http://" + docker("port", nom, "8080").splitlines()[0] if port else None

    docker("network", "create", reseau)
    try:
        print("Le faux Claude et l'atelier")
        lancer(claude, {}, ("python", "/essai/faux_claude.py", "8000"), port=False, volumes=(f"{ICI}:/essai:ro",))
        base_a = lancer(atelier, {"MEGGA_SERVICE": "atelier", "DATABASE_URL": "sqlite:////tmp/atelier.db", "ADMIN_TOKEN": ADMIN})
        attendre(base_a + "/sante", "l'atelier")
        adm = {"authorization": f"Bearer {ADMIN}"}

        print(f"Les {len(modeles)} modèles du dépôt")
        st, r = http("GET", base_a + "/atelier/gabarits", entetes=adm)
        servis = r["gabarits"] if st == 200 else []
        ok("l'atelier les rend tous, dans l'ordre", [g["id"] for g in servis] == [m["id"] for m in modeles], (st, r))
        for g, m in zip(servis, modeles):
            ok(f"{g['id']} : sa source" + (" (agency-agents)" if m["source"] else " (aucune)"),
               ("agency-agents" in json.dumps(g["source"])) if m["source"] else g["source"] is None, g["source"])

        print("Un client par modèle")
        configs = {}
        for m in modeles:
            st, r = http("POST", base_a + "/atelier/clients", {"gabarit": m["id"], "nom_agent": "Alix",
                         "client": {"id": f"essai-{m['id']}", "entreprise": f"Essai {m['id']}", "zone": "suisse"}}, adm)
            ok(f"essai-{m['id']} créé", st == 201, (st, r))
            st, v = http("GET", base_a + f"/atelier/clients/essai-{m['id']}/versions/1", entetes=adm)
            c = configs[m["id"]] = v["config"]
            ok(f"  métier {m['metier']}, outils connaissances et leads, consignes de {len(c['consignes'])} caractères",
               c["metier"] == m["metier"] and {"connaissances", "leads"} <= set(c["outils"]) and len(c["consignes"]) <= CONSIGNES_MAX,
               (c.get("metier"), c.get("outils")))
        st, r = http("POST", base_a + "/atelier/clients", {"gabarit": "sante", "nom_agent": "Alix",
                     "client": {"id": "essai-sante-us", "entreprise": "Essai US", "zone": "etats-unis"}}, adm)
        ok("santé refusé pour la zone États-Unis", st == 400 and "États-Unis" in json.dumps(r, ensure_ascii=False), (st, r))
        st, r = http("POST", base_a + "/atelier/clients", {"gabarit": "plombier", "nom_agent": "Alix",
                     "client": {"id": "essai-x", "entreprise": "X", "zone": "suisse"}}, adm)
        ok("un modèle inconnu refusé", st == 400, (st, r))

        print("L'agent Garage, servi d'après sa version, devant le faux Claude")
        conf = {**configs["garage"], "modeles": {"principal": "claude-sonnet-5-5", "secours": None}}
        base_g = lancer(agent, {"CLIENT_CONFIG": json.dumps(conf), "DATABASE_URL": "sqlite:////tmp/client.db", "INTERNE_TOKEN": INTERNE,
                                "ANTHROPIC_API_KEY": "essai", "ANTHROPIC_BASE_URL": f"http://{claude}:8000", "AGNO_TELEMETRY": "false"})
        attendre(base_g + "/sante", "l'agent")
        st, sante = http("GET", base_g + "/sante")
        ok("/sante annonce chaque métier", all(m["metier"] in sante.get("metiers", []) for m in modeles), sante)
        cle = docker("exec", agent, "python", "-m", "noyau.cles", "creer", "essai", "30").splitlines()[-1]
        ok("une clé d'API créée dans la base du client", cle.startswith("mga_"))
        api = {"authorization": f"Bearer {cle}"}

        st, r = http("POST", base_g + "/api/messages", {"personne": "client-1", "texte": "Bonjour, ma Golf de 2017 fait un bruit en freinant."}, api)
        ok("premier message : la demande 1 est notée", st == 200 and "Demande 1 enregistrée" in r.get("reponse", ""), (st, r))
        premier = json.loads(next(l for l in docker("logs", claude).splitlines() if l.startswith("{")))
        socle = (GABARITS / "_accueil.md").read_text(encoding="utf-8").strip().splitlines()[0]
        garage = next(m for m in modeles if m["id"] == "garage")["premiere"]
        ok("Claude reçoit le socle d'accueil et le bloc Garage", socle in premier["systeme"] and garage in premier["systeme"],
           premier["systeme"][:300])
        ok("Claude peut noter, chercher dans les documents et passer la main",
           {"enregistrer_lead", "chercher_dans_les_documents", "passer_la_main"} <= set(premier["outils"]), premier["outils"])
        st, r = http("POST", base_g + "/api/messages", {"personne": "client-1", "texte": "Elle a 98 000 km."}, api)
        ok("la même personne : la demande 1 complétée, pas doublée", st == 200 and "Demande 1 complétée" in r.get("reponse", ""), (st, r))
        st, r = http("POST", base_g + "/api/messages", {"personne": "client-2", "texte": "Un pneu crevé."}, api)
        ok("une autre personne : la demande 2", st == 200 and "Demande 2 enregistrée" in r.get("reponse", ""), (st, r))
        st, r = http("GET", base_g + "/interne/suivi/leads", entetes={"x-megga-interne": INTERNE})
        leads = (r or {}).get("leads", [])
        # Compléter remplace le besoin par celui que le modèle redonne (noyau/stockage.py, Leads.completer) ; le faux
        # Claude ne redonne que le dernier message.
        ok("le suivi compte deux demandes, la première complétée",
           st == 200 and len(leads) == 2 and any(l["besoin"] == "Elle a 98 000 km." for l in leads), (st, leads))
        journal = docker("logs", agent)
        ok("rien n'a voulu écrire sur le disque en lecture seule", "read-only file system" not in journal.lower())
        ok("aucune exception dans le journal de l'agent", "Traceback" not in journal, journal[-1500:])
        print("Essai réussi.")
        return 0
    except AssertionError as e:
        for n in (atelier, agent):
            print(f"--- {n} ---\n" + docker("logs", "--tail", "40", n, check=False))
        print(f"Essai en échec : {e}")
        return 1
    finally:
        docker("rm", "-f", claude, atelier, agent, check=False)
        docker("network", "rm", reseau, check=False)


if __name__ == "__main__":
    sys.exit(main())
