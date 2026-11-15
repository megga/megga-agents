import os

# Une seule image : l'agent d'un client, ou l'atelier de MEGGA (MEGGA_SERVICE=atelier).
if os.environ.get("MEGGA_SERVICE") == "atelier":
    from atelier.app import principal
else:
    from .app import principal

principal()
