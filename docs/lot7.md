# Lot 7 : Alix FSP sur le socle

Alix FSP (dépôt `megga/fourseasonsproperties`, Worker `fourseasons-alix`) compte environ 8 800 lignes et 48 fichiers d'essai : trois sortes d'interlocuteurs et une soixantaine de fonctions. Elle continue de tourner sans changement jusqu'à la bascule (7.7), qui ne se fait qu'avec l'accord de Julien. Le découpage, validé par Julien le 16.11.2026, une branche et une PR par sous-lot :

| Sous-lot | Contenu |
|---|---|
| **7.1 Fondations** (fait) | les rôles des personnes, les médias de WhatsApp, le branchement à la gestion du site, la configuration de Four Seasons |
| **7.2 Annonces** (fait) | lire, chercher, brouillon puis création, modifier, retirer ; garde-fous et rédaction ; photos, vidéos, mots de passe, clients, carrousel, transfert, formulaire WhatsApp |
| **7.3 Fiche PDF** (fait) | gardée en JavaScript (pdf-lib), appelée comme un service ; choix des photos, photos tirées d'une plaquette |
| 7.4 Partenaires et visiteurs | registre, vitrine, rapprochement, accueil, questions transmises au courtier, demandes du site, envoi à un contact, blocages |
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

Pas encore : une vidéo reçue en fichier (la gestion range les fichiers vidéo dans un stockage que seul le site atteint ; par lien en attendant), l'envoi à un contact (7.4).

## 7.3 La fiche PDF

**Le service de fiche** (`fiche/`) : la mise en page d'Alix FSP (pdf-lib), reprise sans rien réécrire, dans l'image elle-même. L'agent l'appelle comme un processus (`node fiche/src/composer.mjs` : une demande JSON en entrée, le PDF en sortie) ; rien ne sort du conteneur, et la même fiche marche chez Cloudflare comme chez le client. Le modèle de fiche d'un client (ses polices et son logo, `fiche/modeles/<modèle>/ressources.js`) se règle dans `gestion.fiche` ; le nom de la marque vient de `entreprise`. L'image embarque Node (étape `fiche` du Dockerfile, environ 120 Mo de plus).

**Les outils** :
- `fiche_pdf` : la fiche d'une annonce du site (par son identifiant ou sa référence) ou d'un bien qui n'y est pas (ses photos reçues et ce qu'en dit le courtier, les textes rédigés au besoin) ; anonyme par défaut (ni contact, ni référence, ni ligne qui nomme la marque), de marque sur demande, sans prix pour un partenaire, en français ou en anglais ; Claude choisit la couverture et les plus belles photos (`redaction.Choisisseuse`, à la place de Gemini), sauf s'il faut garder l'ordre. Le PDF part dans la conversation.
- `photos_du_pdf` : les photos d'une plaquette PDF reçue (ni petites, ni allongées, ni grises, ni en double ; en JPEG tel quel ou en PNG refait), qui deviennent des médias comme des photos reçues (`pdf:<média du PDF>#<rang>`), reprises du PDF quand un outil s'en sert.

## Ce qui reste après le 7.1

- Une configuration avec des rôles ou une gestion demande une image qui les connaît (celle qui suit la 0.3.0) : une installation restée sur la 0.3.0 la refuse.
- Le choix de la zone de Four Seasons (Europe chez Cloudflare, ou Suisse quand elle existera).
