# Lot 8 : l'interface (la console), et le moteur de l'équipe (lot 11)

Plan du 17.11.2026, relu par Julien le même jour : la direction est validée, ses corrections sont intégrées (voir « Ce que Julien a changé »). D'après la maquette de la plateforme d'agents (https://claude.ai/artifact/Pwpu7ySMquoSoqAbqt3qhU), lue en entier (page, styles, logique) et rendue sur bureau, sur mobile et en thème sombre. Thomas ne l'a pas modifiée : elle reste la référence visuelle, à sa version 61 du 17.11.2026. Rien n'est déployé sans « Fusionne et déploie » de Julien.

**Décidé par Thomas le 17.11.2026 : le lancement vise l'équipe d'agents internes**, celle que dessine la maquette. L'agent qui accueille les clients sur WhatsApp devient un membre de cette équipe.

Ce document est le plan d'ensemble. Chaque sous-lot aura sa conception et son plan de tâches (`docs/superpowers/specs/`, `docs/superpowers/plans/`) au moment de l'ouvrir, comme le lot 10.

## Ce que Julien a changé (17.11.2026)

1. **Un agent est en service dès sa création.** Ni brouillon ni étapes imposées : les documents, WhatsApp et les connecteurs se branchent au fil de la conversation, selon ce que le client veut faire. Les versions restent pour modifier un agent déjà en service (décision 10, principes, 8.1, 8.2, 8.8, 11.6).
2. **Pas d'en-tête dans la conversation.** On sait à qui l'on parle par la barre, où l'agent ouvert est marqué, et par la zone de saisie (« Écrivez à Alix »). L'état d'un agent se lit dans la barre (décision 11, 8.2).
3. **La mascotte est la tête seule** : les yeux et le GG, sans corps ni tenue. La création règle sa couleur et ses yeux (décision 8, 8.1).
4. **La connexion passe par Better Auth**, retenu le 16.11.2026 (décision 6, 8.1).
5. **La pile** : Vite, React, TypeScript et Tailwind, avec shadcn pour les composants. CopilotKit s'essaie dans le 8.2 avant d'être retenu (décision 5).
6. **Les métiers du lancement se choisissent avec Julien** (décision 3, 11.3). En attendant, la maquette montre les huit métiers d'accueil du lot 10.
7. **Ouvrir un agent au public passe par l'essai.** Brancher un numéro WhatsApp à un agent, qui répond alors à des inconnus, passe par l'essai, comme aujourd'hui (décision 12).

Restent à trancher par Julien : la couleur d'accent (décision 7) et le micro (décision 9).

## En une phrase

La maquette est la cible. Le moteur, lui, fait tourner aujourd'hui un agent par entreprise, qui accueille ses clients sur WhatsApp : pour une équipe d'agents avec qui le patron travaille, il manque sept morceaux de moteur, dont deux avant le premier écran utile (l'équipe, l'entrée console). Ce plan les met en tête (lot 11), et construit l'interface à mesure qu'ils arrivent.

## Ce que ce choix change

- **Le moteur passe d'abord.** L'écran central de la maquette (parler à un agent qui agit, avec votre accord) n'a aucune route aujourd'hui.
- **Ce qui est déjà fait sert de fondation**, pas de produit fini : les accords et le journal d'audit (lot 9.1), la base de connaissances (9.2), les connecteurs MCP (9.4), les versions, l'essai et la mise en service (lot 5), le banc d'essai (9.6), les modèles par métier en fichiers (lot 10).
- **L'accueil des clients reste**, comme un métier parmi d'autres : un agent d'équipe qui a, en plus, un numéro WhatsApp. Four Seasons Properties continue de tourner sans changement.
- **Trois risques à garder en vue**, sans rouvrir la décision :
  - un agent interne sans outil branché ne vaut pas mieux qu'une conversation avec un modèle. Les connecteurs (agenda, courriel, fichiers) deviennent indispensables, et la décision du 16.11.2026 (« d'abord sans compte externe ») est à rouvrir ;
  - plusieurs agents qui agissent en même temps restent fragiles (étude de marché, 4.4). Règle retenue : un seul agent écrit et agit à la fois ;
  - les gestionnaires ne sont pas arrêtés par le plafond du jour (`noyau/garde.py`). Une équipe que le patron sollicite toute la journée demande un plafond par compte.

## La maquette face au moteur

| Dans la maquette | Dans le moteur aujourd'hui | Ce qu'il faut |
|---|---|---|
| Discuter avec un agent (« Peux-tu relancer… ») | Rien dans l'atelier. Le patron parle à son agent sur WhatsApp (rôle gestionnaire). L'essai parle à un brouillon, dans un bac à sable ; l'entrée par API ne donne que le rôle visiteur | L'entrée console (11.2) |
| Quinze agents, quatre groupes, épinglés | Un client = un agent (`Config.nom_agent`). Mais un conteneur construit déjà un agent par rôle, sur la même base (`noyau/app.py`) | L'équipe (11.1) |
| Huit métiers d'accueil, ceux du lot 10 (depuis le 17.11.2026) | Huit modèles, tous d'accueil (lot 10) ; deux sur `main` | Le catalogue d'équipe (11.3) |
| « Planifié » (tâches à heure fixe) | Seulement les rappels demandés par une personne et le mot du matin (`bonjour`) | Les tâches planifiées (11.4) |
| Le trombone (donner un fichier à un agent) | Aucune route ne reçoit une pièce depuis la console | Les pièces jointes (11.5) |
| « Son agenda est déconnecté » | Un client MCP dans le noyau ; aucun connecteur prêt à l'emploi | Les connecteurs (11.6) |
| Conversations à plusieurs agents, « @ » | Rien | Travailler à plusieurs (11.7), en dernier |
| « À valider » | Fait : accords (9.1), `GET|POST /clients/{id}/approbations` | L'écran, complété (8.3) |
| « Bibliothèque » | Fait : connaissances (9.2), texte, PDF, HTML, par client | L'écran, complété (8.4), et l'accès par agent |
| « Aujourd'hui » (quatre cartes) | Fait autrement : `valeur`, `suivi`, `alertes` | L'écran, sur les vrais chiffres (8.6) |
| Créer un agent : prénom, métier, couleur, yeux | Fait : modèle par métier, essai, mise en service. Aucun réglage d'apparence | L'écran (8.1) ; l'apparence gardée par l'atelier ; l'agent en service dès sa création |
| Renommer, mettre en pause, archiver, en un clic | Renommer = une nouvelle version à mettre en service. Ni pause ni archivage | 11.1, 8.8 |
| Menu : Activité, Réglages, Aide, Se déconnecter | Fait pour l'activité (`audit`) et les réglages (versions). Aucune connexion par compte | 8.1, 8.3, 8.8 |

Ce que le moteur fait déjà et que la maquette ne montre pas (pour les agents qui ont un numéro WhatsApp) : les conversations des clients, le transfert vers un humain et la reprise en main (9.3), les demandes notées (9.4), les droits d'une personne (9.5), les clés des logiciels, la vue MEGGA sur tous les clients.

## Les constats sur la maquette

### Ce qui est juste

- Le modèle d'ensemble, désormais : des agents qui ont un prénom et un métier, rangés par groupe, à qui l'on écrit.
- Le ton. « Vos agents attendent votre accord avant d'agir. », « Ce que vos agents ont fait depuis hier soir. » : des phrases qu'un patron de PME comprend sans formation.
- La carte d'accord dans la conversation : qui, quoi, un bouton. C'est l'objet du lot 9.1.
- « Alix a vérifié 3 sources », replié par défaut : la bonne façon de montrer le travail sans noyer.
- Le premier message d'un nouvel agent (« Essayez-moi… ») : il invite à l'essayer tout de suite.
- La mascotte, vivante et sobre ; les deux thèmes ; la zone de saisie.

### Ce qui manque pour qu'elle soit opérationnelle

1. **La connexion.** Ni compte, ni rôles, ni invitation d'un collaborateur.
2. **Le premier lancement.** Aucun état vide : que voit une entreprise sans agent ?
3. **Les versions.** Un agent est en service dès sa création (choix de Julien). Mais modifier un agent en service ne passe ni par un brouillon, ni par des versions, et rien ne permet de revenir en arrière.
4. **L'état d'un agent.** La conversation n'a pas d'en-tête (choix de Julien) : l'agent ouvert est marqué dans la barre, et c'est là que doit se lire son état (en service, en pause, une alerte).
5. **Refuser.** La carte d'accord propose « Envoyer » et « Modifier », la liste « Voir » et « Valider ». Jamais « Refuser ». Le contenu exact du message n'est pas montré, ni le délai (une demande expire en 48 heures). « Valider » dans la liste envoie quatre messages WhatsApp en un clic, sans les avoir lus.
6. **Ce qu'un agent sait faire.** La création donne un prénom, un métier et un visage. Rien sur ses outils, ses connexions, les documents qu'il consulte, ni sur ce qui demande un accord. Choix de Julien : ne rien imposer à la création ; l'agent propose de brancher ce qu'il lui faut au fil de la conversation, et ses réglages le montrent (8.8).
7. **Les alertes.** « Son agenda est déconnecté » s'affiche, sans rien pour y remédier.
8. **Ajouter un document, créer une tâche.** La bibliothèque et le planifié se lisent, ils ne se remplissent pas.
9. **Les réglages et l'activité.** Les deux entrées du menu ne mènent nulle part.
10. **Les agents d'accueil.** Lire ce qu'Alix a répondu à Claire Martin, reprendre une conversation, voir les demandes : absent.
11. **Les états.** Ni chargement, ni erreur, ni vide, ni hors ligne. L'atelier rend des erreurs champ par champ, prêtes à montrer : aucun écran ne les montre.
12. **Le mobile.** Voir plus bas : inutilisable.
13. **La vue MEGGA.** Absente.
14. **La langue.** Français seulement, pour un marché suisse à quatre langues.

### Ce qui reste superflu

- **Le panneau « Réglages d'aperçu »** : un outil de maquette, qui recouvre le premier message.
- **Trois styles d'épinglés** (tuiles, bandeau, cartes) : en garder un.
- **« Tous mes agents »** : une seconde liste des mêmes agents. L'état d'un agent (en service, en pause, une alerte) doit se lire dans la barre ; la grille peut partir.
- **Le micro** : aucune route ne reçoit une dictée depuis la console. À trancher par Julien (décision 9) : le retirer en attendant, ou lui faire une route tôt.
- **Deux thèmes sombres en trop** (`bleutee`, `noir`), et des styles qui ne servent plus (`.barre`, `.titulaire`, `.cherche`, `.nouvel`, `.epingle`, `.demo-style`, `#replier`).

Les groupes, les épinglés, la recherche ⌘ K, le trombone et la mention « @ » ne sont plus superflus avec une équipe de quinze agents : ils attendent leur moteur.

### Ce qui est cassé

Vérifié sur le rendu, pas seulement à la lecture.

- **Mobile (390 px)** : la barre latérale garde 304 px, il reste 86 px pour la conversation. La règle `.rail { width: 304px }`, écrite après la règle du mobile, l'emporte.
- **Les non-lus sont masqués** dans la barre (`.rail .nl { display: none }`), comme l'heure du dernier message. Seul signal : le prénom en rouge, donc la couleur seule. Les pastilles ont été retirées à la demande de Julien : trouver un signal qui ne tienne pas qu'à la couleur, sans pastille.
- **« À valider 4 »** est écrit en gris, comme « 48 » documents. Le chiffre qui demande une action ne se distingue pas.
- **Une mascotte passe par-dessus la carte du compte** en bas de la barre (`z-index` des vignettes, pied de barre sans `z-index`).
- **Des comptes qui se contredisent** : « Ventes, 2 agents » dans la barre et « Ventes (4) » dans la grille ; « Bibliothèque 48 » pour cinq lignes.
- **Tout passe par le clic droit** (épingler, renommer, mettre en pause, archiver) : hors de portée au doigt et au clavier. « Archiver » supprime sans confirmation.
- **Contrastes** (seuil : 4,5) : texte discret `#a2a2b8` sur blanc, 2,5 ; texte d'alerte `#e8930c`, 2,4 ; blanc sur le bouton rouge, 4,3 en clair et 3,4 en sombre.
- **Le titre de la page** est « Plaquette MEGGA 2 ».

## Les décisions

| # | Question | État |
|---|---|---|
| 1 | Équipe d'agents internes, ou agent d'accueil seul ? | **Décidé : l'équipe** (Thomas, 17.11.2026) |
| 2 | Une entreprise, un conteneur et plusieurs agents, ou un conteneur par agent ? | Recommandé : un conteneur par entreprise. Quinze conteneurs et quinze bases par PME coûteraient trop, et les agents ne partageraient ni documents ni mémoire. À concevoir avec Julien |
| 3 | Quels métiers au lancement ? | Recommandé : une douzaine, pas quarante. Un métier n'entre au catalogue que si ses outils sont branchés et si son banc d'essai passe. Les premiers : ceux qui travaillent sur des textes et des documents. **La liste se choisit avec Julien** |
| 4 | Les connecteurs : lequel d'abord ? | Google Workspace ou Microsoft 365, selon les premiers clients. Rouvre la décision du 16.11.2026 |
| 5 | La pile de l'interface | **Décidé (Julien, 17.11.2026)** : Vite, React, TypeScript, Tailwind, comme le site (`~/dev/megga`), servie par un Worker qui tient la session ; shadcn pour les composants. CopilotKit (AG-UI, qu'Agno sait déjà servir) s'essaie dans le 8.2 avant d'être retenu |
| 6 | La connexion | **Décidé (Julien, 16.11.2026) : Better Auth.** Adresse et mot de passe, sur invitation de MEGGA ; il fournit aussi Google et Microsoft, le mot de passe oublié et la double authentification. Un code reçu sur WhatsApp ensuite |
| 7 | La couleur d'accent | La maquette est en rouge `#e03e2a`, le logo en orange `#F64900`. À trancher par Julien, puis à foncer jusqu'à 4,5 de contraste |
| 8 | Où ranger l'apparence de la mascotte | Dans la base de l'atelier, pas dans `Config` : le noyau n'en a pas besoin. L'apparence, c'est la couleur et les yeux : la mascotte est la tête seule, sans tenue (Julien, 17.11.2026) |
| 9 | Le micro dans la console | À trancher par Julien : le retirer en attendant sa route, ou lui en faire une tôt (le mode vocal de la maquette est très travaillé) |
| 10 | La création d'un agent | **Décidé (Julien, 17.11.2026)** : l'agent est en service dès sa création, sans étapes imposées ; ce qu'il lui faut se branche au fil de la conversation |
| 11 | L'en-tête de la conversation | **Décidé (Julien, 17.11.2026)** : aucun. L'agent ouvert est marqué dans la barre, la zone de saisie dit « Écrivez à Alix », l'état se lit dans la barre |
| 12 | Ouvrir un agent au public | **Décidé (Julien, 17.11.2026)** : brancher un numéro WhatsApp à un agent (il répond alors à des inconnus) passe par l'essai, comme aujourd'hui |

## Les principes

- **Un écran, une route.** Rien ne s'affiche qui n'ait son moteur. Pas de métier « bientôt disponible ».
- **Le contenu ne passe pas par l'atelier.** Une conversation avec un agent va du navigateur à la zone du client (la porte pour l'Europe et les États-Unis, le serveur suisse, l'installation du client). L'atelier, en zone Europe, ne voit que la configuration. Sans cela, l'écran central serait fermé aux clients suisses et aux installations, à qui l'atelier répond aujourd'hui `409`.
- **Un seul agent écrit et agit à la fois.** Les autres sont consultés.
- **Ce qui sort de l'entreprise demande un accord, par défaut.** Envoyer un message, écrire dans un outil branché : « avec accord » à la création de l'agent, que le client peut ensuite assouplir.
- **Un agent est en service dès sa création ; ensuite, un changement est une version.** Renommer, changer une règle : un brouillon, un essai, puis « Mettre en service ».
- **Le mobile d'abord.** Chaque écran est dessiné à 390 px avant 1360 px.
- **Le jeton ne va jamais dans le navigateur.** La session est un cookie `HttpOnly`.
- **Le code de la maquette n'est pas repris.** Elle sert de référence pour le dessin et les textes ; l'interface est réécrite proprement.

## Le moteur à écrire (lot 11)

Une branche et une PR par sous-lot. Tailles de l'étude de marché, à affiner : S, deux semaines-personne ou moins ; M, de deux à six ; L, plus de six.

### 11.1 L'équipe : plusieurs agents par entreprise (M à L)

- **Aujourd'hui** : `Config` décrit un agent et ses rôles ; le conteneur construit un agent par rôle, tous sur la base du client.
- **À faire** : une équipe dans la configuration. Chaque membre a un identifiant, un prénom, un métier, ses consignes, ses outils, ses règles d'accord, un groupe, un état (brouillon, en service, en pause). Le numéro WhatsApp et les rôles restent à l'agent d'accueil. Les documents disent quels agents les consultent.
- **Avec** : mettre un agent en pause, l'archiver ; un nombre d'agents au plus par entreprise ; un plafond de tours par compte et par jour.
- **À surveiller** : la configuration change de version, donc la garde des installations restées sur l'image d'avant (comme `metiers` au lot 10) ; mettre en service un agent sans redémarrer toute l'équipe ; la mémoire du conteneur (110 Mo pour un agent, 550 Mo avec le modèle de recherche, 1 Gio en `basic`).
- **Fini quand** : `essai-megga` a trois agents en service dans un conteneur, chacun avec ses consignes et ses outils ; l'agent d'accueil répond sur WhatsApp comme avant ; le banc de parité de Four Seasons passe sans changement.
- **Conception** (ajout de Thomas, 17.11.2026) : `docs/superpowers/specs/2026-11-17-equipe-dans-la-configuration-design.md`, à valider par Julien. Elle reprend ce paragraphe sur trois points, d'après les décisions 8, 10 et 12 : un agent n'a pas d'état « brouillon » ; son groupe reste hors de la configuration, comme son apparence ; l'accueil peut être tenu par n'importe quel agent de l'équipe. Elle s'accorde aussi à la console fusionnée par la PR #54.

### 11.2 L'entrée console (M)

- **À faire** : le compte connecté parle à un agent de son équipe avec le rôle gestionnaire, au fil de l'eau (la PR #35 l'a fait pour l'entrée par API et l'essai). La conversation est gardée dans le fil du client et se retrouve. Une demande d'accord née d'un tour s'affiche dans la conversation et s'y décide. Les étapes du tour (les outils appelés) remontent avec la réponse.
- **Où** : dans la zone du client, jamais par l'atelier (voir les principes).
- **Fini quand** : « relance les personnes sans réponse », écrit depuis un navigateur, produit une demande d'accord ; acceptée, l'action se fait une fois ; la conversation se relit le lendemain ; rien n'en est gardé hors de la zone.

### 11.3 Le catalogue des métiers d'équipe (M)

- **La source** : agency-agents (MIT, commit `8ae6164`), 283 agents en anglais, dont 218 dépassent 8 000 caractères, la limite de `Config.consignes` (analyse du 17.11.2026). Les quarante métiers d'une version précédente de la maquette en étaient une sélection ; depuis le 17.11.2026, elle montre les huit métiers d'accueil du lot 10, en attendant la douzaine choisie.
- **Pour chaque métier** : traduire, condenser, écrire ce qu'il ne fait jamais, choisir ses outils, écrire trois cas de banc. Le format du lot 10 (`atelier/gabarits/<id>.md`), avec une famille (les dix de la maquette) et un genre (accueil, équipe).
- **La règle** : un métier n'entre au catalogue que si ses outils sont branchés et si son banc passe.
- **Fini quand** : une douzaine de métiers, choisis avec Thomas et Julien, passent leur banc en pass^k et se créent depuis le catalogue.

### 11.4 Les tâches planifiées (S à M)

- **À faire** : une tâche = un agent, une consigne, un rythme (chaque jour, du lundi au vendredi, chaque semaine, tel jour du mois), en service ou suspendue. Elle tourne sur le réveil qui sert déjà aux rappels ; Agno 3.2 a aussi un planificateur (`agno.scheduler`), à évaluer. Son résultat arrive dans la conversation de l'agent. Ce qui sort de l'entreprise passe par un accord.
- **Fini quand** : « chaque matin à 8 h, trie les demandes de la veille » tourne trois jours de suite, se suspend et se retire.

### 11.5 Les pièces jointes (S à M)

- **À faire** : donner un fichier à un agent depuis la console (PDF, image, tableau), gardé dans le stockage du client, dans sa zone ; 8 Mo au plus, comme les documents.
- **Fini quand** : un agent résume un PDF joint et lit un tableau ; le fichier ne passe pas par l'atelier.

### 11.6 Les connecteurs prêts à l'emploi (M à L)

- **Dans la conversation** (Julien, 17.11.2026) : rien n'est imposé à la création. Quand un agent a besoin d'un outil, il propose de le brancher dans la conversation (« Pour voir vos créneaux, branchez votre agenda »), en un clic.
- **À faire** : le reste du lot 9.4. Agenda, courriel et fichiers de Google Workspace ou de Microsoft 365, par leurs serveurs MCP ; la connexion par le client lui-même, son état, la reconnexion.
- **Fini quand** : un client branche son agenda sans MEGGA ; un agent y lit les créneaux libres ; une connexion perdue devient une alerte avec « Reconnecter ».

### 11.7 Travailler à plusieurs (M, en dernier)

- **À faire** : « @Léa » passe la demande à un collègue avec un résumé, comme le transfert vers un humain (9.3). Dans une conversation de groupe, un agent mène et écrit ; les autres sont consultés (Agno a des équipes, `agno.team`, à évaluer).
- **Fini quand** : une demande passée à un collègue garde son contexte ; aucun cas du banc ne montre deux agents qui font la même action.

## L'interface (lot 8)

### 8.1 Les fondations, la connexion, l'équipe (M)

- **Écrans** : connexion ; premier lancement ; la barre (chercher, nouvel agent, les agents par groupe, un seul style d'épinglés, l'état de chacun) ; créer un agent comme dans la maquette (prénom, métier dans le catalogue, couleur et yeux de la mascotte) ; l'agent créé est en service tout de suite, et sa conversation s'ouvre.
- **Interface** : le dossier `console/`, les jetons de couleur (deux thèmes, contrastes à 4,5), les composants de base, sur shadcn (bouton, carte, liste, état vide, erreur, chargement), la mascotte en composant, les textes dans un fichier par langue.
- **Moteur à ajouter** : les comptes et les sessions, avec Better Auth (un compte relié à une entreprise, deux rôles : propriétaire et collaborateur) ; l'invitation ; l'apparence gardée par l'atelier.
- **Demande** : 11.1.
- **Fini quand** : une personne invitée se connecte, crée un agent, le retrouve en service dans son groupe, sur 390 px comme sur bureau ; une erreur de l'atelier s'affiche sous son champ ; la CI joue ce parcours contre un faux atelier.

### 8.2 Parler à un agent (M)

- **Écrans** : la conversation de la maquette, sans en-tête (l'agent ouvert est marqué dans la barre) ; les étapes repliées ; la carte d'accord avec « Accepter », « Refuser » et le contenu exact.
- **Interface** : un petit essai de CopilotKit (AG-UI) avant de choisir comment la conversation se branche à l'agent.
- **Demande** : 11.2.
- **Coupé de la maquette** : « Modifier » sur un accord (le moteur n'accepte qu'un oui ou un non : on redemande à l'agent), le micro (selon la décision 9).
- **Fini quand** : le parcours du 11.2 se fait à l'écran ; la réponse s'écrit au fil de l'eau ; une panne de l'agent s'affiche avec « Réessayer ».

### 8.3 À valider, et l'activité (S à M)

- **Écrans** : tous les accords en attente, de tous les agents, le compteur en couleur ; le temps restant ; l'activité (chaque action d'un agent, d'après le journal d'audit).
- **Routes** : `approbations`, `audit`.
- **Moteur à ajouter** : les noms des outils en clair dans le catalogue ; une alerte quand une demande attend depuis longtemps (restes du 9.1).
- **Fini quand** : une demande s'accepte ou se refuse une seule fois (un `409` s'explique en clair) ; le compteur suit.

### 8.4 La bibliothèque (S)

- **Écrans** : la liste ; déposer un document (texte, PDF, page) ; choisir les agents qui le consultent ; le retirer ; les refus en clair (illisible, vide, plus de 8 Mo, plus de 200 documents).
- **Routes** : `connaissances`.
- **Coupé de la maquette** : le site relu chaque nuit, le tableau Google, les dossiers, tant que les connecteurs (11.6) ne sont pas là.
- **Fini quand** : un PDF déposé est cité par un agent qui y a accès, et ignoré par un agent qui ne l'a pas.

### 8.5 Planifié (S)

- **Écrans** : les tâches, par heure ; en créer une en l'écrivant ; la suspendre, la retirer ; son dernier résultat.
- **Demande** : 11.4.
- **Fini quand** : une tâche se crée, se suspend et se retire sur mobile ; son dernier résultat ouvre la conversation de l'agent.

### 8.6 Aujourd'hui (S à M)

- **Écrans** : ce que chaque agent a fait depuis hier, avec un lien vers la conversation ; les alertes, chacune avec ce qu'il faut faire ; les chiffres de la période.
- **Routes** : `valeur`, `suivi`, `alertes`, à étendre à toute l'équipe.
- **Fini quand** : chaque carte mène quelque part ; les chiffres portent l'heure de leur calcul ; aucun coût d'achat de MEGGA n'apparaît à un client.

### 8.7 Les agents d'accueil (M)

- **Écrans**, pour un agent qui a un numéro WhatsApp : les conversations de ses clients ; les conversations transmises à l'équipe (« Je la prends », répondre, « Rendre à l'agent ») ; les demandes notées ; les droits d'une personne (remettre, effacer).
- **Routes** : `conversations`, `reprises`, `leads`, `personnes`.
- **Fini quand** : une conversation transmise se prend, reçoit une réponse et se rend, sur mobile.

### 8.8 Les réglages (M)

- **Écrans** : pour un agent : ses consignes, ses outils, ses règles d'accord, ses documents, son groupe, le mettre en pause, l'archiver (avec confirmation), ses versions (un changement passe par un brouillon, s'essaie, se met en service, et « Revenir à la version d'avant ») ; pour un agent d'accueil : la voix, le ton, le transfert, la mention de l'IA ; pour le compte : l'équipe, les connexions, les modèles, les clés des logiciels.
- **Fini quand** : chaque réglage laissé au client se change ici et passe par un brouillon ; ce que MEGGA règle s'affiche sans pouvoir se modifier ; tout se fait au doigt et au clavier, sans clic droit.

### 8.9 La vue MEGGA (M)

- **Écrans** : toutes les entreprises (état, version, alertes) ; reprendre ou rendre la main ; créer une entreprise ; les installations ; les tarifs et les coûts ; le banc d'essai et son rapport ; le catalogue des métiers.
- **Fini quand** : Julien met en service une entreprise de bout en bout sans script ni `curl`, sauf la base chez Neon et le numéro chez Meta.

### 8.10 À plusieurs (S à M)

- **Écrans** : « @ » dans la zone de saisie ; les conversations de groupe de la maquette.
- **Demande** : 11.7.
- **Fini quand** : dans un groupe, on voit qui mène et qui a été consulté ; chaque message porte le prénom de son agent.

## L'ordre

| Étape | Moteur | Interface | Ce qu'on a à la fin |
|---|---|---|---|
| 1 | 11.1 | 8.1 | On se connecte, on crée une équipe |
| 2 | 11.2 | 8.2 | On parle à un agent, il agit avec accord |
| 3 | 11.3 | 8.3, 8.4 | Une douzaine de métiers, les accords, l'activité, les documents |
| 4 | 11.4, 11.5 | 8.5, 8.6 | Les tâches planifiées, les pièces jointes, le point du jour |
| 5 | 11.6 | 8.7, 8.8, 8.9 | Les agents branchés aux outils du client, l'accueil, les réglages, la vue MEGGA |
| 6 | 11.7 | 8.10 | Le travail à plusieurs |

La console est utilisable par un premier client à la fin de l'étape 3, et complète à la fin de l'étape 5. Ordre de grandeur, à affiner sous-lot par sous-lot : quatre à six mois-personne pour les étapes 1 à 3, à peu près autant pour les étapes 4 et 5.

Avant de commencer : fusionner les PR empilées du lot 9 (#38, #39, #41, #42, #43, #44), le lot 10 (#53) et la réponse au fil de l'eau (#35). Le lot 11 s'appuie sur toutes.

## Ce qui reste hors de ce plan

- L'allemand, l'italien et l'anglais : les textes sont prêts à être traduits dès le 8.1.
- L'abonnement, la facturation, et le prix d'une équipe (par agent, par entreprise, à l'usage).
- Les notifications hors WhatsApp (courriel, notification du téléphone).
- La console servie par une installation chez le client, sans passer par MEGGA.
- Le reste des 283 agents : après le premier lot du catalogue, métier par métier, selon la règle du 11.3.
