# Les connecteurs de Composio

[Composio](https://github.com/ComposioHQ/composio) (SDK sous licence MIT) tient plus de mille boîtes d'outils (Gmail, Google Agenda, Outlook, HubSpot, Notion, Slack...) et les connexions aux comptes de leurs utilisateurs. MEGGA s'en sert pour qu'un agent agisse dans les propres comptes d'un client : lire un agenda, envoyer un e-mail, créer un contact.

Le code est dans `noyau/composio.py` (l'agent) et `atelier/routes_composio.py` (l'atelier). On appelle l'API de Composio en HTTP, sans son SDK, qui tirerait OpenAI et d'autres dépendances dans l'image.

## Comment c'est rangé

- **Un seul projet Composio, celui de MEGGA.** Sa clé, `COMPOSIO_API_KEY`, est un secret de la porte, remis aux conteneurs des clients et à l'atelier, comme les clés des modèles.
- **Chaque client y est un utilisateur**, sous son identifiant (`Config.id`). Ses comptes connectés ne servent qu'à son agent.
- **Les outils se choisissent un par un**, par MEGGA, dans la configuration du client : `composio.outils`, leurs noms Composio en majuscules (`GMAIL_SEND_EMAIL`, 40 au plus). Aucun autre outil de Composio n'arrive à l'agent.
- **L'agent les reçoit par le groupe `connecteurs`**, ouvert à tout métier : dans `outils` pour un agent sans rôles, dans `roles.<rôle>.outils` sinon. Sans `composio`, l'atelier le signale (`manques`).
- **Le client connecte ses comptes lui-même**, par un lien de Composio que MEGGA crée dans l'atelier. MEGGA ne voit jamais ses identifiants, et l'atelier ne rend aucun jeton.

```yaml
outils: [connecteurs]
composio:
  outils: [GOOGLECALENDAR_FIND_FREE_SLOTS, GOOGLECALENDAR_CREATE_EVENT, GMAIL_SEND_EMAIL]
```

## Ce que l'agent en fait

Chaque outil choisi devient un outil d'Agno, avec la description et le schéma que Composio en donne. L'agent reçoit aussi une consigne (en anglais, comme ses autres textes) : un outil qui envoie, crée, modifie ou supprime ne s'appelle que si la personne l'a clairement demandé, et une action n'est dite faite que si l'outil l'a confirmée.

Si Composio ne répond pas au démarrage, l'agent sert sans ses connecteurs (un avertissement dans le journal). Si un outil échoue, l'agent lit « Échec de l'outil... Rien n'a été fait » et le dit.

Il n'y a pas encore d'approbation avant une action (lot 9.1, pas sur `main`) : MEGGA ne donne donc que les outils qu'on peut laisser faire à l'agent sans relecture.

## Mettre en route (Julien)

1. Créer le projet MEGGA sur [composio.dev](https://composio.dev) et sa clé d'API.
2. La poser comme secret de la porte : `npx wrangler secret put COMPOSIO_API_KEY` (dans `porte/`), puis redéployer.
3. Dans Composio, créer une configuration d'authentification par boîte d'outils (Gmail, Google Agenda...) : son identifiant commence par `ac_`.
4. Pour un client : `POST /atelier/clients/<id>/composio/lien` avec `{"auth_config": "ac_..."}`, puis lui envoyer le lien rendu. `GET /atelier/clients/<id>/composio/comptes` montre ensuite ses comptes connectés.
5. Dans sa configuration : `outils: [connecteurs]` et la liste `composio.outils`, puis mettre la version en service.
