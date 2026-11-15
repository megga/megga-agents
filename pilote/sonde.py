"""La sonde de santé du pilote : un fichier touché à chaque tour. Sans dépendance, pour que la sonde
(python -m pilote vivant, chaque minute) ne charge pas tout le pilote."""

from __future__ import annotations

import contextlib
import math
import tempfile
import time
from pathlib import Path

VIVANT = Path(tempfile.gettempdir()) / "megga-pilote-vivant"


def vivant() -> None:
    with contextlib.suppress(OSError):
        VIVANT.touch()


def en_vie(intervalle: str | float | None) -> bool:
    try:
        i = float(intervalle or 60)
    except ValueError:
        i = 60.0
    i = max(1.0, i) if math.isfinite(i) else 60.0  # comme le pilote
    try:
        return time.time() - VIVANT.stat().st_mtime < 3 * i + 60
    except OSError:
        return False
