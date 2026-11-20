"""Les outils de l'agent vocal d'ElevenLabs, tirés des outils d'Alix (noyau/appels.py, noyau/appels_outils.py).

    .venv/bin/python scripts/appels_outils.py <client> <adresse de la porte> <secret_id ElevenLabs> > outils.json

Écrit, en JSON, un webhook par outil permis pendant un appel (appels.OUTILS), vers <porte>/appels/<client>/outils/<nom>,
avec l'en-tête Authorization tiré du secret d'ElevenLabs (sa valeur : « Bearer <APPELS_CLE> »). Rien n'est envoyé : on les
pose ensuite dans ElevenLabs (docs/appels.md). Aucun service n'est joint : les outils sont construits, jamais appelés.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from noyau import config as configuration  # noqa: E402
from noyau.app import outils_du_client  # noqa: E402
from noyau.appels import OUTILS  # noqa: E402
from noyau.appels_outils import definitions  # noqa: E402
from noyau.memoire import Memoire  # noqa: E402


def outils_d_appel(conf) -> dict:
    """Les outils du rôle gestionnaire permis pendant un appel, construits sur des services vides."""
    from packs.immobilier.annonces import Services
    from packs.immobilier.annonces import outils as outils_annonces
    from packs.immobilier.marche import Marche

    s = Services.__new__(Services)
    s.reglage_marche, s.fuseau, s.carnet, s.veilles = conf.marche, conf.fuseau, object(), object()  # jamais lus ici
    gerant = conf.les_roles()["gestionnaire"]
    # Les groupes du gestionnaire qui portent des outils d'appel : rappels, mémoire, annonces et marché.
    liste = outils_du_client(conf, None, tuple(g for g in gerant.outils if g in ("rappels", "memoire")), memoire=Memoire(None, conf.fuseau))
    liste += outils_annonces(s) + (Marche(s).outils() if "marche" in gerant.outils else [])
    return {f.__name__: f for f in liste if f.__name__ in OUTILS}


def principal(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    client, porte, secret = argv[1], argv[2].rstrip("/"), argv[3]
    conf = configuration.lire(f"clients/{client}.yaml")
    outils = outils_d_appel(conf)
    manquants = sorted(set(OUTILS) - set(outils))
    if manquants:
        print(f"outils introuvables : {', '.join(manquants)}", file=sys.stderr)
        return 1
    print(json.dumps(definitions({n: outils[n] for n in OUTILS}, f"{porte}/appels/{client}", secret), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv))
