# Installer l'agent MEGGA chez le client

L'offre premium : l'agent tourne sur le serveur ou dans le cloud du client (Azure, AWS, son Kubernetes…). Ses conversations, sa base et ses fichiers ne quittent pas son infrastructure. Seuls partent les appels aux modèles (Claude, DeepSeek) et à la voix (ElevenLabs), vers les comptes que le client a choisis : il doit le savoir.

C'est la même image signée que chez MEGGA. Deux façons de l'installer :
- **Docker Compose**, sur un serveur : l'agent, sa base Postgres et une entrée HTTPS (`installation/compose/`) ;
- **Helm**, dans le Kubernetes du client, avec sa propre base Postgres (`installation/helm/megga-agent/`).

## Ce que MEGGA remet au client

1. **L'image**, par son empreinte : `ghcr.io/megga/megga-agents@sha256:…`, et l'accès en lecture au registre. Le client peut vérifier qu'elle vient bien de MEGGA (`scripts/verifier_image.sh`, avec la clé publique `socle/cosign.pub`).
2. **La licence** de son installation, signée par MEGGA :

   ```bash
   .venv/bin/python scripts/licence.py emettre <id-du-client> <AAAA-MM-JJ>
   ```

   Elle n'a rien de secret : elle ne vaut que pour ce client, et seule MEGGA peut en signer une. L'agent la vérifie au démarrage, sans aucun appel au dehors. Expirée, il tourne encore 30 jours et le signale sur `/sante` ; au-delà, ou pour un autre client, il ne démarre pas.
3. **La configuration** de son agent (`client.yaml`, le format de `noyau/config.py`), avec `zone: client`.

Une seule fois, avant la première licence (Julien) : `.venv/bin/python scripts/licence.py cle`. La clé privée va dans le trousseau, la clé publique dans `noyau/licence.pub`, à commiter : elle part dans l'image.

## Ce que le client prépare

- **Son app Meta** et son numéro WhatsApp : le jeton d'accès, la clé secrète de l'app (pour vérifier la signature des webhooks), et un jeton d'abonnement qu'il choisit.
- **Ses comptes de modèles** (ou ceux que MEGGA lui fournit) : Anthropic, DeepSeek, et ElevenLabs s'il veut la voix.
- **Un nom de domaine public** pour le webhook, en HTTPS (Meta l'exige).

Les secrets restent chez lui : en variables, ou en fichiers montés par Docker, Kubernetes ou son coffre (`<NOM>_FILE=/chemin`, par exemple `ANTHROPIC_API_KEY_FILE=/run/secrets/anthropic`).

| Secret | Pour |
|---|---|
| `MEGGA_LICENCE` | la licence remise par MEGGA |
| `META_TOKEN` | répondre sur WhatsApp |
| `META_APP_SECRET` | vérifier que chaque webhook vient de Meta |
| `META_VERIFY_TOKEN` | l'abonnement du webhook (choisi par le client) |
| `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY` | les modèles |
| `ELEVENLABS_API_KEY` | facultatif : écouter les vocaux et répondre de vive voix |
| `DATABASE_URL` | Helm seulement : la base Postgres du client (Compose fournit la sienne) |

## Avec Docker Compose

Sur un serveur Linux avec Docker, le DNS du domaine pointé dessus, ports 80 et 443 ouverts :

```bash
cd installation/compose
cp exemple.env .env                    # l'image, le domaine, le mot de passe de la base
cp exemple-secrets.env secrets.env     # les secrets ; chmod 600 secrets.env
cp <configuration remise par MEGGA> client.yaml
docker compose up -d
```

L'entrée HTTPS (Caddy) obtient seule son certificat, et ne laisse passer que `/whatsapp` : `/sante` et les routes internes de l'agent ne sont jamais exposées. Pour vérifier :

```bash
docker compose ps                      # agent « healthy »
docker compose exec agent python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8080/sante').read().decode())"
```

`/sante` donne la version de l'image, son commit, l'état de la licence et `"installation": "client"`.

## Avec Helm

Le client crée son Secret (clés du tableau ci-dessus, `DATABASE_URL` comprise), puis :

```bash
helm install agent installation/helm/megga-agent \
  --set image.digest=sha256:<empreinte> \
  --set existingSecret=<son-secret> \
  --set ingress.host=<domaine> --set ingress.tlsSecret=<certificat> \
  --set-file config=<client.yaml>
```

Ou un fichier de valeurs, sur le modèle de `exemple-valeurs.yaml`. Le chart lance un seul agent (deux répondraient deux fois), le remplace en arrêtant l'ancien d'abord, lui laisse 2 minutes pour finir ses tours, le fait tourner sans droits (utilisateur 10001, disque en lecture seule), et n'expose que `/whatsapp`.

## Le webhook chez Meta

Dans l'app Meta du client, Webhooks :
- adresse : `https://<domaine>/whatsapp` ;
- jeton de vérification : `META_VERIFY_TOKEN` ;
- s'abonner au champ `messages`.

L'agent répond lui-même au défi de Meta et vérifie la signature de chaque webhook avec `META_APP_SECRET`. Ici, pas de porte de MEGGA : le webhook va directement chez le client.

## Ce qui change par rapport à Cloudflare

- **Les rappels** : pas de porte pour réveiller l'agent à l'heure dite ; il veille lui-même, chaque minute.
- **La base** : la sienne. Les migrations se jouent au démarrage ; une image démarre aussi sur une base migrée par la version suivante, pour qu'un retour arrière reste possible.
- **Les sauvegardes** : celles de sa base (Compose : le volume `base`, ou `pg_dump`). L'outil d'export de MEGGA (`noyau/stockage.py`, `exporter` et `importer`) déplace un client entier, par exemple entre deux installations.
- **Les mises à jour** : à la main pour l'instant (nouvelle empreinte, vérifiée, dans `.env` ou les valeurs Helm). Le conteneur pilote et les mises à jour signées viennent ensuite (lot 6, parties 3 et 4).
