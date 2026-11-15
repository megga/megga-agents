import os

# Une seule image : l'agent d'un client, l'atelier de MEGGA (MEGGA_SERVICE=atelier), ou le pilote
# d'une installation hors Cloudflare (MEGGA_SERVICE=pilote).
service = os.environ.get("MEGGA_SERVICE")
if service == "atelier":
    from atelier.app import principal
elif service == "pilote":
    from pilote.service import principal
else:
    from .app import principal

principal()
