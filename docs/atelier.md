# L'atelier : construire et piloter les agents (lot 5)

Un seul moteur : la configuration du client (`noyau/config.py`). L'atelier ne fait que la remplir, la valider, l'essayer, la mettre en service et en garder les versions. Pas d'écran ici : l'interface viendra au dernier lot et ne fera qu'appeler cette API.

## Où il tourne

La même image que les agents, en service « atelier » (`MEGGA_SERVICE=atelier`), dans un conteneur unique en zone Europe, derrière la porte : tout ce qui commence par `/atelier` lui est transmis tel quel. Sa base (versions et jetons) est un Postgres de MEGGA, posé comme celle d'un client.

## Les rôles

| Rôle | Jeton | Peut |
|---|---|---|
| MEGGA | `ADMIN_TOKEN` | tous les clients, tous les réglages, forcer une mise en service, reprendre la main |
| client | délivré par MEGGA, montré une fois | son seul agent : métier, prénom, voix, ton, outils à cocher |

Ce qu'un client ne peut pas toucher est repris tel quel de la version de base. Quand MEGGA reprend la main, le client peut encore préparer et essayer des versions, mais seul MEGGA les met en service.

## Le parcours

1. MEGGA crée le client d'une configuration complète : version 1, brouillon. Puis lui donne un jeton.
2. `valider` montre la configuration qui résulterait des changements, sans rien garder.
3. Une nouvelle version part d'une base (la dernière par défaut) : un brouillon.
4. `essai` : l'agent de cette version répond, hors WhatsApp, dans une base d'essai à part. Rien ne part au numéro du client.
5. `activer` : la porte inscrit la configuration dans l'annuaire et redémarre le conteneur du client, qui la relit au réveil. La version devient publiée, donc figée, et en service. Un brouillon jamais essayé est refusé (MEGGA peut forcer).
6. Revenir en arrière : `activer` une version publiée plus ancienne.

## Les routes

Toutes sous `/atelier`, jeton en `Authorization: Bearer …`.

| Route | Rôle | Effet |
|---|---|---|
| `GET /catalogue` | tous | métiers, outils, zones, modèles, réglages du client |
| `GET /clients` | tous | les clients et leur état (annuaire, conteneur) ; un client ne voit que le sien |
| `POST /clients` | MEGGA | `{config}` : un nouveau client |
| `GET /clients/{id}` | tous | le client, sa version en service et sa configuration |
| `GET /clients/{id}/versions` | tous | l'historique |
| `GET /clients/{id}/versions/{v}` | tous | une version |
| `POST /clients/{id}/valider` | tous | `{base?, changements}` : la configuration résultante, sans rien garder |
| `POST /clients/{id}/versions` | tous | `{base?, changements}` : un brouillon |
| `POST /clients/{id}/versions/{v}/essai` | tous | `{message, conversation?}` : la réponse de l'agent |
| `POST /clients/{id}/versions/{v}/activer` | tous | `{forcer?}` : mise en service ou retour |
| `POST /clients/{id}/reprise` | MEGGA | `{gere_par_megga}` : reprendre ou rendre la main |
| `POST /clients/{id}/jetons` | MEGGA | un jeton pour le client |
| `DELETE /clients/{id}/jetons` | MEGGA | retire ses jetons |

Côté porte (jeton `ADMIN_TOKEN`) : `PUT /admin/clients/{id}/config` (appelée par l'atelier), `GET /admin/clients`, `PUT /admin/atelier/secrets`.

## Sur les fondations d'Agno

Les versions sont les composants d'Agno 3.2 (`agno.db` : `create_component_with_config`, `upsert_config`, `set_current_version`), vérifiés sur SQLite et Postgres : brouillon modifiable, version publiée figée, numéros jamais réutilisés, retour par `set_current_version`. Les routes HTTP d'AgentOS (`/components`, `/registry`) ne sont pas exposées : elles écrivent des agents Agno sans connaître notre configuration, et leurs droits suivent l'utilisateur du jeton, pas nos rôles.

## Ce qui reste

- **Mise en route** (sur « Fusionne et déploie ») : la migration `0002` de l'annuaire passe au déploiement ; créer une base Neon pour l'atelier et la poser par `PUT /admin/atelier/secrets` (comme `scripts/secrets_client.sh`) ; puis inscrire dans l'atelier les clients déjà là (`essai-megga`, puis `megga-estates`).
- **Un numéro, un client** : `essai-megga` et `megga-estates` ont le même numéro ; la porte refusera d'activer le second tant que le premier le garde.
- **Zone suisse et chez le client** : la mise en service y est notée mais pas poussée ; elle passera par le pilotage (lot 6).
- **Connexion des clients** : un jeton par client pour l'instant ; la vraie connexion (comptes, mots de passe) viendra avec l'interface.
- **Essais** : la base d'essai est sur le disque du conteneur, effacée à chaque réveil ; un essai consomme des jetons de modèle comme une vraie conversation.
- **Agno 3.2** : sous Postgres, la table des versions a une colonne `deleted_at` que SQLite n'a pas ; l'export d'une base qui contient des versions ne se recharge pas encore dans SQLite. À régler avant de déménager la base de l'atelier.
- **Interface** : rien n'est figé côté écrans ; le catalogue et les erreurs (champ et message) sont faits pour qu'une interface les affiche telles quelles.
