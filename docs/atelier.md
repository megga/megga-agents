# L'atelier : construire et piloter les agents (lot 5)

Un seul moteur : la configuration du client (`noyau/config.py`). L'atelier ne fait que la remplir, la valider, l'essayer, la mettre en service et en garder les versions. Pas d'écran ici : l'interface viendra au dernier lot et ne fera qu'appeler cette API.

## Où il tourne

La même image que les agents, en service « atelier » (`MEGGA_SERVICE=atelier`), dans un conteneur unique en zone Europe, derrière la porte : tout ce qui commence par `/atelier` lui est transmis tel quel, à condition de porter un jeton (sans jeton, la porte ne réveille pas l'atelier). Sa base (versions et jetons) est un Postgres de MEGGA, posé comme celle d'un client.

## Les rôles

| Rôle | Jeton | Peut |
|---|---|---|
| MEGGA | `ADMIN_TOKEN` | tous les clients, tous les réglages, forcer une mise en service, reprendre la main |
| client | délivré par MEGGA, montré une fois | son seul agent : métier, prénom, voix, ton, outils à cocher |

Ce qu'un client ne peut pas toucher est repris tel quel de la version de base. Il ne met pas non plus en service une version qui change ce que MEGGA règle (le numéro WhatsApp, les modèles Meta, la gestion du site, les consignes écrites sur mesure) : revenir à une version d'avant n'est permis au client que si ces réglages sont les mêmes que ceux en service. Un modèle par métier qu'il applique garde les consignes sur mesure de MEGGA. Quand MEGGA reprend la main, le client peut encore préparer et essayer des versions, mais seul MEGGA les met en service.

## Les modèles par métier

Un modèle (« gabarit » dans le code) pré-remplit une configuration complète : métier, ton, consignes, outils, voix par défaut. Le client choisit son métier, donne un prénom, et obtient un agent qui marche tel quel ; il peut ensuite l'affiner.

| Modèle | Pour |
|---|---|
| `generaliste` | accueillir les clients, répondre, retenir, programmer des rappels |
| `immobilier` | une agence : demandes d'achat, de vente, de location, critères, rappels ; la recherche de biens s'ajoute quand MEGGA branche le catalogue de l'agence |

Un modèle ne touche jamais à ce qui tient au client (identifiant, entreprise, zone, numéro WhatsApp) ni aux réglages avancés de MEGGA (modèles de langue, catalogue, modèles Meta). Les deux usages passent par le même moteur : le client qui construit son seul agent, et MEGGA pour tous les clients.

## Les erreurs

Une configuration refusée rend, champ par champ, un message en français clair, prêt à montrer : « Le prénom doit faire 40 caractères au plus. », « Choisissez une voix dans la liste. », « Choisissez un métier : general ou immobilier. »…

```json
{"erreur": "configuration invalide", "details": [{"champ": "nom_agent", "message": "Le prénom doit faire 40 caractères au plus."}]}
```

## Le parcours

1. MEGGA crée le client d'une configuration complète : version 1, brouillon. Puis lui donne un jeton.
2. `valider` montre la configuration qui résulterait des changements, sans rien garder.
3. Une nouvelle version part d'une base (la dernière par défaut) : un brouillon. Dans `modeles`, `voix` et `whatsapp`, les changements se fusionnent clé par clé ; partout ailleurs, la valeur donnée remplace l'ancienne en entier (c'est ainsi qu'on retire un modèle Meta ou une voix par langue).
4. `essai` : l'agent de cette version répond, hors WhatsApp, dans une base d'essai à part ; avec des rôles, celui du rôle demandé (`role`, le visiteur par défaut), avec ses consignes et sans les outils du pack (ils demandent la gestion du site du client). 200 essais par agent et par jour au plus. Rien ne part au numéro du client. Chaque version et chaque conversation d'essai est une personne neuve.
5. `activer` : la porte inscrit la configuration dans l'annuaire, puis le conteneur du client redémarre dès qu'il a fini ses tours en cours, et relit la configuration. La version devient publiée, donc figée, et en service. Un brouillon jamais essayé est refusé (MEGGA peut forcer). Une version d'une autre zone que celle en service est refusée : changer de zone, c'est déménager le client. Hors Cloudflare (chez le client, zone suisse), un ordre signé part à l'installation à la place de l'annuaire (voir « Les installations hors Cloudflare »).
6. Revenir en arrière : `activer` une version publiée plus ancienne.

Si la mise en service s'interrompt après la porte, l'atelier remet l'annuaire sur la version d'avant. Si la porte ne répond pas (état incertain), la liste des clients signale un `ecart` entre la version que sert l'annuaire et celle de l'atelier : il suffit de relancer la mise en service.

## Les routes

Toutes sous `/atelier`, jeton en `Authorization: Bearer …`.

| Route | Rôle | Effet |
|---|---|---|
| `GET /catalogue` | tous | métiers, outils, zones, modèles, réglages du client |
| `GET /gabarits` | tous | les modèles par métier et leurs réglages |
| `GET /clients` | tous | les clients et leur état (annuaire, conteneur) ; un client ne voit que le sien |
| `POST /clients` | MEGGA | `{config}`, ou `{gabarit, client: {id, entreprise, zone, numero_id?}, nom_agent}` : un nouveau client (sans numéro : seulement par API) |
| `GET /clients/{id}` | tous | le client, sa version en service et sa configuration |
| `GET /clients/{id}/versions` | tous | l'historique |
| `GET /clients/{id}/versions/{v}` | tous | une version |
| `POST /clients/{id}/valider` | tous | `{base?, changements}` : la configuration résultante, sans rien garder |
| `POST /clients/{id}/versions` | tous | `{base?, changements}` : un brouillon |
| `POST /clients/{id}/gabarit` | tous | `{gabarit, nom_agent?, base?}` : un brouillon d'après un modèle par métier |
| `POST /clients/{id}/versions/{v}/essai` | tous | `{message, conversation?}` : la réponse de l'agent |
| `POST /clients/{id}/versions/{v}/activer` | tous | `{forcer?}` : mise en service ou retour |
| `POST /clients/{id}/reprise` | MEGGA | `{gere_par_megga}` : reprendre ou rendre la main |
| `POST /clients/{id}/jetons` | MEGGA | un jeton pour le client |
| `DELETE /clients/{id}/jetons` | MEGGA | retire ses jetons |
| `GET /clients/{id}/cles` | tous | les clés des logiciels du client (entrée par API), sans empreinte |
| `POST /clients/{id}/cles` | tous | `{logiciel, par_minute?}` : une clé, montrée une fois ; le client : 5 clés en service et 30 par minute au plus, MEGGA jusqu'à 600 ; une fois l'agent en service |
| `DELETE /clients/{id}/cles/{cle}` | tous | retire une clé, tout de suite |

Côté porte (jeton `ADMIN_TOKEN`) : `PUT /admin/clients/{id}/config` (appelée par l'atelier), `GET|POST /admin/clients/{id}/cles` et `DELETE /admin/clients/{id}/cles/{cle}` (transmises au conteneur du client), `GET /admin/clients` (ou `?id=` pour un seul), `PUT /admin/atelier/secrets` (sa base, et sa clé de pilotage). Le conteneur d'un client a une route interne `/interne/vider`, que la porte appelle avant de l'arrêter.

## L'entrée par API (lot 6.6)

Un logiciel du client parle à son agent sans WhatsApp, à l'adresse `https://api.megga.ai/api/<client>/messages` (`docs/api.md`, pour le développeur). Les clés se créent ici pour un client servi par la porte : l'atelier tire la clé, la rend une seule fois, et n'en envoie que l'empreinte (SHA-256) au conteneur du client, par la porte. L'empreinte est gardée dans la base du client (`megga_cles_api`), jamais dans l'atelier : une clé se vérifie là où elle sert, se retire sans redémarrage, et suit le client s'il déménage. Hors Cloudflare, l'atelier refuse (`409`) : les clés se créent sur l'installation (`python -m noyau.cles`), rien n'entrant chez le client.

Le débit d'une clé protège la facture des modèles : un client crée lui-même jusqu'à 5 clés en service, à 30 messages par minute au plus ; au-delà, MEGGA les règle (jusqu'à 600). Une clé se crée une fois une version de l'agent en service, sa base existant alors.

Un client peut n'avoir que cette entrée : sa configuration n'a alors pas de `whatsapp`, et l'annuaire pas de numéro. Les rappels WhatsApp qui attendaient encore sont alors annulés (notés `rappel_echec`, « sans WhatsApp ») ; un rappel en échec pour une autre raison est retenté 5 minutes plus tard, plus en boucle. Hors Cloudflare, une telle version n'est pas envoyée à une installation dont l'agent sert une image d'avant ce lot (nos tables en version 1, d'après son dernier relevé) : elle exigerait un numéro.

## Le suivi

Ce que la console montrera de chaque agent. Rien n'est copié hors du client : l'atelier demande à la porte, qui demande au conteneur du client, qui lit sa propre base. Un conteneur ne dort plus (17.11.2026) : l'alarme de la porte passe toutes les 4 minutes, le relance s'il s'est arrêté et repousse son sommeil ; la porte garde une lecture récente en mémoire, jamais rangée (5 minutes pour l'activité et les alertes, 1 minute pour les conversations).

| Route | Rôle | Effet |
|---|---|---|
| `GET /clients/{id}/suivi?jours=7` | tous | état (version en service, annuaire, conteneur), activité de la période : tours (dont `tours_api`, venus d'un logiciel), tours en échec, recours au secours, personnes, jetons par modèle, voix et vocaux, rappels en attente, refus de débit par API (`api_debit` du journal), `delais` (temps moyen jusqu'aux coches bleues et jusqu'à la réponse, en secondes depuis l'envoi du message, et le nombre de réponses lentes : plus de 30 s pour lire, 120 s pour répondre, notées `reponse_lente` aux alertes) ; **coûts pour MEGGA seulement** |
| `GET /clients/{id}/conversations` | tous | les personnes qui ont écrit, la plus récente d'abord |
| `GET /clients/{id}/conversations/{personne}` | tous | (un numéro, ou `api:<logiciel>:<identifiant>`) ses derniers messages, tels qu'elle les a vécus : reçus (texte, vocal transcrit) et envoyés (réponses, vocaux, rappels, messages du noyau), clés et jetons masqués |
| `GET /clients/{id}/alertes?jours=7` | tous | tours, envois, vocaux, voix ou rappels en échec ; envois refusés après coup par Meta (`envoi_refuse`, son code d'erreur) ; messages reçus trop tard pour une réponse (`message_ancien`) ; pannes du conteneur, avec l'heure où elles ont été résolues ; écart avec l'annuaire ; porte ou conteneur injoignable |
| `GET /tarifs`, `PUT /tarifs` | MEGGA | les tarifs : par million de jetons et par modèle (entrée, sortie, cache), la voix pour 1000 caractères, l'écoute par vocal |

D'où viennent les chiffres :
- les tours, les modèles (secours compris) et leurs jetons : les tours d'Agno, dans la base du client ; les jetons d'entrée sont comptés hors cache, quel que soit le fournisseur ;
- les échecs et la voix : un petit journal du noyau (`megga_journal`), sans texte ni numéro, seule source des échecs ;
- les conversations : le fil du noyau (`megga_fil`), écrit en arrière-plan comme le journal, sans jamais retarder une réponse ; celles d'avant le fil se rebâtissent des tours d'Agno ;
- les pannes d'un conteneur (démarrage, transmission, rappels) : les dix dernières, gardées par son objet à la porte, marquées résolues quand il répond de nouveau. Une alarme en échec se repose elle-même (1, 2, 5, 10, puis 15 minutes) au lieu de s'arrêter ; un webhook que le conteneur n'a pas reçu est gardé par son objet (un jour, 200 au plus) et rejoué quand il répond, lu alors jusqu'à 24 heures après son envoi. Les simples accusés de Meta (envoyé, remis, lu) ne réveillent plus le conteneur.

**Le plafond du jour** : un visiteur, un partenaire ou une personne venue par API a au plus 100 tours de modèle par jour, et tous ensemble 2 000 par client (`noyau/garde.py`, `Plafond`) ; au-delà, une phrase polie, une fois, puis plus rien jusqu'au lendemain (429 par API), et l'alerte `plafond`. Les gestionnaires ne sont jamais arrêtés. Un tour appelle 25 outils au plus.

**Le relevé chiffré** (20.11.2026) : la console de MEGGA suit tous les clients d'un coup, sans réveiller aucun conteneur et sans jamais voir une conversation.

| Route | Rôle | Effet |
|---|---|---|
| `GET /releves?jours=7` | MEGGA | chaque agent, jour par jour (UTC) : tours, tours par API, échecs, secours, personnes, jetons par modèle, totaux du journal, délais ; son coût de chaque jour, l'écart de version, son état au dernier relevé et `silencieux` (actif, sans relevé depuis 40 minutes) ; 400 jours au plus |

D'où il vient :
- le conteneur le calcule (`GET /interne/releve`, `noyau/suivi.py`, `releve`) : aujourd'hui et hier, d'après les tours d'Agno et le journal ; aucun texte, nom ni numéro, ni le détail technique du journal ;
- à son alarme, au plus tous les quarts d'heure, l'objet du client à la porte le lit, le reconstruit champ par champ (`porte/src/releves.js`, `nettoyer` : seulement des nombres et des noms de modèle, de fournisseur, de genre ou de version permis) et le range dans l'annuaire (tables `releves` et `etats`, migration `0004`), avec l'état du conteneur (démarré, genre et heure des pannes, sans leur message) ; 400 jours gardés ;
- l'atelier les lit tous en un appel (`GET /admin/releves` de la porte) et ajoute ce que lui seul sait : l'entreprise, la version en service, les coûts aux tarifs de MEGGA.

Un relevé en échec est noté aux pannes du conteneur (`releve`) sans arrêter les rappels, et retenté au quart d'heure suivant. Les installations hors Cloudflare n'y sont pas encore : leur suivi vient toujours de leur pilote.

MEGGA lit les conversations d'un client comme le client lui-même, pour l'aider et reprendre la main (décision de Julien, 15.11.2026).

Les coûts reposent sur les prix d'achat de MEGGA : ils ne se montrent qu'à MEGGA, et un modèle sans tarif est signalé (`sans_tarif`) plutôt que compté à zéro sans le dire.

## Les installations hors Cloudflare (lot 6.3)

Chez le client (puis en zone suisse), aucun accès entrant : le pilote de l'installation appelle la porte chaque minute (`POST /pilotage/releve`), qui transmet à l'atelier sans réveiller personne si la requête n'est pas signée et récente. L'atelier vérifie la signature avec la clé publique enregistrée pour ce client, refuse une requête rejouée, garde le dernier relevé, et répond avec les ordres qui attendent. La signature couvre aussi l'installation que la requête dit être, et une clé ne sert qu'une installation. Un relevé est contrôlé avant d'être gardé (nombres finis, forme de l'état et du suivi) ; la porte refuse un corps sans longueur annoncée ou de plus de 256 Kio. Le pilote : `pilote/` ; le protocole : `noyau/pilotage.py` ; le guide côté client : `docs/installation-client.md`.

| Route | Rôle | Effet |
|---|---|---|
| `GET /installations` | MEGGA | les installations, leur dernier relevé (silencieuse au-delà de 5 minutes), leur réglage de pilotage, l'écart ; `cle_pilotage` : l'atelier peut signer |
| `GET /clients/{id}/installation` | tous | l'installation, ses 20 derniers ordres et le journal du pilotage |
| `PUT /clients/{id}/installation` | MEGGA | `{cle_publique}` : la mise en service, avec la clé que l'installation a remise (`python -m pilote cle`) |
| `DELETE /clients/{id}/installation` | MEGGA | révoque sa clé : plus aucun relevé accepté |
| `POST /clients/{id}/installation/image` | MEGGA | `{version, image}` : une version d'image (par son empreinte) ; le pilote la vérifie et l'installe si le client l'a permis (`MISES_A_JOUR`), sinon elle est proposée |

**Les ordres** : signés par la clé de pilotage de l'atelier (`PILOTAGE_CLE`, distincte de celle des licences), vérifiés par l'installation avec la clé publique de l'image (`noyau/pilotage.pub`). Une semaine pour aboutir, quel que soit le mode de l'installation. Ils partent seulement si le client a choisi `PILOTAGE=complet`. Une configuration part sans les réglages laissés à leur valeur par défaut : une installation restée sur l'image précédente l'accepte encore quand un réglage facultatif s'ajoute (règle qui va avec : ne jamais changer une valeur par défaut sans changer `VERSION` de la configuration).
- `activer` d'une version hors Cloudflare : la version est mise en service dans l'atelier, puis un ordre part. Un ordre du même genre qui n'était pas encore parti est remplacé. Renvoyer la version en service est permis tant que l'installation ne la sert pas (ordre refusé, en échec ou expiré).
- Leurs états : `en_attente`, `remis`, puis ce qu'en dit l'installation : `attente_accord`, `a_appliquer`, `applique`, `propose` (une image que le client installe à la main), `refuse`, `echec`, `remplace`, `retire` (le client est revenu à son fichier), `expire`.
- Une image (`MISES_A_JOUR=oui` chez le client, `mises_a_jour` dans l'installation) : `a_appliquer` avance sans changer d'état, et chaque étape arrive au journal (signature vérifiée, base sauvegardée et image remplacée) ; puis `applique` quand l'agent répond sur la nouvelle version, ou `echec` avec retour à l'image d'avant. Le détail : `docs/installation-client.md`, « Les mises à jour de l'image ». MEGGA ne propose jamais une version qui saute une migration (deux versions soutenues).
- L'écart : l'installation ne sert pas la version en service dans l'atelier, d'après son dernier relevé ; inconnu si l'agent n'a pas répondu à ce relevé (renvoyer la version attend alors le relevé suivant).

**Le suivi** d'une installation vient de son dernier relevé, calculé chez elle toutes les 5 minutes : `jours` vaut 1, 7 ou 30, et la réponse dit quand il a été calculé. Les coûts, pour MEGGA seulement, comme ailleurs. Les alertes y ajoutent l'installation silencieuse ou révoquée, l'agent en panne, la licence expirée, l'écart, et les ordres refusés, en échec ou expirés. Les conversations ne quittent jamais l'installation : `409`, même pour MEGGA.

**Le journal** du pilotage (`megga_pilotage`) garde, des deux côtés, chaque clé enregistrée ou révoquée et chaque ordre : déposé, par qui, remis, puis ce qu'il est devenu.

## Sur les fondations d'Agno

Les versions sont les composants d'Agno 3.2 (`agno.db` : `create_component_with_config`, `upsert_config`, `set_current_version`), vérifiés sur SQLite et Postgres : brouillon modifiable, version publiée figée, numéros jamais réutilisés, retour par `set_current_version`. Les routes HTTP d'AgentOS (`/components`, `/registry`) ne sont pas exposées : elles écrivent des agents Agno sans connaître notre configuration, et leurs droits suivent l'utilisateur du jeton, pas nos rôles.

## Ce qui reste

- **Mise en route** (sur « Fusionne et déploie ») : la migration `0002` de l'annuaire passe au déploiement ; créer une base Neon pour l'atelier et la poser par `PUT /admin/atelier/secrets` (comme `scripts/secrets_client.sh`) ; puis inscrire dans l'atelier les clients déjà là (`essai-megga`, puis `megga-estates`).
- **Script d'inscription** : `scripts/inscrire_client.py` reste possible, mais son inscription ne vient d'aucune version : l'atelier montrera un écart jusqu'à la prochaine mise en service. Il demande la migration `0002`.
- **Redémarrage** : un message arrivé pendant les quelques secondes entre la fin des tours et l'arrêt du conteneur peut rester sans réponse.
- **Un numéro, un client** : `essai-megga` et `megga-estates` ont le même numéro ; la porte refusera d'activer le second tant que le premier le garde.
- **Installations hors Cloudflare** : piloter une installation garde l'atelier éveillé (un relevé par minute ; environ 7,5 $ par mois pour le conteneur), et aussi le calcul Neon de sa base, qui ne passe plus en veille : environ 19 $ par mois de plus, et davantage s'il est partagé avec les bases des clients. À régler avant la première installation pilotée : une petite base Neon à part pour l'atelier, ou des relevés absorbés par la porte quand rien ne change. La zone suisse viendra avec Exoscale.
- **Mises à jour de l'image (lot 6.4)** : aucune installation n'en accepte tant que `socle/cosign.pub` n'existe pas (`scripts/cle_signature.sh`, Julien), puis qu'une version n'est pas publiée avec elle. Sous Helm avec Argo CD ou Flux (sans lecture du cluster), les mises à jour par le pilote restent à éviter ; le droit de changer les deux Deployments couvre tout leur pod, à fermer chez le client par une ValidatingAdmissionPolicy (à écrire avec lui). La rotation des clés de pilotage et de signature (une image qui porte l'ancienne et la nouvelle le temps du passage) n'est pas traitée. La restauration d'une sauvegarde reste à la main.
- **Entrée par API (lot 6.6)** : la migration `0003` de l'annuaire passe au déploiement ; la base de chaque client passe à la version 2 de nos tables à son réveil. Le débit d'une clé est tenu en mémoire du conteneur (remis à zéro au redémarrage). Avant le déploiement : la zone `megga.ai` doit être sur le compte Cloudflare de MEGGA (`docs/deploiement.md`). Restent : un domaine par client (Cloudflare for SaaS, une colonne domaine dans l'annuaire, la recherche par hôte), plus tard et seulement si un client le demande ; un appel vers le logiciel (webhook) pour les rappels, les vocaux, la réponse au fil de l'eau, et une limite à la porte avant le réveil d'un conteneur (Cloudflare Rate Limiting) si des clés mal formées ou devinées arrivaient en nombre.
- **Inscription d'un client** : créer le compte (identifiant, entreprise, zone, numéro WhatsApp) reste à MEGGA ; le client règle ensuite son agent lui-même.
- **Connexion des clients** : un jeton par client pour l'instant ; la vraie connexion (comptes, mots de passe) viendra avec l'interface.
- **Essais** : la base d'essai est sur le disque du conteneur, effacée à chaque réveil ; un essai consomme des jetons de modèle comme une vraie conversation.
- **Agno 3.2** : sous Postgres, la table des versions a une colonne `deleted_at` que SQLite n'a pas ; l'export d'une base qui contient des versions ne se recharge pas encore dans SQLite. À régler avant de déménager la base de l'atelier.
- **Suivi** : la réécriture d'une réponse pour l'oral passe par un petit modèle dont les jetons ne sont pas encore comptés ; les tarifs restent à saisir (`PUT /tarifs`).
- **Interface** : rien n'est figé côté écrans ; le catalogue et les erreurs (champ et message) sont faits pour qu'une interface les affiche telles quelles.
