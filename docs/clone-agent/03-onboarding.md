# 03. L'onboarding : créer son clone en lui parlant

## Le but

En moins de 20 minutes, sans un seul formulaire à remplir, la personne :

1. a raconté qui elle est et ce qu'elle n'aime pas faire ;
2. a branché ses premiers comptes ;
3. a relu un portrait d'elle et l'a corrigé ;
4. a vu son clone **rendre un premier vrai service** (une boîte mail triée, trois réponses prêtes, un rendez-vous calé).

Tout le reste (ingestion complète, voix, avatar, autres comptes) continue ensuite, en fond, ou plus tard.

C'est l'écran qui décide du produit : la spec de la console pose déjà la règle « Un écran qui impose des étapes avant que l'agent ne réponde » comme un échec. Ici, le clone répond dès la première phrase.

## Qui mène l'entretien

**L'agent d'accueil** : un agent à part, avec ses propres consignes, dont le seul travail est de faire connaissance et d'écrire. Il ne fait rien dans les comptes. Il parle en texte ou en vocal, au choix de la personne.

Il a des outils d'écriture, pas de lecture libre :

| Outil | Ce qu'il écrit |
|---|---|
| `noter_fait` | un fait sur la personne (« vit à Lyon », « deux enfants, Léa 8 ans et Tom 5 ans »), avec sa source (« dit à l'onboarding ») |
| `noter_personne` | un proche ou un contact important, son lien, comment on lui parle |
| `noter_corvee` | une tâche que la personne n'aime pas, sa fréquence, le domaine, le service concerné |
| `noter_regle` | une règle qu'elle énonce (« jamais de rendez-vous le mercredi ») |
| `proposer_compte` | demande à l'écran d'afficher le bouton de branchement d'un compte (Gmail, Agenda...) |
| `proposer_mission` | une mission tirée d'une corvée, avec le niveau d'autonomie suggéré |
| `montrer_portrait` | affiche le portrait en cours, que la personne corrige |
| `passer_etape` | avance dans le parcours (l'écran suit) |

L'écran est une conversation, avec des éléments qui apparaissent quand l'agent les propose (boutons de branchement, cartes du portrait, curseurs) : c'est exactement ce que CopilotKit et AG-UI, déjà dans la console, savent faire (actions et composants rendus par l'agent).

## Le parcours

### 0. Le compte (1 minute)

- Courriel ou Google, Microsoft, Apple (Better Auth, déjà dans la console).
- Le pays, d'où vient la zone (Suisse, Europe, États-Unis) : dit clairement, avec ce que ça veut dire (« vos données restent en Suisse »).
- Majeur : une case, et un contrôle plus fort avant la voix et l'avatar.
- Les consentements, un par un, en mots simples : traiter ses données pour créer son clone ; lire les comptes qu'il branchera ; aucun usage pour entraîner des modèles. Aucun consentement groupé.

### 1. Faire connaissance (5 minutes)

L'agent d'accueil ouvre :

> « Bonjour ! Je vais devenir votre clone : je vais faire à votre place ce que vous n'aimez pas faire sur l'ordinateur. Pour ça, j'ai besoin de vous connaître un peu. Racontez moi une semaine normale : qu'est ce qui vous prend du temps et que vous aimeriez ne plus jamais faire ? »

Il suit la conversation, relance, et ne pose jamais plus d'une question à la fois. Ce qu'il cherche, dans l'ordre :

1. **Les corvées** (le cœur : c'est ce qui vend le produit dans la minute) ;
2. **Le contexte** : situation, travail, famille, lieu, langues ;
3. **Les gens** : qui compte, qui écrit souvent, à qui on dit tu ;
4. **Les règles** : ce qu'il ne faut jamais faire, les préférences fortes ;
5. **Le ton** : comment la personne écrit (« plutôt court », « toujours poli », « des emojis avec les amis »).

Tout ce qu'il note apparaît en direct, sur le côté, en petites cartes que la personne peut corriger ou supprimer d'un geste.

### 2. Brancher les comptes (3 minutes)

L'agent propose les comptes **à partir des corvées citées**, pas une liste de cinquante logos : « Vous avez parlé des mails et des rendez-vous : on branche votre Gmail et votre agenda ? »

- Le branchement passe par Composio (le lien de connexion du service, comme aujourd'hui), sauf que c'est le titulaire qui le déclenche lui-même, sans MEGGA.
- Chaque compte branché dit ce que le clone pourra y faire, domaine par domaine.
- Les sites sans API (banque, impôts, assureur) sont notés pour plus tard (C6) : « Je saurai bientôt le faire sur ce site ; je vous préviens dès que c'est prêt. »

### 3. Le premier service (3 minutes, pendant que l'ingestion démarre)

Dès que la boîte mail est branchée, le clone fait quelque chose d'utile **tout de suite**, sur les 50 derniers mails seulement :

- « Vous avez 12 mails qui attendent une réponse. J'ai préparé les 3 plus simples, voulez vous les voir ? »
- Ou : « Vous avez 31 newsletters jamais ouvertes. Je vous désabonne de celles là ? »

Les brouillons sont **proposés**, jamais envoyés à ce stade, quel que soit le réglage futur.

En parallèle, l'ingestion de l'historique commence (voir plus bas) : la barre de progression reste visible, avec ce qu'elle a déjà appris (« 420 mails lus, 37 contacts reconnus »).

### 4. Le portrait (3 minutes)

> « Voici ce que j'ai compris de vous. Corrigez moi. »

Le portrait est une page lisible, en sections : qui vous êtes, vos proches, comment vous écrivez, vos règles, ce que je vais faire pour vous. Chaque ligne montre d'où elle vient (« vous me l'avez dit », « lu dans 14 de vos mails ») et sa certitude. La personne corrige en parlant (« Non, Marc c'est mon associé, pas mon frère ») : l'agent d'accueil met à jour.

Un fait jamais confirmé et tiré d'une seule source reste marqué « à confirmer » et n'est pas utilisé pour agir.

### 5. Le jeu « Qui a écrit ça ? » (2 minutes, facultatif mais recommandé)

Le clone montre deux réponses à un vrai mail reçu : celle que la personne a vraiment envoyée, et celle qu'il aurait écrite. Elle dit laquelle est la sienne, et ce qui cloche dans l'autre (« trop long », « je ne dis jamais Cordialement »). Cinq tours suffisent.

Ce jeu fait trois choses : il mesure la ressemblance dès le départ, il apprend vite au clone ce qui ne va pas, et il montre l'effet waouh quand la personne n'arrive plus à distinguer les deux. C'est aussi un très bon moment à partager.

### 6. Régler l'autonomie (2 minutes)

Pour chaque domaine branché, un curseur à trois positions, expliqué avec un exemple concret :

| Position | Ce que fait le clone | Exemple pour les mails |
|---|---|---|
| **Observer** | lit et résume, ne prépare rien | « Vous avez 3 mails importants » |
| **Proposer** | prépare tout, attend votre oui | « Voici la réponse à Julie, je l'envoie ? » |
| **Agir et rendre compte** | fait, et vous le dit dans le point du jour | « J'ai répondu à Julie pour confirmer jeudi » |

Le réglage est **celui de la personne** (décision de Thomas). L'agent d'accueil suggère un départ prudent (« proposer » pour tout ce qui part vers un tiers), explique pourquoi, et rappelle qu'on peut changer d'avis à tout moment, ou dire plus tard en langage naturel « à partir de maintenant, réponds seul aux demandes de rendez-vous ».

### 7. Les rendez-vous suivants

L'onboarding ne s'arrête pas : il devient une relation.

- Le point du jour pose une ou deux questions pour mieux connaître la personne.
- Chaque nouveau compte branché relance une petite ingestion et quelques questions.
- Après une semaine : « Vous avez validé 40 de mes réponses sans les changer. Voulez vous que je réponde seul à ce genre de mails ? »
- La voix (C7) et l'avatar (C9) se proposent plus tard, chacun avec son propre parcours de consentement.

## Ce que l'onboarding produit

| Sortie | Où | Usage |
|---|---|---|
| La configuration du clone, version 1 | atelier (comme tout agent : brouillon, essai, mise en service) | comment le clone travaille |
| Les faits, personnes, règles et préférences | modèle de soi | qui est la personne |
| Les missions | modèle de soi (table des missions) | ce que le clone fait, quand |
| Le profil de style, première version | modèle de soi | comment il écrit |
| Les comptes branchés | Composio (utilisateur = titulaire) | ses mains |
| La politique d'autonomie | configuration (`clone.domaines`) | ce qu'il fait seul |
| Les mesures de départ | relevé chiffré, sans contenu | ressemblance de départ, temps jusqu'au premier service |

La configuration naît par l'atelier comme celle d'un agent d'entreprise : l'agent d'accueil appelle les mêmes routes (créer, valider, essayer, activer), avec le rôle du titulaire. Il faut donc ouvrir à un titulaire la création de son propre clone (aujourd'hui `POST /clients` est réservé à MEGGA) et la mise en service sans essai forcé, deux manques déjà notés dans la spec de la console.

## L'ingestion de l'historique

Le gros de la ressemblance vient de ce que la personne a **déjà écrit et fait**, pas de ce qu'elle dit d'elle même.

| Source | Ce qu'on en tire | Volume par défaut |
|---|---|---|
| Mails envoyés | style par destinataire et par contexte, formules, longueur, langue ; contacts et liens ; décisions types (accepter, refuser, relancer) | 12 derniers mois, 2 000 mails au plus |
| Mails reçus | qui écrit, sur quoi, ce qui attend réponse ; comptes et services utilisés (factures, confirmations) | 3 derniers mois |
| Agenda | routines, horaires, durées, préférences de créneaux, gens rencontrés | 6 mois passés, tout le futur |
| Documents (Drive, Dropbox) | sur demande seulement, dossier par dossier | aucun par défaut |
| Messages (WhatsApp exporté, autres) | style informel | sur demande seulement |

**Les règles de l'ingestion** :

- Chaque source est **choisie** par la personne, avec sa période ; elle peut l'arrêter et tout effacer à tout moment.
- Les textes bruts sont gardés **chiffrés**, le temps de l'extraction, puis seulement ce que la personne a choisi de garder (par défaut : les extraits qui servent d'exemples de style, et les liens vers les originaux, qui restent chez le fournisseur).
- Les données des **tiers** (ce que les autres ont écrit) ne servent qu'au service du titulaire, jamais ailleurs ; voir [07-securite-conformite.md](07-securite-conformite.md).
- Aucun mot de passe, code ni numéro de carte n'est retenu (la règle de `noyau/memoire.py`, étendue).
- L'extraction tourne avec un petit modèle, par lots, avec un coût plafonné par titulaire et visible par MEGGA dans le relevé.

## Les cas difficiles

| Cas | Réponse |
|---|---|
| La personne ne veut brancher aucun compte | le clone sert de mémoire et de secrétaire par la conversation ; il explique ce qu'il pourrait faire de plus, sans insister |
| Elle parle d'une autre personne en détail (santé d'un proche...) | l'agent note seulement ce qui sert une corvée, et marque la donnée comme sensible |
| Elle donne un mot de passe dans la conversation | jamais retenu ; l'agent explique que les comptes se branchent par le bouton, et le masquage déjà en place le retire du fil |
| Elle a plusieurs vies (pro et perso, deux langues) | le style et les règles se rangent par contexte ; le portrait les montre séparés |
| Elle veut aller très vite | tout est facultatif sauf le compte et un premier compte branché ; le reste revient dans le point du jour |
| Elle abandonne au milieu | tout ce qui est noté reste, le clone reprend là où elle s'est arrêtée, par un message (si elle l'a permis) |

## Ce qu'il faut construire (résumé, détaillé dans [08-lots.md](08-lots.md))

- L'agent d'accueil, ses consignes et ses outils d'écriture (C2).
- Les écrans conversationnels de l'onboarding dans la console, avec les composants rendus par l'agent (C2).
- L'inscription libre et la mise en service par le titulaire dans l'atelier (C1).
- L'ingestion par lots, avec reprise et progression (C3).
- Le portrait, lisible et corrigeable (C2 pour la v1, enrichi en C3 et C5).
- Le jeu « Qui a écrit ça ? » (C3).
