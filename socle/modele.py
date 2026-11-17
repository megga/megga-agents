"""Le modèle de recherche de la base de connaissances (noyau/connaissances.py), posé dans l'image à sa construction.

Une révision figée de Hugging Face et l'empreinte SHA-256 de chaque fichier : une image construite deux fois a le
même modèle, et un fichier changé en route arrête la construction.

  python socle/modele.py /opt/megga/modele
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

DEPOT = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
FICHIERS = {
    # le modèle quantifié en int8 (118 Mo), sous le nom que le noyau attend
    "model.onnx": ("onnx/model_quint8_avx2.onnx", "98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f"),
    "tokenizer.json": ("tokenizer.json", "2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8"),
}


def poser(dossier: Path) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    for nom, (chemin, empreinte) in FICHIERS.items():
        url = f"https://huggingface.co/{DEPOT}/resolve/{REVISION}/{chemin}"
        cible = dossier / nom
        h = hashlib.sha256()
        with urllib.request.urlopen(url, timeout=300) as r, open(cible, "wb") as f:
            while morceau := r.read(1 << 20):
                h.update(morceau)
                f.write(morceau)
        if h.hexdigest() != empreinte:
            cible.unlink()
            raise SystemExit(f"{nom} : empreinte inattendue ({h.hexdigest()}), construction arrêtée")
        print(f"{nom} : {cible.stat().st_size // 1_000_000} Mo, empreinte vérifiée")


if __name__ == "__main__":
    poser(Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/megga/modele"))
