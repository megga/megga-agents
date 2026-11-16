# Lot 7 : Alix FSP sur le socle

Alix FSP (dépôt `megga/fourseasonsproperties`, Worker `fourseasons-alix`) compte environ 8 800 lignes et 48 fichiers d'essai : trois sortes d'interlocuteurs et une soixantaine de fonctions. Elle continue de tourner sans changement jusqu'à la bascule (7.7), qui ne se fait qu'avec l'accord de Julien. Le découpage, validé par Julien le 16.11.2026, une branche et une PR par sous-lot :

| Sous-lot | Contenu |
|---|---|
| **7.1 Fondations** (fait) | les rôles des personnes, les médias de WhatsApp, le branchement à la gestion du site, la configuration de Four Seasons |
| **7.2 Annonces** (fait) | lire, chercher, brouillon puis création, modifier, retirer ; garde-fous et rédaction ; photos, vidéos, mots de passe, clients, carrousel, transfert, formulaire WhatsApp |
| **7.3 Fiche PDF** (fait) | gardée en JavaScript (pdf-lib), appelée comme un service ; choix des photos, photos tirées d'une plaquette |
| **7.4 Partenaires et visiteurs** (fait) | registre, vitrine, rapprochement, accueil, questions transmises au courtier, demandes du site, envoi à un contact, blocages |
| 7.5 Marché | recherche sur les portails, veille, suivi de zones, carnet des prix |
| 7.6 Comportements | règles apprises, fil, capacités, règles d'affichage, messages hors des 24 heures |
| 7.7 Parité et bascule | les scénarios d'Alix en scénarios neutres, joués sur les deux (sur le socle par l'entrée par API), la copie des données, le numéro de test, la bascule sur accord |

Décidé par Julien (16.11.2026) : Claude à la place de Gemini pour rédiger les annonces et regarder les photos (l'humeur d'un vocal, qui demandait Gemini, n'est pas reprise) ; ElevenLabs seul pour écouter et parler (ni Whisper ni Telnyx).

## 7.1 Les fondations

**Les rôles** (`Config.roles`, `noyau/roles.py`). Sans rôles, rien ne change : tout le monde parle au même agent. Avec eux, un agent par rôle, avec les consignes et les outils de ce rôle en plus de ceux de tous :
- **gestionnaire** : les gens du client. Leurs numéros et leur compte dans la gestion du site viennent du secret `GESTIONNAIRES` (JSON `{"+41…": "compte"}`), jamais de la configuration ;
- **partenaire** : inscrit par le client (table `megga_partenaires` ; les outils pour inscrire et ce qu'un partenaire peut demander viennent au 7.4) ;
- **visiteur** : toute autre personne. Sans ce rôle, un visiteur n'est pas servi ; un refus poli (`roles.refus`) part au plus une fois par jour ;
- **bloqué** (table `megga_bloques`) : jamais lu, jamais répondu, quel que soit le rôle.

Une personne venue d'un logiciel par API est un visiteur ; des rôles sans visiteurs ferment l'entrée par API (403).

**Les médias** (`noyau/whatsapp.py`). Reçus : photos, vidéos (compressées ou en qualité d'origine) et documents, avec leur légende, numérotés par personne (`megga_medias` : « média 3 » désigne le même fichier pour l'agent et ses outils ; seul l'identifiant chez Meta est gardé). Une photo est montrée au modèle (cinq par tour au plus), jamais gardée dans l'historique. Le choix dans une liste ou un bouton, un formulaire rempli et le nom WhatsApp de la personne sont lus aussi. Envoyés : image, document, vidéo (par identifiant ou par lien), dépôt d'un fichier, liste, boutons, carrousel, formulaire (WhatsApp Flow).

**La gestion du site** (`packs/immobilier/gestion.py`, `Config.gestion`). L'API `/api/gestion` du site, au nom du compte d'un gestionnaire, avec la clé partagée `GESTION_CLE` (secret). Les sites propres à certains biens (`gestion.sites`, par préfixe de l'identifiant). Les outils qui s'en servent viennent au 7.2.

**La configuration de Four Seasons** : `clients/four-seasons-properties.yaml`, sans aucun secret, avec ses trois rôles, en zone Europe (à confirmer), et pas encore de numéro WhatsApp (seulement par API jusqu'au numéro de test). Ses consignes complètes arrivent avec ses outils.

**Les secrets** : chez Cloudflare, `scripts/secrets_gestion.sh <id> <porte>` pose `GESTION_CLE` et `GESTIONNAIRES` (saisie masquée, par Julien) ; chez le client, des variables comme les autres (`docs/installation-client.md`).

## 7.2 Les annonces

`packs/immobilier/annonces.py` : 32 outils, pour le rôle qui a le groupe `annonces` (les gestionnaires), tous au nom du compte de la personne dans la gestion du site. Ce qu'un outil garde d'un tour à l'autre (le brouillon, l'action à confirmer) est dans la base du client (`megga_etats`), pas en mémoire : un conteneur endormi ne perd rien.
- **Lire** : `lister_annonces`, `voir_annonce`, `chercher_biens` (budget, chambres, surface, communes, type, équipements, mots).
- **Créer** : `preparer_annonce` rassemble les faits (ce qui est déjà dit est gardé), fait rédiger les textes par Claude d'après les mots du courtier et ses photos (`redaction.py`), et montre le brouillon ; `creer_annonce` ne le crée qu'au message suivant, puis range les photos et la plaquette PDF.
- **Modifier** : `modifier_annonce`, `reecrire_annonce` (à confirmer) ; `masquer_annonce`, `supprimer_annonce`, toujours à confirmer : `confirmer_action` refuse dans le tour même qui a préparé.
- **Garde-fous** (`garde.py`) : ni tiret long ni point médian ; jamais un nom de `gestion.noms_interdits` ni une consigne (« PDF », « brouillon ») dans un texte ; un titre ni trop court ni une liste de mots.
- **Photos et documents** : `ajouter_photos`, `couverture_photo`, `ordonner_photos`, `retirer_photos`, `ajouter_document`, d'après les médias reçus (« média 3 ») et les numéros de `voir_annonce`.
- **Mots de passe** : `acces_annonce` (verrouiller, changer ; jamais déverrouiller depuis WhatsApp), `mot_de_passe_site` et `porte_site` (administrateur seulement), `envoyer_mot_de_passe`. Un mot de passe part seul dans la conversation, jamais dans ce que lit le modèle.
- **Vidéos** : `ajouter_video` (par lien), `envoyer_video`, `retirer_video`.
- **Montrer** : `montrer_biens` (carrousel, photos par lien signé), `message_client` (prêt à transférer), `formulaire_annonce` (le WhatsApp Flow de `gestion.formulaire_annonce`).
- **Clients** : `recherche_client`, `lister_recherches_clients`, `biens_pour_recherche`, `supprimer_recherche_client`, `lire_bien_prive`, `proprietaire_bien`, `partage_bien`.

Pas encore : une vidéo reçue en fichier (la gestion range les fichiers vidéo dans un stockage que seul le site atteint ; par lien en attendant). L'envoi à un contact est venu au 7.4.

## 7.3 La fiche PDF

**Le service de fiche** (`fiche/`) : la mise en page d'Alix FSP (pdf-lib), reprise sans rien réécrire, dans l'image elle-même. L'agent l'appelle comme un processus (`node fiche/src/composer.mjs` : une demande JSON en entrée, le PDF en sortie) ; rien ne sort du conteneur, et la même fiche marche chez Cloudflare comme chez le client. Le modèle de fiche d'un client (ses polices et son logo, `fiche/modeles/<modèle>/ressources.js`) se règle dans `gestion.fiche` ; le nom de la marque vient de `entreprise`. L'image embarque Node (étape `fiche` du Dockerfile, environ 120 Mo de plus).

**Les outils** :
- `fiche_pdf` : la fiche d'une annonce du site (par son identifiant ou sa référence) ou d'un bien qui n'y est pas (ses photos reçues et ce qu'en dit le courtier, les textes rédigés au besoin) ; anonyme par défaut (ni contact, ni référence, ni ligne qui nomme la marque), de marque sur demande, sans prix pour un partenaire, en français ou en anglais ; Claude choisit la couverture et les plus belles photos (`redaction.Choisisseuse`, à la place de Gemini), sauf s'il faut garder l'ordre. Le PDF part dans la conversation.
- `photos_du_pdf` : les photos d'une plaquette PDF reçue (ni petites, ni allongées, ni grises, ni en double ; en JPEG tel quel ou en PNG refait), qui deviennent des médias comme des photos reçues (`pdf:<média du PDF>#<rang>`), reprises du PDF quand un outil s'en sert.

## 7.4 Les partenaires et les visiteurs

Quatre groupes d'outils de plus, par rôle (`Role.outils`) ; ceux qui agissent au nom d'un compte de gestion (`annonces`, `partenaires`, `visiteurs`) ne vont qu'au rôle gestionnaire, la configuration refuse le reste.
- **partenaires** (gestionnaire, `packs/immobilier/reseau.py`) : `ajouter_partenaire` (prénom et nom de famille exigés), `retirer_partenaire`, `lister_partenaires` (par nom de famille), `regle_partenaire` (ce qui part d'office : fiche partenaire, fiche normale, quelques lignes, rien), `recherches_partenaires`, `clore_recherche`, `repondre_partenaire`.
- **vitrine** (partenaire) : son seul outil, `chercher_biens`, ne lit que la vitrine du site (`GET /api/gestion/vitrine`) et ne rend que des références, des types, des communes et des chiffres ; même si la vitrine en disait plus, ni prix ni adresse ne passent. Pas même les rappels : il n'a rien d'autre. Ses messages sont des données, sa consigne le dit, mais la garde est l'absence du code.
- **visiteurs** (gestionnaire, `packs/immobilier/visiteurs.py`) : `repondre_visiteur` (par l'identifiant de la question ou le nom du visiteur ; `clore` s'il s'en charge), `envoyer_a_un_contact` puis `confirmer_envoi` au message suivant (10 envois par jour ; jamais à un gestionnaire, un partenaire ni un bloqué ; un mot de passe d'annonce part dans un aperçu direct, jamais par le modèle), `bloquer_numero`, `debloquer_numero`, `lister_bloques` (un partenaire bloqué est retiré).
- **accueil** (visiteur) : `chercher_biens` (les biens des sites publics, `gestion.publics`, avec prix et lien ; les autres en une ligne, sans prix ni lien ; un off-market, de vive voix), `transmettre_contact` (après son oui, trois fiches par jour), `demander_au_courtier` (quatre questions par jour).

**Le partenaire cherche, le courtier choisit.** Sa recherche part au gestionnaire, après sa réponse : une liste à toucher par bien. Le choix touché revient par l'identifiant de la ligne (`pc:<demande>:<rang>:<choix>`) et se traite sans le modèle (`Conversations.choix`), une fois (écriture conditionnelle), seulement pour un gestionnaire ; s'il répond en mots, `repondre_partenaire`. La fiche partenaire (anonyme, sans prix) ou normale est composée par le service de fiche (7.3), déposée chez Meta et envoyée au partenaire ; quelques lignes, en texte. Avec une règle, rien n'est demandé : elle s'applique et le gestionnaire en reçoit la note.

**L'effet réseau et le rapprochement.** Une recherche assez précise (deux critères parmi type, communes, budget, chambres, surface) est gardée trois mois (`megga_recherches`). Quand le site signale un bien entré en ligne, les recherches gardées partent à la gestion (`POST /api/gestion/vitrine/correspondances`, le prix reste sur le serveur) : chaque partenaire concerné devient une demande (un bien déjà proposé ce mois-ci ne revient pas). Le même bien est rapproché des clients que chaque gestionnaire a dans sa mémoire (celle d'Agno), triés par Claude (`redaction.Assistante`) ; sauf off-market ou privé, et une fois par bien.

**Le visiteur.** L'accueil de Greg part tel quel au premier message d'une conversation (rien depuis douze heures), en français ou en anglais, avec le prénom du profil WhatsApp s'il en est un vrai (`Role.accueil`, `noyau/accueil.py`, générique) ; à une simple salutation, l'accueil seul ; dans une autre langue, le modèle le traduit. Sa question au courtier part avec un identifiant ; la réponse lui est relayée. Six heures sans réponse (jamais entre 20 h et 9 h), il est prévenu une fois : une échéance (`Conversations.echeances`) que `/interne/rappels` traite et dont l'heure s'ajoute au prochain réveil de la porte. Un visiteur venu par API reçoit la réponse à son prochain message (le Contexte la lui fait transmettre).

**Le Contexte de chaque tour.** Les consignes d'un rôle deviennent une fonction (`noyau/agent.py`, `instructions_du_tour`) qui ajoute, pour la personne qui parle : ses demandes et leur état (partenaire), les demandes qui attendent un choix, les questions ouvertes, les contacts et les demandes du site récents, ce qu'Alix a signalé de lui-même (gestionnaire), les réponses du courtier (visiteur).

**Hors des 24 heures.** Ce que l'agent envoie de lui-même (`Conversations.envoyer_de_soi_meme`) part dans la fenêtre ; sinon il est gardé (`megga_differes`) et part au prochain message de la personne, avant sa réponse, et le modèle Meta de l'usage l'annonce s'il est réglé (`modeles_meta` : `partenaire`, `livraison`, `demande`, `reponse_visiteur`, `suivi_visiteur`, `ouverture`, `rapprochement` ; `<usage>_<langue>` d'abord).

**Les entrées du site (choix à valider).** Deux routes de l'agent, protégées par la clé du site (`SITE_CLE`, secret du client, 32 caractères au moins ; sans elle, 404) : `POST /site/bien {reference}` (202, le rapprochement et le réseau suivent en arrière-plan) et `POST /site/demande` (le formulaire d'une fiche : au courtier du bien, ou à tous les courtiers qui sont gestionnaires, avec une réponse prête rédigée par Claude et un lien wa.me qui l'ouvre). Chez Cloudflare, la porte les transmet telles quelles (`POST /site/<client>/bien|demande`, refusées sans clé bien formée, sans réveiller le conteneur) ; chez le client, Caddy et l'ingress de Helm les exposent. Le site d'Alix FSP appelle aujourd'hui `/bien` et `/demande` d'Alix par une liaison de service avec `GESTION_ALIX_CLE` : à la bascule, `SITE_CLE` peut prendre la même valeur et le site appeler la porte. Écarté : passer par `/interne/…` (le jeton interne est propre à la porte et ne doit pas sortir).

**Les tables** (additives, sans changer `SCHEMA_VERSION`) : `megga_partenaires` gagne `famille`, `agence`, `regle` ; `megga_bloques` gagne `nom` (deux tables du 7.1, encore jamais déployées) ; nouvelles : `megga_demandes`, `megga_propositions`, `megga_recherches`, `megga_questions`, `megga_differes`.

**Four Seasons** : `clients/four-seasons-properties.yaml` donne les groupes à ses trois rôles, ses consignes (Greg, l'ordre des destinations, les devises, les marchés), l'accueil de Greg mot pour mot et ses sites publics (Marbella, Dubaï). Rien de Four Seasons dans le noyau ni dans le pack (un essai le vérifie).

## Ce qui reste après le 7.4

- Les modèles Meta (accord, livraison, demande, suivi, ouverture) : leurs noms dans `modeles_meta` quand le numéro de test existera (7.7). Sans eux, ce qui part hors des 24 heures attend le prochain message.
- Le blocage chez Meta en plus de notre liste (Alix le fait quand Meta le permet) ; la vidéo reçue en fichier (7.2).
- Le site de Four Seasons qui appelle la porte (`/site/…`) au lieu d'Alix : à la bascule (7.7), avec Julien.
- Les réactions et le vocal propres aux visiteurs et aux partenaires sont ceux du noyau (le 👀, un vocal pour un vocal) ; l'humeur d'un vocal n'est pas reprise (décision du 16.11.2026).

## Ce qui reste après le 7.1

- Une configuration avec des rôles ou une gestion demande une image qui les connaît (celle qui suit la 0.3.0) : une installation restée sur la 0.3.0 la refuse.
- Le choix de la zone de Four Seasons (Europe chez Cloudflare, ou Suisse quand elle existera).
