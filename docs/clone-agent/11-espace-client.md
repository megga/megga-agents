# 11. L'espace client, recentré

Écrit le 21.11.2026, à la demande de Julien, après [10-console.md](10-console.md). Ce fichier dit ce que le cadrage change pour l'espace où un client construit son agent. C'est une proposition : rien n'est construit avant l'accord de Julien.

## Où en est l'espace client

- **Dans le code** (`console/`, lot 8.1) : la connexion, le rail, le fil de conversation, et le Studio, qui crée un agent en deux gestes (prénom et métier, puis couleur et yeux). Next.js, Better Auth, CopilotKit et AG-UI sont en place.
- **En ligne** : il n'est pas ouvert. Sans serveur d'agents branché, console.megga.ai mène à la console de MEGGA, et un compte ne se crée que sur invitation.
- **Dans le plan** (`docs/plan.md`, lots 5 et 8) : la suite prévue était un assistant pas à pas, une question par écran (métier, prénom, voix et ton, ce que l'agent sait faire), un essai dans un faux WhatsApp, puis « Mettre en service ». Aucun de ces écrans n'est construit, et leur plan n'a pas encore été rendu.

## Ce que le cadrage change

On ne remplit plus des écrans : **on parle, et l'agent d'accueil écrit la configuration** ([03-onboarding.md](03-onboarding.md)). La conception de la console le disait déjà (un écran qui impose des étapes avant que l'agent ne réponde est un échec) : c'est l'assistant pas à pas du plan qui s'en écartait.

| Étape | Le pas à pas prévu | Recentré |
|---|---|---|
| Commencer | choisir un métier dans une liste | raconter : l'agent d'accueil écoute, relance, une question à la fois |
| Le métier, les règles, le ton | un écran chacun | notés pendant la conversation, en cartes sur le côté, corrigées d'un geste ou en parlant |
| Le prénom, la couleur, les yeux | le Studio | le Studio reste : c'est le visage de l'agent |
| La voix | un écran pour l'écouter | une carte dans le fil, proposée par l'agent, à écouter là |
| Les outils | une liste à cocher | les comptes proposés d'après ce que la personne a dit, avec un bouton de branchement dans le fil |
| L'essai | un faux WhatsApp, étape obligée | le premier vrai service rendu sert d'essai ; on parle à l'agent dès la première phrase |
| La mise en service | un bouton, après l'essai | sans essai forcé ; l'autonomie se règle domaine par domaine |
| Ensuite | un tableau de bord : quelques chiffres, « Modifier », « Revenir à la version d'avant » | « À valider », le point du jour, le journal, le portrait |

Le but chiffré du cadrage devient celui de l'espace client : **le premier service rendu en moins de 20 minutes**, sans un seul formulaire.

## Les écrans de l'app

| Écran | Ce qu'il montre | Aujourd'hui | Lot |
|---|---|---|---|
| La conversation | le fil, et ce que l'agent y fait apparaître : cartes, boutons de branchement, curseurs | le fil existe, sans carte | C2 |
| Le portrait | ce que l'agent a compris, par section, avec la source et la certitude de chaque ligne | rien | C2 |
| À valider | chaque action en attente : ce qui l'a provoquée, l'aperçu exact, oui, modifier ou non | dans le rail de la maquette du lot 8.1, pas construit | C4 |
| Le journal | ce qui a été fait, avec le résultat confirmé et « annuler » quand c'est possible | rien | C4 |
| L'autonomie | par domaine et par genre : observer, proposer, agir et rendre compte | rien | C2, C4 |
| Les comptes branchés | ce qui est branché, ce que l'agent peut y faire, débrancher | rien | C2 |
| Le point du jour | son heure, en texte ou en vocal | rien | C4 |
| Pause | tout repasse en « observer », tout de suite | rien | C4 |
| Mes données | exporter, oublier une source, tout effacer avec un reçu | rien | C1 |
| Mon compte | double authentification, appareils connectés | le compte existe, sans double authentification | C1 |
| Ma voix, mon avatar | l'enregistrement en direct et le consentement | rien | C7, C9 |

## Ce qu'on garde

La base ne change pas : Next.js, Better Auth, CopilotKit et AG-UI, les composants, les jetons de couleur, le rail, le fil, la mascotte, le Studio. Les règles de la conception du lot 8.1 tiennent toujours : aucun bouton qui ne fait rien, jamais deux fois la même information à l'écran, tous les textes relus par Julien.

## Ce qui manque avant le premier écran

Les six manques notés dans la conception du lot 8.1 tiennent toujours. Le cadrage en fait des conditions, et en ajoute deux.

| Manque | Où | Lot |
|---|---|---|
| L'inscription libre : en ligne, un compte ne se crée que sur invitation | console | C1 |
| La création par le client lui-même : `POST /atelier/clients` est réservé à MEGGA | atelier | C1 |
| Plusieurs agents par compte (l'agent d'une entreprise et le clone de son patron) : l'atelier compte un agent par client | atelier | C1 |
| La mise en service sans essai forcé | atelier | C1 |
| Le lien entre un compte de la console et un client de l'atelier | console et atelier | C1 |
| Une entrée au fil de l'eau pour un agent en service (PR #35, ouverte) | noyau | C2 |
| Relire un fil après rechargement | console | C2 |
| L'agent d'accueil, ses outils d'écriture, les cartes qu'il fait apparaître | `packs/clone/accueil/`, console | C2 |

## Et les entreprises ?

L'espace client a deux publics : l'entreprise qui veut un agent pour ses clients (WhatsApp, voix), et la personne qui veut son clone. Le cadrage ne parle que de la seconde.

**Proposition** : la même entrée pour les deux. L'agent d'accueil demande d'abord pour qui il travaillera. Pour une entreprise, il note l'activité, les horaires, les services, le ton, puis propose un modèle de l'atelier (le généraliste, l'immobilier ou l'un des 283 du catalogue), une voix à écouter et les outils. Tout ce qu'il a noté reste visible dans une page « Réglages », modifiable d'un geste : rien n'est caché derrière la conversation.

C'est un changement par rapport à l'exigence de Julien des 15 et 20.11.2026 (un assistant pas à pas). Il ne se fait pas sans son accord.

## L'ordre proposé

1. **Avec C1** : l'inscription libre, le compte et sa double authentification, « Mes données ».
2. **Avec C2** : la conversation avec ses cartes, le portrait, les comptes branchés, l'autonomie.
3. **Avec C4** : « À valider », le journal, le point du jour, la pause.
4. **Avec C7 et C9** : la voix, puis l'avatar.

Avant C1, un seul travail utile : le plan écran par écran, à refaire sur cette base plutôt que sur le pas à pas.

## À trancher par Julien

1. **Les entreprises aussi par la conversation**, comme proposé, ou le pas à pas reste pour elles ?
2. **Un seul espace pour les deux publics**, ou deux entrées séparées ?
