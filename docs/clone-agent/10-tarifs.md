# 10. Les tarifs

Demande de Thomas (21.11.2026) : quatre offres, **Free, Plus (20), Pro (100), Ultra (200)**, plus une offre **Local (5 par mois)** pour qui fait tourner son clone sur sa propre machine. Chaque abonnement couvre ce que coûte son clone dans le cloud ; la grille doit être rentable pour MEGGA, attirante pour le client et réaliste aux prix d'aujourd'hui.

Tout ce qui suit est calculé, pas deviné : les prix unitaires sont sourcés ou marqués comme hypothèses, et le calcul se refait dès que les vrais coûts sortent du relevé chiffré (C1 à C4).

## L'idée qui protège la marge : le crédit

Le titulaire ne voit qu'une **jauge de crédits** par mois. **Un crédit, c'est environ 2 centimes de coût pour MEGGA**, et il se vend 5 centimes (dans un forfait comme en recharge). Chaque chose que fait le clone consomme des crédits selon ce qu'elle coûte vraiment :

| Ce que fait le clone | Crédits | Coût estimé pour MEGGA |
|---|---|---|
| Une tâche (répondre à un mail, caler un rendez-vous, retrouver une information, remplir un formulaire par un connecteur) | 1 | 0,02 $ en moyenne (voir plus bas) |
| Une tâche qui demande une réflexion approfondie (Opus) | 5 | environ 0,10 $ |
| Une tâche sur un site sans API (navigateur dans le cloud) | 6 | environ 0,12 $ en moyenne (0,25 $ la première fois, 0,05 $ avec une recette) |
| Une minute de vocal dit par le clone | 4 | environ 0,08 $ |
| Une minute d'appel téléphonique | 6 | environ 0,12 $ (hypothèse) |
| Une minute de vidéo de l'avatar | 50 | environ 1 $ (hypothèse) |
| Trier un mail, le point du jour, la consolidation de nuit, la mémoire | 0 | compris, avec un plafond raisonnable par offre |

**Pourquoi c'est solide** : si une tâche coûte plus cher que prévu, on change son poids en crédits, pas le prix des offres. La marge est tenue par construction ; ce qui peut bouger, c'est le nombre de tâches qu'un crédit achète, et c'est ce que la ressemblance et le routage des modèles doivent améliorer avec le temps. Le mécanisme existe déjà dans l'atelier pour les agents d'entreprise (forfaits, enveloppe du mois, recharge sous un seuil, Stripe) : l'unité passe de la conversation au crédit.

## La grille

Les mêmes chiffres dans les trois devises : **dollars hors taxes** aux États-Unis, **euros TTC** en Europe, **francs suisses TTC** en Suisse (le grand public attend un prix TTC en Europe et en Suisse). Paiement sur le web seulement (Stripe) : pas d'achat dans les magasins d'applications, qui prennent 15 à 30 %.

| | **Free** | **Plus** | **Pro** | **Ultra** | **Local** |
|---|---|---|---|---|---|
| Prix par mois | 0 | 20 | 100 | 200 | 5 (ou 48 par an) |
| À l'année | | 200 (deux mois offerts) | 1 000 | 2 000 | 48 |
| Crédits par mois | 25 | 400 | 2 000 | 4 500 | sans limite : la machine du client paie |
| Ça représente | une tâche par jour | environ 13 tâches par jour, ou 250 tâches, 10 démarches sur des sites et 15 minutes de vocaux | le travail courant d'un indépendant | presque tout déléguer | tout, à son rythme |
| Mails triés par mois | 300 | 2 000 | 6 000 | 10 000 | sans limite |
| Comptes branchés | 1 boîte mail, 1 agenda | tous ceux du catalogue | tous | tous | tous |
| Historique lu à l'onboarding | 3 mois, 500 mails | 12 mois | complet | complet | complet |
| Portrait, mémoire, règles, « À valider », journal, export, oubli | oui | oui | oui | oui | oui |
| Autonomie réglable par domaine | oui | oui | oui | oui | oui |
| Point du jour | dans l'app | app et WhatsApp | app, WhatsApp, vocal avec sa voix | idem | app |
| Navigateur dans le cloud (C6) | non | oui | oui, prioritaire | oui, tâches en parallèle | navigateur de la machine |
| Vocaux | non | voix neutre | sa voix clonée (C7) | sa voix clonée | clé ElevenLabs du client |
| Appels téléphoniques (C7) | non | non | oui | oui | non |
| App sur l'ordinateur (C8) | non | non | oui | oui | c'est l'offre |
| Réflexion approfondie (Opus) | non | non | oui | oui | selon son modèle |
| Avatar vidéo (C9) | non | non | non | oui | non |
| Deux clones séparés (pro et perso) | non | non | non | oui | non |
| Zone Suisse | non | non | oui | oui | sans objet : tout reste chez lui |
| Recharges | non | 100 crédits pour 5 | idem | idem | non |
| Support | aide en ligne | courriel | prioritaire | dédié | aide en ligne |

Les droits du RGPD et de la nLPD (voir, corriger, exporter, effacer) sont dans **toutes** les offres, gratuite comprise : ce n'est pas une option.

## Ce que coûte un clone : les prix unitaires

| Poste | Prix retenu | Source ou hypothèse |
|---|---|---|
| Claude Haiku 5.5 | 0,10 $ en entrée, 0,50 $ en sortie, par million de jetons | prix d'Anthropic, relevé le 03.11.2026 |
| Claude Sonnet 5.5 | 2 $ / 10 $ ; lecture du cache 0,10 $ | idem |
| Claude Opus 5.5 | 4 $ / 20 $ ; lecture du cache 0,20 $ | idem |
| Batch (ingestion, consolidation) | moitié prix | idem |
| Voix ElevenLabs | 0,05 $ (Flash) à 0,10 $ (v3, multilingue) pour 1 000 caractères ; une minute dite fait environ 900 caractères | page de prix et guides de 2026, à confirmer sur [la page officielle](https://elevenlabs.io/pricing/api) |
| WhatsApp, message de modèle « utilitaire » (le point du jour) | 0,03 $ en France ; payant même dans la fenêtre de 24 h depuis le 01.10.2026 | tableaux tiers d'octobre 2026, à confirmer sur [la grille de Meta](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing) |
| Composio | 4 $ pour 1 000 appels au-delà du forfait (3 $ par Sessions) ; forfait Pro à 29 $ pour 50 000 appels | changement de prix d'août 2026, à confirmer sur [composio.dev/pricing](https://composio.dev/pricing) |
| Transcription d'un vocal reçu | environ 0,01 $ la minute | hypothèse |
| Appel téléphonique (voix et ligne) | environ 0,12 $ la minute | hypothèse, à chiffrer en C7 |
| Avatar vidéo | environ 1 $ la minute | hypothèse, à chiffrer en C9 |
| Infrastructure (calcul, base, fichiers, clés) | environ 0,10 $ par titulaire et par mois | [09-infrastructure.md](09-infrastructure.md) |
| Paiement | environ 3 % plus 0,30 $ par prélèvement | ordre de grandeur Stripe, cartes européennes moins chères |
| TVA | 20 % pris comme cas défavorable pour l'Europe (8,1 % en Suisse) | |

### Le coût d'une tâche : 0,02 $ en moyenne, à une condition

Une tâche, c'est en général trois appels au modèle (lire, décider, agir et vérifier). Avec le portrait et les règles en cache :

| Modèle | Une tâche | Part visée |
|---|---|---|
| Haiku 5.5 (trier, résumer, réponses simples, extraction) | environ 0,003 $ | 70 % |
| Sonnet 5.5 (rédiger comme le titulaire, agir avec des outils) | environ 0,05 $ | 28 % |
| Opus 5.5 (décisions difficiles, compté à part : 5 crédits) | environ 0,10 $ | 2 % |
| **Moyenne** | **environ 0,018 $** | |

**La condition** : un routage qui envoie à Haiku tout ce qu'il fait aussi bien. Haiku 5.5 coûte vingt fois moins que Sonnet 5.5 ; c'est la décision d'architecture qui pèse le plus sur la rentabilité. Le jeu « Qui a écrit ça ? » et les mesures de ressemblance (C3, C5) diront quelles tâches Haiku tient sans que le titulaire voie la différence. Si la part de Haiku tombe à 40 %, une tâche coûte environ 0,03 $ : on passe la tâche à 1,5 crédit, et la marge ne bouge pas.

### Ce qui change dans l'architecture à cause des prix

1. **Gmail, Google Agenda et Outlook en direct, pas par Composio.** Ce sont les connecteurs qui servent le plus (des milliers d'appels par titulaire et par mois) : à 4 $ les 1 000 appels, ils coûteraient plusieurs dollars par mois à chaque titulaire. On les écrit nous-mêmes (API Gmail avec notifications push, Microsoft Graph), ce qui demande de toute façon la validation de sécurité de Google (07). Composio reste pour la longue traîne, avec un plafond d'appels par offre. À ajouter au lot C4.
2. **Le batch pour tout ce qui peut attendre** : ingestion, consolidation de nuit, choix des exemples de style (moitié prix).
3. **Le point du jour dans l'app d'abord** : sur WhatsApp, il coûte 0,03 $ par jour et par titulaire (0,90 $ par mois), d'où sa place à partir de Plus.
4. **La voix Flash par défaut** pour les vocaux du quotidien, la voix la plus fidèle pour les messages qui comptent.

## La rentabilité, offre par offre

« Plafond » : le titulaire qui consomme tous ses crédits et tous ses mails triés. « Typique » : 40 % des crédits, ce qui est l'usage courant des abonnements grand public (beaucoup paient plus qu'ils ne consomment). Le revenu net, c'est le prix moins la TVA (en Europe) et les frais de paiement.

| Offre | Coût fixe (tri, consolidation, WhatsApp, infra, point du jour) | Coût au plafond | Coût typique | Revenu net Europe (TTC) | Revenu net États-Unis (HT) | Coût au plafond / revenu (Europe) | Marge brute typique (Europe) |
|---|---|---|---|---|---|---|---|
| Free | 0,27 $ | 0,77 $ | 0,42 $ | 0 | 0 | | |
| Plus | 2,03 $ | 10,03 $ | 4,82 $ | 15,87 $ | 19,10 $ | 63 % | **70 %** |
| Pro | 6,65 $ | 46,65 $ | 21,32 $ | 80,53 $ | 96,70 $ | 58 % | **74 %** |
| Ultra | 8,70 $ | 98,70 $ | 42,96 $ | 161,37 $ | 193,70 $ | 61 % | **73 %** |
| Local | environ 0,50 $ (relais, longue traîne Composio, sauvegarde) | 0,55 $ | 0,30 $ | 3,74 $ par mois (3,21 $ par mois en annuel) | | 15 % | **environ 90 %** |

**Même un titulaire qui consomme tout laisse une marge** (37 à 42 % en Europe, davantage aux États-Unis). L'abonnement annuel (deux mois offerts) réduit le revenu net d'environ 17 % : le titulaire au plafond reste au-dessus de son coût, et l'usage typique garde une marge d'environ 60 %.

### L'offre gratuite se paie par la conversion

Un gratuit coûte environ 0,25 $ par mois en moyenne (beaucoup sont peu actifs ; 0,77 $ au plus). Pour une clientèle payante faite à 80 % de Plus, 15 % de Pro et 5 % d'Ultra :

| Part des gratuits qui deviennent payants | Revenu net par payant | Coût des payants | Coût des gratuits, par payant | Marge brute | Contribution par payant et par mois |
|---|---|---|---|---|---|
| 3 % | 32,84 $ | 9,21 $ | 8,08 $ | 47 % | 15,55 $ |
| 5 % | 32,84 $ | 9,21 $ | 4,75 $ | 58 % | 18,89 $ |
| 10 % | 32,84 $ | 9,21 $ | 2,25 $ | 65 % | 21,39 $ |

C'est réaliste pour un produit d'IA grand public, à condition de tenir l'offre gratuite serrée :
- une offre gratuite par personne (téléphone vérifié, double authentification) ;
- un clone gratuit inactif depuis 30 jours s'endort (plus de tri, plus de point du jour) ; ses données restent, puis sont effacées après 12 mois d'inactivité, avec un avertissement avant ;
- les tâches gratuites passent d'abord par Haiku ;
- pas de navigateur, pas de voix, pas de WhatsApp sortant.

### Les coûts fixes à couvrir (hors titulaires)

Ce que la marge doit payer avant d'être un bénéfice : l'équipe, le support, la validation de sécurité annuelle de Google pour Gmail, le juriste et l'AIPD, le test d'intrusion, la zone Suisse chez Exoscale (environ 263 € par mois au départ, dans le plan), les forfaits de base des fournisseurs (Composio, ElevenLabs), le programme de signalement des failles. **Le seuil de rentabilité, c'est les coûts fixes du mois divisés par la contribution d'un payant** : par exemple, 50 000 $ de coûts fixes par mois demandent environ 2 600 payants à 5 % de conversion (exemple, pas une estimation des coûts fixes).

## Pourquoi c'est attirant pour le client

- **Le marché a fixé les repères** : les grands assistants d'IA grand public sont à 20 par mois, et leurs offres intensives entre 100 et 200. Clone Agent s'y place exactement, mais il **fait** le travail au lieu d'en parler.
- **Le calcul pour le client est simple** : 400 crédits, c'est environ 13 tâches par jour. À 5 minutes gagnées par tâche, c'est plus d'une heure rendue chaque jour pour 20 par mois.
- **La gratuité montre la magie** : le premier service rendu (03, l'onboarding) et le jeu « Qui a écrit ça ? » sont dans l'offre gratuite. On paie quand on veut que le clone en fasse plus.
- **Pas de mauvaise surprise** : la jauge se voit dans l'app, le clone prévient à 80 %, rien ne se recharge sans un seuil choisi par le titulaire.
- **Local pour les plus attachés à leurs données** : rien ne quitte leur machine, pour le prix d'un café par mois.

## Le calendrier des offres

Les offres suivent les lots : on ne vend pas ce qui n'existe pas.

| Moment | Offres ouvertes |
|---|---|
| Version publique 1 (après C5) | Free et Plus (sans navigateur ni voix) ; Plus à 20 avec 400 crédits sur les mails, l'agenda et les connecteurs |
| Après C6 (navigateur) | Pro, d'abord avec Opus, le navigateur prioritaire et 2 000 crédits |
| Après C7 (voix) | la voix clonée et les appels entrent dans Pro et Ultra ; Ultra ouvre |
| Après C8 (app ordinateur) | Local |
| Après C9 (avatar) | l'avatar dans Ultra |

Un titulaire déjà abonné garde son prix quand l'offre s'enrichit.

## L'offre Local : le clone sur sa propre machine

### Ce qui tourne où

| Chez le titulaire | Chez MEGGA (ce que paient les 5) |
|---|---|
| le noyau du clone (la même image, en mode local) | l'app signée et ses mises à jour |
| le modèle de soi, en SQLite chiffré (les tests du dépôt tournent déjà sur SQLite) | le relais, toujours sortant comme le pilote : l'app mobile et WhatsApp entrant parlent au clone sans ouvrir aucun port chez lui |
| le coffre et les sessions de sites | les connecteurs directs (Gmail, Agenda, Outlook) : le titulaire se connecte par l'app de MEGGA, ses jetons restent chez lui |
| le navigateur (celui de la machine : mêmes sessions, même adresse, moins de blocages par les sites) | la longue traîne Composio, 100 appels par mois |
| le modèle : sa propre clé (Anthropic, ElevenLabs), ou un modèle ouvert sur sa machine, ou les deux | les recettes communes des sites, sans donnée personnelle |
| | une sauvegarde chiffrée de son modèle de soi (1 Go), s'il la veut, chiffrée par une clé que MEGGA n'a pas |

**Ce qu'il faut dire clairement au titulaire** : son clone ne travaille que quand sa machine est allumée ; avec sa propre clé, il paie aussi le modèle à Anthropic (de l'ordre de quelques dollars par mois pour un usage courant) ; avec un modèle ouvert, rien ne sort de chez lui, mais l'écriture et les actions sont moins fines qu'avec Claude.

### Trois façons de faire tourner le modèle

| Mode | Le modèle | Pour qui |
|---|---|---|
| **Local avec clé** | Claude, avec la clé du titulaire | toute machine récente ; la meilleure qualité |
| **Hybride** (recommandé) | un petit modèle ouvert sur la machine pour trier, résumer et extraire (ce qui touche le plus de données) ; Claude avec sa clé pour rédiger et agir | machines de la classe « Entrée » et au-dessus |
| **Tout local** | un modèle ouvert sur la machine pour tout | classes « Confort » et « Haut de gamme » ; pour ceux qui ne veulent rien envoyer dehors |

### Les machines assez puissantes

Les modèles ouverts changent tous les trimestres : la liste des modèles est à revalider au début de C8. Les tailles de mémoire, elles, tiennent : c'est la mémoire (vidéo ou unifiée) qui décide de ce qu'une machine peut faire tourner. Repères actuels : les familles gpt-oss (20 et 120 milliards de paramètres, licence Apache 2.0), Qwen3 (dont 30B-A3B et ses variantes qui voient les images) et Mistral Small (24B).

**Pour le noyau seul (mode « Local avec clé »)** : processeur 4 cœurs ou plus des cinq dernières années, **8 Go de mémoire (16 Go recommandés)**, 20 Go de disque libre, macOS 14 ou plus récent, Windows 11, ou Linux (Ubuntu 22.04 ou plus récent). Presque tout ordinateur portable ou de bureau récent convient, ainsi qu'un mini-PC toujours allumé (par exemple les petits PC à processeur Intel N100 et 16 Go) ou un NAS capable de faire tourner Docker avec 8 Go. Un Raspberry Pi 5 de 8 Go fait tourner le noyau et le navigateur, lentement : à réserver aux bricoleurs.

**Pour un modèle sur la machine** :

| Classe | Ce qu'elle fait tourner | Mac (Apple Silicon) | PC avec carte graphique | Autres |
|---|---|---|---|---|
| **Insuffisante** | un petit modèle (7 à 8 milliards de paramètres), bon pour trier, pas pour agir | Mac de 8 ou 16 Go | cartes de 8 à 12 Go, ou pas de carte graphique dédiée | Chromebook, tablettes : mode « Local avec clé » seulement |
| **Entrée** (hybride confortable, tout local possible) | un modèle de 20 à 30 milliards de paramètres, compressé en 4 bits (environ 14 à 20 Go) | **32 Go de mémoire unifiée** : MacBook Pro M1 Pro ou Max et suivants, MacBook Air M4 32 Go, Mac mini M4 32 Go ou M4 Pro | **carte de 16 Go** avec 32 Go de mémoire : RTX 4060 Ti 16 Go, 4070 Ti Super, 4080, 5060 Ti 16 Go, 5070 Ti, 5080 ; Radeon RX 7900 XT ou XTX (prise en charge moins mûre) | |
| **Confort** (tout local, contexte long, vision) | les mêmes modèles plus vite, avec plus de contexte, et les variantes qui lisent les écrans | **48 à 64 Go** : Mac mini M4 Pro 48 ou 64 Go, MacBook Pro M3 ou M4 Max 64 Go, Mac Studio | **carte de 24 à 32 Go** : RTX 3090, 4090, 5090 | |
| **Haut de gamme** (proche du cloud) | des modèles d'environ 100 milliards de paramètres et plus (par exemple gpt-oss 120B, environ 65 Go) | **96 à 128 Go et plus** : MacBook Pro M4 Max 128 Go, Mac Studio (Max ou Ultra) | plusieurs cartes, ou une carte de 80 Go | AMD Ryzen AI Max+ 395 avec 128 Go (Framework Desktop, HP Z2 Mini G1a) ; NVIDIA DGX Spark (128 Go) |

**La machine qu'on recommandera** pour le « tout local » : un **Mac mini M4 Pro de 48 ou 64 Go**. Silencieux, sobre, fait pour rester allumé, dans la classe « Confort ». Pour l'hybride, n'importe quel Mac de 32 Go ou PC avec une carte de 16 Go suffit.

L'app vérifie la machine à l'installation (mémoire, carte graphique, place libre), propose le mode qui lui convient, et mesure la vitesse réelle avant de recommander le tout local.

## Questions pour Julien

1. Le crédit vendu 5 centimes pour un coût visé de 2 centimes (2,5 fois) : d'accord, ou s'en tenir à la règle des trois fois (6 centimes, soit moins de crédits par offre) ?
2. Les prix en euros et en francs suisses TTC égaux aux prix en dollars hors taxes : d'accord (plus simple, moins de marge en Europe) ?
3. Ouvrir Pro dès le navigateur (C6), avant la voix (C7) ?
4. Écrire nous-mêmes les connecteurs Gmail, Agenda et Outlook (C4), plutôt que les payer à l'appel chez Composio ?
5. L'offre Local : avec ou sans la sauvegarde chiffrée chez MEGGA ?
