"""Le pack immobilier : les biens d'une agence, et les outils de l'agent pour les chercher.

Le catalogue vient d'un fichier livré avec l'image (la démo) ou d'un flux JSON de
l'agence, au format de `catalogue.Bien`. Les connecteurs vers les formats des
portails (IDX en Suisse, flux XML ailleurs) viendront ensuite, un par format.
Rien de Four Seasons ici : le pack ne connaît que ce que le catalogue du client contient.
"""

from .catalogue import Bien, Catalogue  # noqa: F401
from .outils import outils  # noqa: F401
