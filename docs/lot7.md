# Lot 7 : Alix FSP sur le socle

Alix FSP (dépôt `megga/fourseasonsproperties`, Worker `fourseasons-alix`) compte environ 8 800 lignes et 48 fichiers d'essai : trois sortes d'interlocuteurs et une soixantaine de fonctions. Elle continue de tourner sans changement jusqu'à la bascule (7.7), qui ne se fait qu'avec l'accord de Julien. Le découpage, validé par Julien le 16.11.2026, une branche et une PR par sous-lot :

| Sous-lot | Contenu |
|---|---|
| **7.1 Fondations** (fait) | les rôles des personnes, les médias de WhatsApp, le branchement à la gestion du site, la configuration de Four Seasons |
| **7.2 Annonces** (fait) | lire, chercher, brouillon puis création, modifier, retirer ; garde-fous et rédaction ; photos, vidéos, mots de passe, clients, carrousel, transfert, formulaire WhatsApp |
| **7.3 Fiche PDF** (fait) | gardée en JavaScript (pdf-lib), appelée comme un service ; choix des photos, photos tirées d'une plaquette |
| **7.4 Partenaires et visiteurs** (fait) | registre, vitrine, rapprochement, accueil, questions transmises au courtier, demandes du site, envoi à un contact, blocages |
| **7.5 Marché** (fait) | recherche sur les portails, veille, suivi de zones, carnet des prix |
| **7.6 Comportements** (fait) | règles apprises, fil, capacités, règles d'affichage, messages hors des 24 heures |
| **7.7 Parité et bascule** (parité et copie faites ; numéro et bascule à Julien) | les scénarios d'Alix en scénarios neutres, joués sur les deux, la copie des données, le numéro de test, la bascule sur accord |

Décidé par Julien (16.11.2026) : Claude à la place de Gemini pour rédiger les annonces et regarder les photos (l'humeur d'un vocal, qui demandait Gemini, n'est pas reprise) ; ElevenLabs seul pour écouter et parler (ni Whisper ni Telnyx) ; la recherche sur les portails reste chez DeepSeek (7.5).

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

## 7.5 Le marché

Un groupe d'outils de plus, `marche`, pour les gestionnaires seulement (`packs/immobilier/marche.py`, `carnet.py`). Les régions et leurs portails viennent de la configuration (`Config.marche` : pour chaque région, les grands portails de la recherche simple, puis les autres) ; rien d'une agence dans le pack.
- **Les portails** : `chercher_marche` (mode simple : les grands portails, requêtes groupées par « OR », 128 caractères au plus ; avancée : une requête par portail, puis la lecture des cinq meilleures annonces), par région ou sur les sites nommés. La recherche passe par l'outil de recherche web de DeepSeek (`/v1/tools/search` et `/v1/tools/fetch`, la clé du modèle de secours), comme dans Alix : ce n'est pas le portail en direct. Ne restent que les pages d'une annonce (un identifiant dans le chemin), sur les sites demandés.
- **Sans lien pour le modèle** : les résultats sont numérotés ; `montrer_annonces` ouvre chaque annonce choisie, écarte celle qui n'est plus en ligne, et l'envoie dans sa carte (titre, prix, pièces ou chambres, surface, portail, lien exact avec aperçu). `lire_annonce_marche` la lit en entier.
- **La veille**, seulement à la demande : `surveiller_marche` (chaque jour ou chaque semaine, 4 semaines par défaut, 12 au plus, 10 veilles par courtier), `annuler_veille`. Seules les nouvelles annonces partent, triées par Claude puis vérifiées. **Le suivi d'une zone** : `suivre_zone` (une recherche approfondie par semaine, 12 semaines au plus, 5 zones), `arreter_zone` ; il ne prévient que si la médiane des prix demandés bouge de 5 % ou plus, sur cinq relevés au moins, et dit quand il s'arrête. Veilles et zones (`megga_veilles`) passent à l'heure dite comme le suivi des visiteurs (`Conversations.echeances`) ; leur passage est réservé avant d'être fait, deux réveils ne le font pas deux fois. Hors des 24 heures, ce qu'elles trouvent attend le prochain message (modèles Meta `veille` et `zone` s'ils sont réglés).
- **Le carnet des prix au m²** (`megga_releves`, 2 000 relevés, partagé par les gestionnaires) : `noter_marche` (vente réalisée, avis en fourchette, annonce avec son lien ; un prix au m² hors des bornes plausibles est refusé, souvent le terrain pris pour l'habitable), `releves_marche`, `retirer_releve`. Les annonces lues sur les portails y entrent d'elles-mêmes quand Claude y lit clairement un prix de vente et une surface habitable (`redaction.Assistante.lire_fiches`). `analyser_marche` et `comparer_bien` rendent des chiffres calculés dans le code (médiane, quartiles, valeurs hors norme écartées), par source, avec la période ; jamais par le modèle.
- **`clients_pour_bien`** : les clients que le courtier a en mémoire dont les critères collent à un bien (le nôtre, ou décrit), triés par Claude.

**Four Seasons** : ses cinq régions (Suisse par défaut, prestige international, Espagne pour Marbella, France voisine, Dubaï) et leurs portails dans `clients/four-seasons-properties.yaml`, le groupe `marche` pour ses gestionnaires.

**Décidé par Julien (16.11.2026)** : la recherche sur les portails reste chez DeepSeek, comme dans Alix (0,75 $ les 1 000 recherches), plutôt que la recherche web de Claude.

## 7.6 Les comportements

- **Le fil** (`noyau/fil.py`, `Config.fil`, générique) : l'agent relit les douze derniers tours ; ce qui sort de cet historique se fond, après la réponse et en arrière-plan, dans un résumé court (1 500 caractères), refait chaque fois que douze messages de plus en sont sortis, par le modèle de l'oral ou du secours. Il se relit à chaque tour, entre balises, comme une donnée ; jamais un mot de passe ni un code ; il s'efface après trente jours sans message. Pour Four Seasons : activé. Les autres clients n'y gagnent rien tant qu'on ne l'active pas (un appel de modèle de plus toutes les douze réponses).
- **Les règles apprises** (groupe `travail`, gestionnaire, `packs/immobilier/travail.py`, table `megga_regles`, 30 par courtier) : `apprendre_regle` (portée : partout, une personne, ou un site de `gestion.sites` et le principal), `oublier_regle`, `regles`. Elles se relisent toutes à chaque tour (le Contexte). Une règle doit reprendre au moins 30 % des mots du dernier message du courtier (`Conversations.entendu`) : une page lue ou un message relayé ne peut pas en faire apprendre une. Une règle qui contredirait une consigne absolue (prix ou adresse aux partenaires, mot de passe affiché, mandat confidentiel rendu public, tiret long, estimation) est refusée, sauf si elle va dans leur sens.
- **Le point** (`point`), seulement à la demande : les annonces sans photo, masquées ou pas en ligne, les demandes du site, les questions des visiteurs sans réponse, les demandes des partenaires qui attendent un choix, les rappels, les veilles.
- **Les capacités** : pour un rôle qui a le groupe `travail`, ce que l'agent sait faire, d'après ses groupes et la configuration réelle (le formulaire s'il est publié, les partenaires et les visiteurs seulement s'ils peuvent écrire, la voix si elle est réglée) ; rien n'est promis qui n'est pas en service.
- **La règle d'affichage** d'Alix (une idée par bloc, titres en gras, un bloc par bien, montants et surfaces écrits pareil, ni tableau, ni « # », ni point médian, ni tiret long) : dans les consignes de tout rôle qui a un outil du pack.
- **Hors des 24 heures** : si le modèle Meta de l'usage manque, le modèle « message » (`modeles_meta.message`, sa variable : le nom de l'agent) annonce ce qui est gardé ; sa réponse rouvre les 24 heures et tout part aussitôt. Un rappel sans modèle « rappel » l'utilise aussi. Ce qui ne se garde pas (le suivi d'un visiteur) ne s'annonce pas.

## 7.7 La parité et la bascule

Décidé par Julien (16.11.2026) : une route d'export dans Alix pour copier ses données (le seul changement apporté à Alix avant la bascule) ; la parité jouée avec le vrai Claude et un juge ; le numéro de test créé par Julien, préparé ici. La marche à suivre complète : `docs/bascule-fsp.md`.

- **La parité** (`parite/`) : les 36 cas du banc noté d'Alix en scénarios neutres (`cas.json` : qui écrit quoi, le temps qui passe, des critères vérifiés sur la trace ou lus par un juge). Les deux agents les jouent en local avec le vrai Claude : Alix par son propre banc (`alix.mjs`, sans rien modifier dans son dépôt), le socle tel que `creer` le construit, contre la vraie gestion du site servie en local (`socle.py`, `gestion.mjs`). Les mêmes critères et le même juge notent les deux (`noter.py`). Premier passage (16.11.2026, Claude Sonnet 5.5, juge Sonnet 5.5) : **Alix 89 / 100, socle 88 / 100** ; chacun gagne des cas que l'autre perd, à hauteur de ce que le juge varie d'un passage à l'autre (3 points pour Alix entre deux notations des mêmes traces). Le rapport : `docs/parite-7-7.md`. Pas de défaut du socle trouvé ; les écarts sont des choix de réponse du modèle (un visiteur qui revient n'est pas salué par son nom, une suite proposée différente). Un biais : le socle ne vide pas son historique avec le temps (Alix repart à neuf après 12 heures), les cas « le lendemain » (G06, G14, R01, M01, V08) lui sont plus faciles.
- **La copie des données** : la route `GET /export` d'Alix (megga/fourseasonsproperties#132, en lecture seule, protégée par `EXPORT_CLE`, non déployée), jointe le temps de la copie par une adresse `workers.dev` ouverte puis refermée (décidé par Julien) ; l'import `python -m packs.immobilier.reprise export.json` (partenaires et leur règle, numéros bloqués, demandes et leurs choix, recherches gardées, souvenirs des gestionnaires dans la mémoire d'Agno, règles de travail, fil, veilles, zones, carnet du marché), une fois par base, identifiants gardés, dates converties ; refaite (`--encore`), elle ne double rien. Essayé sur un export produit par le vrai code d'Alix (`tests/donnees/export_alix.json`).
- **Le numéro de test** et **la bascule** : la marche à suivre, les modèles Meta à soumettre et la décision qui reste (le numéro que le socle sert pour Four Seasons après la bascule) sont dans `docs/bascule-fsp.md`. Le mode relais d'Alix (transmettre au socle au lieu de répondre) est un second changement dans son dépôt, à faire seulement sur l'accord de Julien.

## Ce qui reste après le 7.4

- Les modèles Meta (message, rappel, partenaire, livraison, demande, reponse_visiteur, suivi_visiteur, ouverture, veille, zone, rapprochement) : leurs noms dans `modeles_meta` quand le numéro de test existera (7.7). Sans eux, ce qui part hors des 24 heures attend le prochain message.
- Le blocage chez Meta en plus de notre liste (Alix le fait quand Meta le permet) ; la vidéo reçue en fichier (7.2).
- Le site de Four Seasons qui appelle la porte (`/site/…`) au lieu d'Alix : à la bascule (7.7), avec Julien.
- Les réactions et le vocal propres aux visiteurs et aux partenaires sont ceux du noyau (le 👀, un vocal pour un vocal) ; l'humeur d'un vocal n'est pas reprise (décision du 16.11.2026).

## Ce qui reste après le 7.1

- Une configuration avec des rôles ou une gestion demande une image qui les connaît (celle qui suit la 0.3.0) : une installation restée sur la 0.3.0 la refuse.
- Le choix de la zone de Four Seasons (Europe chez Cloudflare, ou Suisse quand elle existera).
