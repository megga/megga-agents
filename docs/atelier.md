# L'atelier : construire et piloter les agents (lot 5)

Un seul moteur : la configuration du client (`noyau/config.py`). L'atelier ne fait que la remplir, la valider, l'essayer, la mettre en service et en garder les versions. Pas d'écran ici : l'interface viendra au dernier lot et ne fera qu'appeler cette API.

## Où il tourne

La même image que les agents, en service « atelier » (`MEGGA_SERVICE=atelier`), dans un conteneur unique en zone Europe, derrière la porte : tout ce qui commence par `/atelier` lui est transmis tel quel, à condition de porter un jeton (sans jeton, la porte ne réveille pas l'atelier). Sa base (versions et jetons) est un Postgres de MEGGA, posé comme celle d'un client.

## Les rôles

| Rôle | Jeton | Peut |
|---|---|---|
| MEGGA | `ADMIN_TOKEN` | tous les clients, tous les réglages, forcer une mise en service, reprendre la main |
| client | délivré par MEGGA, montré une fois | son seul agent : métier, prénom, voix, ton, outils à cocher |

Ce qu'un client ne peut pas toucher est repris tel quel de la version de base. Quand MEGGA reprend la main, le client peut encore préparer et essayer des versions, mais seul MEGGA les met en service.

## Le parcours

1. MEGGA crée le client d'une configuration complète : version 1, brouillon. Puis lui donne un jeton.
2. `valider` montre la configuration qui résulterait des changements, sans rien garder.
3. Une nouvelle version part d'une base (la dernière par défaut) : un brouillon. Dans `modeles`, `voix` et `whatsapp`, les changements se fusionnent clé par clé ; partout ailleurs, la valeur donnée remplace l'ancienne en entier (c'est ainsi qu'on retire un modèle Meta ou une voix par langue).
4. `essai` : l'agent de cette version répond, hors WhatsApp, dans une base d'essai à part. Rien ne part au numéro du client. Chaque version et chaque conversation d'essai est une personne neuve.
5. `activer` : la porte inscrit la configuration dans l'annuaire, puis le conteneur du client redémarre dès qu'il a fini ses tours en cours, et relit la configuration. La version devient publiée, donc figée, et en service. Un brouillon jamais essayé est refusé (MEGGA peut forcer). Une version d'une autre zone que celle en service est refusée : changer de zone, c'est déménager le client.
6. Revenir en arrière : `activer` une version publiée plus ancienne.

Si la mise en service s'interrompt après la porte, l'atelier remet l'annuaire sur la version d'avant. Si la porte ne répond pas (état incertain), la liste des clients signale un `ecart` entre la version que sert l'annuaire et celle de l'atelier : il suffit de relancer la mise en service.

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

Côté porte (jeton `ADMIN_TOKEN`) : `PUT /admin/clients/{id}/config` (appelée par l'atelier), `GET /admin/clients` (ou `?id=` pour un seul), `PUT /admin/atelier/secrets`. Le conteneur d'un client a une route interne `/interne/vider`, que la porte appelle avant de l'arrêter.

## Le suivi

Ce que la console montrera de chaque agent. Rien n'est copié hors du client : l'atelier demande à la porte, qui demande au conteneur du client (il se réveille s'il dormait, quelques secondes), qui lit sa propre base.

| Route | Rôle | Effet |
|---|---|---|
| `GET /clients/{id}/suivi?jours=7` | tous | état (version en service, annuaire, conteneur), activité de la période : tours, tours en échec, recours au secours, personnes, jetons par modèle, voix et vocaux, rappels en attente ; **coûts pour MEGGA seulement** |
| `GET /clients/{id}/conversations` | tous | les personnes qui ont écrit, la plus récente d'abord |
| `GET /clients/{id}/conversations/{personne}` | tous | ses derniers échanges (ce qu'elle a dit, ce que l'agent a répondu), clés et jetons masqués |
| `GET /clients/{id}/alertes?jours=7` | tous | tours, envois, vocaux, voix ou rappels en échec ; dernière panne du conteneur ; écart avec l'annuaire ; porte ou conteneur injoignable |
| `GET /tarifs`, `PUT /tarifs` | MEGGA | les tarifs : par million de jetons et par modèle (entrée, sortie, cache), la voix pour 1000 caractères, l'écoute par vocal |

D'où viennent les chiffres :
- les tours, les modèles (secours compris) et leurs jetons : les tours d'Agno, dans la base du client ;
- les échecs autour d'un tour et la voix : un petit journal du noyau (`megga_journal`), sans texte ni numéro ;
- la dernière panne d'un conteneur (démarrage, transmission, rappels) : gardée par son objet, à la porte.

Les coûts reposent sur les prix d'achat de MEGGA : ils ne se montrent qu'à MEGGA, et un modèle sans tarif est signalé (`sans_tarif`) plutôt que compté à zéro sans le dire.

## Sur les fondations d'Agno

Les versions sont les composants d'Agno 3.2 (`agno.db` : `create_component_with_config`, `upsert_config`, `set_current_version`), vérifiés sur SQLite et Postgres : brouillon modifiable, version publiée figée, numéros jamais réutilisés, retour par `set_current_version`. Les routes HTTP d'AgentOS (`/components`, `/registry`) ne sont pas exposées : elles écrivent des agents Agno sans connaître notre configuration, et leurs droits suivent l'utilisateur du jeton, pas nos rôles.

## Ce qui reste

- **Mise en route** (sur « Fusionne et déploie ») : la migration `0002` de l'annuaire passe au déploiement ; créer une base Neon pour l'atelier et la poser par `PUT /admin/atelier/secrets` (comme `scripts/secrets_client.sh`) ; puis inscrire dans l'atelier les clients déjà là (`essai-megga`, puis `megga-estates`).
- **Script d'inscription** : `scripts/inscrire_client.py` reste possible, mais son inscription ne vient d'aucune version : l'atelier montrera un écart jusqu'à la prochaine mise en service. Il demande la migration `0002`.
- **Redémarrage** : un message arrivé pendant les quelques secondes entre la fin des tours et l'arrêt du conteneur peut rester sans réponse.
- **Un numéro, un client** : `essai-megga` et `megga-estates` ont le même numéro ; la porte refusera d'activer le second tant que le premier le garde.
- **Zone suisse et chez le client** : la mise en service y est notée mais pas poussée ; elle passera par le pilotage (lot 6).
- **Connexion des clients** : un jeton par client pour l'instant ; la vraie connexion (comptes, mots de passe) viendra avec l'interface.
- **Essais** : la base d'essai est sur le disque du conteneur, effacée à chaque réveil ; un essai consomme des jetons de modèle comme une vraie conversation.
- **Agno 3.2** : sous Postgres, la table des versions a une colonne `deleted_at` que SQLite n'a pas ; l'export d'une base qui contient des versions ne se recharge pas encore dans SQLite. À régler avant de déménager la base de l'atelier.
- **Suivi** : la réécriture d'une réponse pour l'oral passe par un petit modèle dont les jetons ne sont pas encore comptés ; les tarifs restent à saisir (`PUT /tarifs`) ; les zones suisse et client auront leur suivi par le pilotage (lot 6) ; MEGGA peut lire les conversations d'un client comme lui, à confirmer.
- **Interface** : rien n'est figé côté écrans ; le catalogue et les erreurs (champ et message) sont faits pour qu'une interface les affiche telles quelles.
