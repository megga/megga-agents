"""Un essai réel des résumés de la page Activité, avec Claude : trois conversations, puis leurs phrases.

Lancé à la main, avec votre clé dans le terminal (elle ne sort pas de cette commande) :

    ANTHROPIC_API_KEY=… .venv/bin/python scripts/essai_resumes.py

Sans clé, le modèle d'essai répond à la place de Claude (pour vérifier que l'essai tourne). Les agents et leurs
conversations vivent dans un dossier jetable, effacé à la fin. Coût avec Claude : quelques centimes.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RACINE), str(RACINE / "console" / "agents")]

CONVERSATIONS = [
    ("alix", ["Bonjour, je cherche un 3 pièces à Lausanne, budget 1,2 million.",
              "Avec un balcon si possible. Je suis libre jeudi après-midi pour visiter."]),
    ("lea", ["Bonjour, j'ai reçu un rappel pour ma facture de septembre, pourtant je l'ai payée le 3 octobre."]),
    ("alix", ["Pouvez-vous demander à votre collègue de la fiduciaire si le dossier Martin est complet ?"]),
]


async def principal() -> None:
    with tempfile.TemporaryDirectory() as dossier:
        os.environ["AGENTS_DONNEES"] = dossier
        import serveur  # après AGENTS_DONNEES : ses données vont dans le dossier jetable

        fiches = {"alix": {"prenom": "Alix", "metier": "immobilier", "entreprise": "Agence du Lac", "compte": "essai"},
                  "lea": {"prenom": "Léa", "metier": "fiduciaire", "entreprise": "Agence du Lac", "compte": "essai"}}
        serveur.ecrire_registre({f"agent-{k}": v for k, v in fiches.items()})
        registre = serveur.lire_registre()
        print("Modèle :", "Claude" if os.environ.get("ANTHROPIC_API_KEY") else "modèle d'essai (aucune clé)", "\n")
        for n, (qui, messages) in enumerate(CONVERSATIONS):
            agent = serveur.construire(f"agent-{qui}", registre[f"agent-{qui}"])
            for texte in messages:
                sortie = await agent.arun(texte, user_id=f"agent-{qui}", session_id=f"fil-{n}")
                print(f"> {texte}\n{fiches[qui]['prenom']} : {sortie.content}\n")
        print("Ce que montrerait la page Activité :")
        for c in serveur.conversations("essai")["conversations"]:
            print(f"- {c['resume'] or '(pas de résumé)'}")
            for e in c["etapes"]:
                print(f"    étape : a demandé à {registre[e['collegue']]['prenom']} : {e['question']}")


if __name__ == "__main__":
    asyncio.run(principal())
