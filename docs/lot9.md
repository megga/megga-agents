# Lot 9 : les fonctionnalités du lancement

D'après l'étude de marché du 16.11.2026 (le catalogue des fonctionnalités indispensables), en commençant par celles qui ne demandent aucun compte chez un tiers. Une branche et une PR par sous-lot ; rien n'est déployé sans « Fusionne et déploie » de Julien.

| Sous-lot | Contenu |
|---|---|
| **9.1 Approbations et journal d'audit** (fait) | une règle par outil (accord d'un gestionnaire, ou interdit), le journal de chaque appel d'outil, la décision sur WhatsApp ou dans la console |
| **9.2 Base de connaissances** (cette PR) | les documents du client, une recherche par le sens calculée dans l'image (aucune donnée ne sort), des réponses qui citent leur source |
| 9.3 Transfert vers un humain | passer la main à un collaborateur avec un résumé, puis la reprendre |
| 9.4 Leads et connecteurs | la fiche d'un lead vers un webhook ou un tableur ; un client MCP dans le noyau |
| 9.5 Le client et ses chiffres | le retour sur investissement visible du client, la conformité (mention de l'IA, export et effacement par personne), le choix des modèles par le client |
| 9.6 Banc d'essai par pack | les scénarios de `parite/` généralisés, mesurés en pass^k à chaque version |

Décidé avec Thomas (16.11.2026) : une PR par sous-lot ; d'abord ce qui ne demande aucun compte externe (les agendas Google et Microsoft viendront après) ; la recherche par le sens calculée par un modèle embarqué dans l'image ; le choix des modèles laissé au client plutôt qu'un secours imposé.

## 9.1 Les approbations et le journal d'audit

**Pourquoi.** Un agent WhatsApp lit les messages d'inconnus, voit les données du client et peut agir (envoyer une fiche, transmettre un contact, créer une annonce). Une consigne glissée dans un message peut lui faire appeler un outil qu'il ne devrait pas ; aucun filtre ne détecte ces injections de façon fiable. L'accord d'une personne de l'entreprise sur les actions qui comptent est la défense qui tient ; le journal permet de vérifier ce qui a été fait.

**La règle d'un outil** (`Config.approbations`, et `Role.approbations` par-dessus pour les personnes d'un rôle) : `{nom de l'outil: "approbation" | "interdit"}`. Un outil absent se fait sans accord, comme avant.
- `interdit` : l'outil n'est même pas proposé au modèle ; appelé quand même, il est refusé.
- `approbation` : l'action n'est pas faite. La demande (l'outil et ses arguments) est gardée dans la base du client (`megga_approbations`) ; le modèle reçoit « Demande n envoyée à l'équipe… » et le dit à la personne.

Le client règle lui-même les approbations de son agent (`approbations` est un champ du client dans l'atelier) : c'est lui qui porte le risque d'une action. Celles d'un rôle restent un réglage de MEGGA.

**Le crochet** (`noyau/approbations.py`, `Gardien`). Tous les outils d'un agent passent par un crochet d'Agno (`tool_hooks`), qui connaît l'outil, ses arguments et la personne (`run_context`). Les outils eux-mêmes ne changent pas : la règle s'ajoute autour, pour les outils du noyau comme pour ceux des packs.

**La décision.**
- Sur WhatsApp : chaque gestionnaire (secret `GESTIONNAIRES`) reçoit la demande, une fois fini le tour de la personne qui l'a faite, avec ses arguments (secrets masqués) et une liste « Accepter » ou « Refuser ». Le choix touché est traité sans le modèle (préfixe `ap:`, comme les choix des partenaires) et seulement pour un gestionnaire. Hors des 24 heures, la demande attend son prochain message (modèle Meta `approbation` s'il est réglé).
- Dans la console : `POST /atelier/clients/{id}/approbations/{n}` `{accord}`, pour le client comme pour MEGGA.
- Une décision ne se prend qu'une fois (écriture conditionnelle) : deux gestionnaires qui touchent en même temps ne font pas l'action deux fois. Sans réponse en 48 heures, la demande expire. Une personne a au plus 20 demandes qui attendent.

**L'action accordée** est faite au nom de la personne qui l'a demandée (son `run_context`), avec les arguments gardés, par l'outil du même nom de son rôle. La personne reçoit un court message (« l'équipe a validé votre demande, c'est fait », en français ou en anglais selon la langue de l'agent ; modèle Meta `approbation_reponse` hors des 24 heures), et son agent en connaît le détail à son tour suivant (le Contexte, entre balises `<approbations>`, dit une seule fois).

**Le journal d'audit** (`megga_audit`) : chaque appel d'outil, accordé ou pas, avec l'outil, la personne, la règle, l'issue (`fait`, `erreur`, `refuse`, `attente`) et la durée ; jamais ses arguments ni son résultat (ce qu'une action a fait se lit dans la conversation, ou dans sa demande d'accord). Écrit en arrière-plan, il ne retarde ni ne fait échouer un tour ; à l'arrêt du service, les lignes encore en route sont attendues avec les tours. Gardé trois mois.

**Les routes.**

| Route | Rôle | Effet |
|---|---|---|
| `GET /atelier/clients/{id}/audit?jours=7` | tous | les appels d'outils de la période, les plus récents d'abord |
| `GET /atelier/clients/{id}/approbations?etat=attente` | tous | les demandes (`attente`, `accordee`, `faite`, `echec`, `refusee`, `expiree`), leurs arguments en aperçu masqué |
| `POST /atelier/clients/{id}/approbations/{n}` | tous | `{accord: true|false}` : l'action accordée est faite tout de suite ; `409` si la demande n'attend plus |

Côté porte : `GET /admin/clients/{id}/suivi/audit|approbations` (lues une minute en mémoire) et `POST /admin/clients/{id}/approbations/{n}` (jeton `ADMIN_TOKEN`), transmises au conteneur (`/interne/suivi/audit`, `/interne/suivi/approbations`, `/interne/approbations/{n}`). Hors Cloudflare, comme les conversations, rien ne quitte l'installation (`409`) : elle décide sur WhatsApp, par ses gestionnaires.

**Les tables** (additives, sans changer `SCHEMA_VERSION`) : `megga_audit`, `megga_approbations` ; exportées et importées avec le reste du client.

**Ce qui reste.**
- Les noms des outils ne sont pas encore listés par le catalogue de l'atelier (ils dépendent des packs et des rôles) : la console devra les montrer pour qu'on les coche.
- Sans gestionnaires (un agent sans rôles), la décision ne se prend que dans la console : l'équipe n'est prévenue de rien sur WhatsApp. Une alerte du suivi pour les demandes qui attendent viendra avec la console.
- Les modèles Meta `approbation` et `approbation_reponse` sont à soumettre si un client veut décider hors des 24 heures.

## 9.2 La base de connaissances

**Pourquoi.** La qualité des réponses est le premier frein cité par les entreprises, et l'analyse de documents leur premier cas d'usage (étude de marché, section 3). Un agent qui répond d'après les documents du client (tarifs, conditions, horaires, procédures) et qui cite sa source, ou qui dit qu'il ne sait pas, invente moins.

**Le groupe d'outils `connaissances`**, dans `Config.outils` (l'agent sans rôles) ou dans les outils d'un rôle : il ne va qu'aux rôles qu'on choisit (un partenaire, qui ne doit jamais voir un prix, ne l'a pas d'office). Il donne l'outil `chercher_dans_les_documents` et une consigne : chercher d'abord dans les documents, citer leur titre entre parenthèses, dire simplement quand rien ne répond. Les deux métiers le permettent.

**Rien ne sort de la zone du client** (décidé avec Thomas le 16.11.2026) : ni les documents, ni les questions. Le modèle de recherche par le sens est embarqué dans l'image :
- `paraphrase-multilingual-MiniLM-L12-v2`, quantifié en int8 (ONNX, 118 Mo) : français, allemand, italien, anglais, et d'une langue à l'autre (une question en français trouve un passage en allemand) ;
- posé à la construction de l'image par `socle/modele.py`, révision de Hugging Face et empreintes SHA-256 figées : un fichier changé arrête la construction ; la CI vérifie que le modèle de l'image répond juste (`python -m noyau.connaissances verifier`) ;
- chargé au premier document ou à la première question seulement, puis gardé tant que le conteneur est éveillé : un client sans documents ne paie rien.

**La mémoire, à surveiller.** Mesuré sur linux/amd64 : environ 110 Mo pour l'agent seul, environ 550 Mo une fois le modèle chargé (sans la réserve d'onnxruntime, désactivée). Les conteneurs sont en `basic` (1 Gio) et le chart Helm limite à 1 Gi : ça tient pour un client, mais un agent chargé (pack immobilier, plusieurs rôles) avec une base de connaissances est à mesurer en production avant d'en ouvrir beaucoup ; `standard-1` (4 Gio, environ 27 $ par mois) est l'issue si ça ne tient pas. L'image passe de 672 Mo à 1,13 Go (onnxruntime, numpy, le modèle). Le modèle quantifié demande un processeur x86-64 avec AVX2 (Cloudflare, Exoscale et les serveurs courants l'ont).

**Les documents.** Texte (ou Markdown), PDF (avec du texte : un PDF scanné doit d'abord passer par une reconnaissance de caractères) ou page HTML ; 8 Mo au plus. Lus, découpés en passages d'environ 800 caractères aux fins de phrase (chacun reprend la fin du précédent : une réponse coupée en deux se retrouve), calculés, rangés dans la base du client (`megga_documents`, `megga_passages` avec le vecteur et le nom du modèle qui l'a calculé). Le texte d'origine n'est pas gardé, seulement ses passages. 200 documents et 20 000 passages au plus par client.

**La recherche** compare la question à tous les passages, en mémoire : une PME en a quelques milliers au plus, la comparaison prend quelques millisecondes. Ni pgvector ni rien de propre à Postgres : la même chose sur SQLite, comme le veut le plan. Seuls les passages au-dessus d'un seuil (0,3, mesuré sur le modèle int8 : une question hors sujet ne rend rien) partent au modèle, quatre au plus, avec leur titre.

**Les routes.**

| Route | Rôle | Effet |
|---|---|---|
| `GET /atelier/clients/{id}/connaissances` | tous | les documents de la base |
| `POST /atelier/clients/{id}/connaissances` | tous | `{titre, genre (texte, pdf, html), texte ou base64, source?}` : le document lu et rangé (`201`) ; `400` s'il est illisible, vide ou de trop |
| `DELETE /atelier/clients/{id}/connaissances/{n}` | tous | retire un document et ses passages |

Côté porte : `GET|POST /admin/clients/{id}/connaissances`, `DELETE /admin/clients/{id}/connaissances/{n}` (jeton `ADMIN_TOKEN`, 12 Mo au plus avec sa longueur), transmises au conteneur (`/interne/connaissances`). Hors Cloudflare, rien n'entre chez le client (`409`) : les documents s'ajoutent sur son serveur, `docker compose exec agent python -m noyau.connaissances ajouter conditions.pdf "Conditions de location"` (et `lister`, `retirer <n>`).

**Les tables** (additives, sans changer `SCHEMA_VERSION`) : `megga_documents`, `megga_passages` ; exportées et importées avec le reste du client (les vecteurs en base64).

**Ce qui reste.**
- L'essai de l'atelier n'a pas les documents du client (sa base d'essai est à part) : l'outil y répond qu'ils ne sont pas consultables ici.
- Un changement de modèle demandera de recalculer les passages (le nom du modèle est gardé avec chaque vecteur pour le savoir).
- Pas encore de lecture d'un site entier, d'un Drive ni d'un fichier Word : à venir avec les connecteurs (9.4).
