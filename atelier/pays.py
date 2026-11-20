"""Le pays de chaque client, pour la carte du monde de la console (20.11.2026).

Un réglage de l'atelier (megga_reglages, clé « pays »), pas de la configuration de l'agent : le changer ne crée aucune
version et ne touche aucun conteneur. MEGGA seul le règle ; la liste des clients le porte.
"""

from __future__ import annotations

from typing import Any

from .regles import Refus

CLE = "pays"
# Les codes ISO 3166-1 à deux lettres (console/scripts/carte-monde.cjs les tire de i18n-iso-countries).
CODES = frozenset((
    "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC "
    "CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD "
    "GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH "
    "KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW "
    "MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC "
    "SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY "
    "UZ VA VC VE VG VI VN VU WF WS XK YE YT ZA ZM ZW "
).split())


def tous(reglages: Any) -> dict[str, str]:
    return _propres(reglages.lire(CLE))


def _propres(lus: Any) -> dict[str, str]:
    return {k: v for k, v in lus.items() if v in CODES} if isinstance(lus, dict) else {}


def regler(reglages: Any, client: str, code: Any) -> str | None:
    """Le pays du client, ou aucun (null) ; un code inconnu est refusé."""
    if code is not None and (not isinstance(code, str) or code.upper() not in CODES):
        raise Refus(422, "pays : un code ISO à deux lettres (CH, FR, ES…), ou null")
    for _ in range(5):  # lu puis écrit seulement s'il n'a pas changé entre-temps (deux membres, deux clients)
        avant = reglages.lire(CLE)
        pays = _propres(avant)
        if code is None:
            pays.pop(client, None)
        else:
            pays[client] = code.upper()
        if reglages.changer(CLE, avant, pays):
            return pays.get(client)
    raise Refus(409, "pays : changé au même instant, réessayez")
