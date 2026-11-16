# Lot 9 : les fonctionnalités du lancement

D'après l'étude de marché du 16.11.2026 (le catalogue des fonctionnalités indispensables), en commençant par celles qui ne demandent aucun compte chez un tiers. Une branche et une PR par sous-lot ; rien n'est déployé sans « Fusionne et déploie » de Julien.

| Sous-lot | Contenu |
|---|---|
| **9.1 Approbations et journal d'audit** (cette PR) | une règle par outil (accord d'un gestionnaire, ou interdit), le journal de chaque appel d'outil, la décision sur WhatsApp ou dans la console |
| 9.2 Base de connaissances | les documents du client, une recherche par le sens calculée dans l'image (aucune donnée ne sort), des réponses qui citent leur source |
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
