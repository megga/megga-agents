# Installer l'agent MEGGA chez le client

L'offre premium : l'agent tourne sur le serveur ou dans le cloud du client (Azure, AWS, son Kubernetes…). Ses conversations, sa base et ses fichiers ne quittent pas son infrastructure. Seuls partent les appels aux modèles (Claude, DeepSeek) et à la voix (ElevenLabs), vers les comptes que le client a choisis : il doit le savoir.

C'est la même image signée que chez MEGGA. Deux façons de l'installer :
- **Docker Compose**, sur un serveur : l'agent, sa base Postgres, une entrée HTTPS et le pilote (`installation/compose/`) ;
- **Helm**, dans le Kubernetes du client, avec sa propre base Postgres (`installation/helm/megga-agent/`).

Le pilote, à côté de l'agent, permet à MEGGA de suivre l'installation et, si le client le veut, d'en changer la configuration. Il appelle MEGGA, jamais l'inverse (voir « Le pilotage par MEGGA »).

## Ce que MEGGA remet au client

1. **L'image**, par son empreinte : `ghcr.io/megga/megga-agents@sha256:…`, et un jeton de lecture du registre (privé) de MEGGA. Le client peut vérifier qu'elle vient bien de MEGGA (`scripts/verifier_image.sh`, avec la clé publique `socle/cosign.pub`).
2. **La licence** de son installation, signée par MEGGA :

   ```bash
   .venv/bin/python scripts/licence.py emettre <id-du-client> <AAAA-MM-JJ>
   ```

   Elle n'a rien de secret : elle ne vaut que pour ce client, et seule MEGGA peut en signer une. L'agent la vérifie au démarrage, sans aucun appel au dehors, puis à chaque appel. Expirée, il tourne encore 30 jours et le signale sur `/sante` ; au-delà, un agent déjà lancé cesse de servir (`/sante` et le webhook répondent 503) et il ne redémarre plus. Pour un autre client, il ne démarre pas.
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
| `PILOTE_CLE` | le pilote seulement : la clé de l'installation (voir « Le pilotage par MEGGA ») |

## L'accès au registre

L'image est dans le registre privé de MEGGA. Avec le jeton de lecture remis par MEGGA :

```bash
docker login ghcr.io -u <compte remis par MEGGA> --password-stdin
```

(le jeton se colle, puis Ctrl-D). Pour Kubernetes, le même accès dans un Secret de type `docker-registry` pour `ghcr.io`, donné au chart par `image.pullSecrets` (`[{name: <ce secret>}]`).

## Avec Docker Compose

Sur un serveur Linux avec Docker, le DNS du domaine pointé dessus, ports 80 et 443 ouverts :

```bash
cd installation/compose
cp exemple.env .env                    # l'image, le domaine, le mot de passe de la base, le pilotage
cp exemple-secrets.env secrets.env     # les secrets ; chmod 600 secrets.env
cp <configuration remise par MEGGA> client.yaml
(umask 077; echo "PILOTE_CLE=$(openssl genpkey -algorithm ed25519 -outform DER | base64)" > pilote.env)
docker compose up -d
```

La quatrième ligne crée la clé de l'installation, sans l'afficher ; elle ne sert qu'au pilote. Avec `PILOTAGE=non`, elle peut attendre.

Sans `client.yaml`, l'installation s'arrête net (« bind source path does not exist ») au lieu de démarrer un agent sans configuration. L'entrée HTTPS (Caddy) obtient seule son certificat, et ne laisse passer que `/whatsapp` : `/sante` et les routes internes de l'agent ne sont jamais exposées. Pour vérifier :

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

Ou un fichier de valeurs, sur le modèle de `exemple-valeurs.yaml`.

Le pilote, avec `pilotage.mode` à `suivi` ou `complet` : sa clé dans un Secret à part (clé `PILOTE_CLE`, donné par `pilotage.secret`), ou en fichier depuis le coffre (`pilotage.extraEnv` avec `PILOTE_CLE_FILE`). Il ne reçoit que sa clé et l'adresse de la base, jamais les clés des modèles ni celles de Meta.

- **Secrets en fichiers** : sans Secret Kubernetes, le coffre du client (pilote CSI de Vault, Key Vault…) monte ses fichiers par `extraVolumes` et `extraVolumeMounts`, et chaque secret se déclare dans `extraEnv` sous la forme `<NOM>_FILE` (par exemple `ANTHROPIC_API_KEY_FILE=/mnt/secrets/anthropic`).
- **HTTPS** : exigé par Meta. Le chart refuse de s'installer sans `ingress.tlsSecret`, sauf `ingress.tlsAilleurs=true` si un répartiteur de charge l'assure devant l'ingress.

Le chart lance un seul agent (deux répondraient deux fois), le remplace en arrêtant l'ancien d'abord, le fait tourner sans droits (utilisateur 10001, disque en lecture seule), et n'expose que `/whatsapp`.

## Le webhook chez Meta

Dans l'app Meta du client, Webhooks :
- adresse : `https://<domaine>/whatsapp` ;
- jeton de vérification : `META_VERIFY_TOKEN` ;
- s'abonner au champ `messages`.

L'agent répond lui-même au défi de Meta et vérifie la signature de chaque webhook avec `META_APP_SECRET`. Ici, pas de porte de MEGGA : le webhook va directement chez le client.

## Ce qui change par rapport à Cloudflare

- **Les rappels** : pas de porte pour réveiller l'agent à l'heure dite ; il veille lui-même, chaque minute.
- **L'arrêt** (mise à jour, redémarrage) : l'agent finit d'abord ses tours en cours et sa tournée de rappels, 100 secondes au plus ; Compose et le chart attendent 2 minutes avant de le forcer.
- **La base** : la sienne. Les migrations se jouent au démarrage ; une image démarre aussi sur une base migrée par la version suivante, pour qu'un retour arrière reste possible.
- **Les sauvegardes** : celles de sa base (Compose : le volume `base`, ou `pg_dump`). L'outil d'export de MEGGA (`noyau/stockage.py`, `exporter` et `importer`) déplace un client entier, par exemple entre deux installations.
- **La configuration** : changée par MEGGA à travers le pilote, si le client le permet (`PILOTAGE=complet`) ; sinon dans son `client.yaml` (redémarrer l'agent pour qu'il le relise).
- **Les mises à jour de l'image** : à la main pour l'instant (nouvelle empreinte, vérifiée, dans `.env` ou les valeurs Helm). MEGGA peut déjà en proposer une par le pilote, qui la note ; son installation par le pilote viendra avec les mises à jour signées (lot 6, partie 4).

## Le pilotage par MEGGA

Un petit service à côté de l'agent, la même image. Il appelle MEGGA en HTTPS, chaque minute : aucun port n'est ouvert chez le client, rien n'entre. Le client choisit ce qui sort, dans `.env` (ou `pilotage.mode` du chart) :

| `PILOTAGE` | Ce qui sort |
|---|---|
| `non` | rien : le pilote ne fait rien (par défaut) |
| `suivi` | l'état de l'agent (version, licence, configuration servie), les volumes, les modèles et leurs jetons, les échecs ; jamais une conversation, un texte ni un numéro |
| `complet` | le suivi, et MEGGA peut changer la configuration de l'agent ou proposer une version de l'image |

**La clé de l'installation** : créée chez le client (`pilote.env` ci-dessus), elle ne quitte jamais son serveur. Le client remet sa partie publique à MEGGA, qui l'enregistre à la mise en service :

```bash
docker compose exec pilote python -m pilote cle
```

Chaque appel du pilote est signé de cette clé, à l'heure près (5 minutes) et jamais deux fois le même. MEGGA peut la révoquer ; le client aussi, en retirant `pilote.env` ou en passant `PILOTAGE=non`. Une nouvelle clé se remet de la même façon.

**Les ordres de MEGGA** (avec `PILOTAGE=complet`) : une version de la configuration de l'agent, venue de l'atelier, ou une version de l'image proposée. Aucune commande libre. Chaque ordre est signé par MEGGA, vérifié par le pilote (signature, client, zone, configuration valide, une semaine au plus), puis inscrit à son journal, comme chez MEGGA.

**L'accord du client** : avec `PILOTAGE_ACCORD=oui` (le réglage d'exemple), chaque ordre attend son oui.

```bash
docker compose exec pilote python -m pilote ordres        # les ordres, et ce qui changerait
docker compose exec pilote python -m pilote accepter 12
docker compose exec pilote python -m pilote refuser 12
docker compose exec pilote python -m pilote revenir       # l'agent revient à client.yaml
docker compose exec pilote python -m pilote journal       # ce qui s'est passé, le plus récent d'abord
```

Sous Kubernetes, les mêmes commandes : `kubectl exec deploy/<nom>-megga-agent-pilote -- python -m pilote ordres`.

**Comment l'agent change de configuration** : le pilote note la nouvelle version dans la base de l'installation, signature comprise ; `client.yaml` reste en lecture seule et n'est jamais réécrit. Dans la minute, l'agent la voit, finit ses tours en cours et s'arrête ; Compose ou Kubernetes le relancent, et il sert la nouvelle version après en avoir revérifié la signature (une version retouchée dans la base ne sert jamais : l'agent reprend `client.yaml`). S'il ne la sert pas dans les 10 minutes, elle est marquée en échec et l'agent revient à la précédente. Le pilote n'a besoin ni de Docker ni de l'API de Kubernetes.

**Une version d'image proposée** est notée et montrée (`python -m pilote ordres`) ; le client peut la refuser. Son installation par le pilote viendra au lot 6.4.
