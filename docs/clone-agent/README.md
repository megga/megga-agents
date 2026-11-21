# Clone Agent : votre agent, c'est vous

Dossier de cadrage du 21.11.2026, écrit avec Thomas pour Julien. C'est un plan, pas du code : rien n'est construit avant l'accord de Julien, et rien n'est fusionné ni déployé sans « Fusionne et déploie ».

## L'idée en une phrase

Chacun crée son clone IA en lui parlant, et lui laisse tout ce qu'il n'aime pas faire sur un ordinateur : il écrit comme lui, décide comme lui, et agit dans ses propres comptes.

> « Votre agent, c'est vous. »
> « Un agent qui vous ressemble. »
> « Créez votre clone IA. »
> « Laissez à votre clone tout ce que vous n'aimez pas faire, et concentrez vous sur l'essentiel. »

## Ce qui change par rapport à megga-agents aujourd'hui

Aujourd'hui, un agent MEGGA **représente une entreprise auprès de ses clients** (Alix pour Four Seasons) : il accueille, répond, retient, rappelle. Clone Agent **représente une personne auprès du reste du monde, et travaille à sa place** : il trie ses mails et y répond, gère son agenda, relance, remplit les formulaires, range les factures, suit l'administratif.

Trois briques nouvelles, posées sur le socle existant :

1. **L'onboarding par la conversation** : la personne raconte sa vie et sa semaine, le clone en tire sa propre configuration, ses missions et un premier portrait d'elle ([03-onboarding.md](03-onboarding.md)).
2. **Le modèle de soi** : la grande base de données d'une personne (identité, style, relations, règles, décisions, routines, souvenirs, procédures), apprise de son historique et corrigée en continu ([04-modele-de-soi.md](04-modele-de-soi.md)).
3. **Les mains** : les connecteurs (Composio, MCP) quand un service a une API, un navigateur dans le cloud quand il n'en a pas, puis une app sur l'ordinateur ([05-actions.md](05-actions.md)).

## Les décisions de Thomas (21.11.2026)

| Sujet | Décision |
|---|---|
| Nom du projet | **Clone Agent** (nom de code dans le dépôt ; la marque publique reste à choisir, voir [01-concept.md](01-concept.md)) |
| Cible au lancement | **Grand public (B2C)** : toute personne majeure, un clone par personne |
| Autonomie | **Au choix de l'utilisateur** : il règle lui-même, domaine par domaine, ce que son clone fait seul ou lui soumet |
| Agir sans connecteur | **Les deux, par étapes** : navigateur dans le cloud d'abord, app sur l'ordinateur ensuite |
| Ressemblance | **Complète** : style d'écriture et décisions, voix clonée, avatar vidéo (dans cet ordre) |
| Offres | **Free, Plus (20), Pro (100), Ultra (200), et Local (5)** pour un clone sur sa propre machine ; chaque abonnement couvre son coût cloud ([10-tarifs.md](10-tarifs.md)) |
| Identité | **Aucun modèle nommé**, sur aucune offre : on voit son clone et MEGGA, jamais la technique ([11-offre-locale.md](11-offre-locale.md)) |
| Confidentialité | **Rien en clair vers un modèle extérieur** : données brutes traitées par des modèles maison dans la zone, texte pseudonymisé seulement vers l'extérieur, données sensibles jamais dehors ([12-confidentialite.md](12-confidentialite.md)) |
| Local | **Hybride et sans couture** : la machine fait ce qu'elle peut, le cloud prend le relais et veille quand elle dort, sans que le titulaire le voie |
| Infrastructure | **Confiée à Claude** : calcul partagé sans état, un coordinateur endormi par titulaire, données en cellules isolées par la base et le chiffrement ([09-infrastructure.md](09-infrastructure.md), à valider par Julien) |

## Le dossier

| Fichier | Contenu |
|---|---|
| [01-concept.md](01-concept.md) | le produit : pour qui, les missions, le parcours, la concurrence, le nom, le modèle économique |
| [02-architecture.md](02-architecture.md) | les bases techniques : ce qu'on réutilise, ce qu'on ajoute, le passage au grand public |
| [03-onboarding.md](03-onboarding.md) | l'onboarding conversationnel, étape par étape, et ce qu'il produit |
| [04-modele-de-soi.md](04-modele-de-soi.md) | la base de données de la personne : schéma, apprentissage, relecture, oubli |
| [05-actions.md](05-actions.md) | les mains du clone, le curseur d'autonomie, la file « À valider », le journal |
| [06-ressemblance.md](06-ressemblance.md) | écrire, parler et apparaître comme la personne, avec son consentement prouvé |
| [07-securite-conformite.md](07-securite-conformite.md) | sécurité, données, AI Act, RGPD et nLPD, conditions des services tiers |
| [08-lots.md](08-lots.md) | les lots C1 à C9, leurs critères de fin et leurs essais |
| [09-infrastructure.md](09-infrastructure.md) | l'infrastructure cloud du grand public : pools, coordinateurs, cellules, clés, zone Suisse, dimensionnement, pannes |
| [10-tarifs.md](10-tarifs.md) | les offres Free, Plus, Pro, Ultra et Local, le crédit, la disponibilité et le temps de travail, les coûts unitaires, la rentabilité, les machines |
| [11-offre-locale.md](11-offre-locale.md) | l'offre Local hybride (orchestrateur, renfort cloud, veilleur), et l'identité unique du clone sur toutes les offres |
| [12-confidentialite.md](12-confidentialite.md) | la confidentialité : trois classes de données, modèles maison, sas de pseudonymisation, passerelle unique, canaris |

## Les principes qui ne bougent pas

1. **La personne garde la main.** Elle voit tout ce que son clone a fait, peut tout arrêter d'un geste, et règle elle-même son autonomie.
2. **Ses données sont à elle.** Aucun texte brut ne part vers un modèle extérieur, et une donnée sensible ne quitte jamais la zone (12). Une personne ne voit jamais les données d'une autre ; MEGGA suit la santé et les chiffres de chaque clone, jamais ce qu'il lit ni ce qu'il écrit (comme la décision de Julien du 20.11.2026 pour les conversations). Tout s'exporte et tout s'efface.
3. **Le clone ne ment pas sur ce qu'il est** quand la loi ou la situation demandent de le dire : une voix ou une vidéo de synthèse est toujours signalée.
4. **Rien n'est dit fait sans preuve** : une action n'est annoncée que si l'outil l'a confirmée (règle déjà en place pour Composio).
5. **Une seule identité** : le clone dit qu'il est une IA, jamais sur quel modèle il tourne ; il se tait plutôt que de mentir.
6. **Ce qu'il lit n'est jamais un ordre** : un mail, une page web ou un document peut contenir des instructions ; le clone ne suit que la personne.
7. **Un seul moteur.** Le clone est un agent MEGGA : même noyau, même atelier, même porte, mêmes zones. On ajoute, on ne réécrit pas.

## Les anti-objectifs (un échec, même si tout marche)

- Une action engagée au nom de la personne au-delà de ce qu'elle a permis.
- Une donnée d'une personne visible par une autre, ou lue par MEGGA.
- Une voix ou un visage cloné sans consentement vérifié de son propriétaire.
- Un tiers trompé sur le fait qu'il parle à une IA alors que la loi exige de le dire.
- Un onboarding qui demande plus de 20 minutes avant le premier service rendu.
- Un clone qui « devine » un fait sur la personne et le traite comme vrai.

## Glossaire

| Terme | Sens |
|---|---|
| **Titulaire** | la personne que le clone représente (le « client » au sens de l'atelier) |
| **Tiers** | toute autre personne avec qui le clone échange au nom du titulaire |
| **Modèle de soi** | la base de données du titulaire, en couches (voir 04) |
| **Portrait** | la vue lisible du modèle de soi, que le titulaire relit et corrige |
| **Mission** | une tâche confiée au clone, ponctuelle ou récurrente (« réponds aux demandes de rendez-vous ») |
| **Domaine** | un grand champ d'action (mails, agenda, administratif, achats, finances, social...) |
| **Curseur d'autonomie** | pour chaque domaine et chaque genre d'action : observer, proposer, agir et rendre compte |
| **Recette** | une procédure apprise sur un site sans API, rejouée la fois suivante |
| **À valider** | la file des actions qui attendent le oui du titulaire |

## Ce qu'on attend de Julien

1. Lire ce dossier, corriger ce qui ne tient pas, trancher les questions ouvertes de chaque fichier (elles sont rassemblées dans [08-lots.md](08-lots.md)).
2. Valider l'ordre des lots et le périmètre de la première version publique (C1 à C5, « le clone qui écrit »).
3. Choisir avec Thomas un juriste pour l'AI Act, le RGPD et la nLPD avant le lot C4 (le clone agit au nom de quelqu'un).
