# 01. Le concept

## Le problème

Une bonne part du temps passé devant un ordinateur ne demande ni talent ni envie : répondre aux mails qui attendent, caler des rendez-vous, relancer, remplir des formulaires, télécharger et ranger des factures, comparer des offres, résilier un abonnement, suivre un remboursement, déclarer, payer, classer. Ce sont des tâches **personnelles** (elles demandent de savoir qui on est, ce qu'on veut, comment on parle) et **éparpillées** (dix sites, trois boîtes mail, des portails sans API).

Les assistants actuels répondent à des questions. Ils ne connaissent pas assez la personne pour agir à sa place, et ils n'ont pas les mains dans ses comptes.

## La promesse

Un clone qui :

1. **vous connaît** : votre vie, vos proches, vos comptes, vos règles, vos habitudes ;
2. **vous ressemble** : il écrit comme vous, tranche comme vous le feriez, et plus tard parle avec votre voix ;
3. **fait le travail** : dans vos propres comptes, sur vos propres sites, et vous rend compte ;
4. **reste à vous** : vous réglez ce qu'il fait seul, vous voyez tout, vous pouvez tout arrêter et tout effacer.

## Pour qui (grand public, décision de Thomas)

Toute personne majeure qui passe du temps sur des tâches numériques qu'elle n'aime pas. Les premiers à viser, parce que la douleur est forte et le gain visible tout de suite :

| Profil | Ce qui pèse | Ce que le clone fait d'abord |
|---|---|---|
| Indépendant, freelance, artisan | mails clients, devis, relances, factures, administratif | répondre aux demandes, relancer les impayés, ranger les factures |
| Parent actif | école, activités, santé, rendez-vous, papiers de la famille | agenda familial, inscriptions, formulaires, rappels |
| Cadre débordé | boîte mail, agenda, notes de frais, suivi | tri et réponses, calage de réunions, notes de frais |
| Senior peu à l'aise avec le numérique | portails administratifs, banque, santé | démarches en ligne, explications, rappels |
| Personne qui déménage, change de travail, se marie | dizaines de démarches à la suite | changements d'adresse, résiliations, ouvertures de comptes |

**Hors cible au lancement** : les mineurs, et les usages professionnels réglementés où le clone engagerait un secret professionnel (médecin, avocat) ; ils viendront avec une offre et des garde-fous à part.

**Le pont avec l'existant** : un indépendant qui a déjà un agent MEGGA pour ses clients (WhatsApp) peut y ajouter son clone. Ce sont deux agents distincts, l'un face à ses clients, l'autre à son service.

## Les missions de la première version

Rangées par domaine. Chaque mission a un genre d'action (lire, préparer, agir chez soi, envoyer à un tiers, engager), qui détermine ce que le curseur d'autonomie permet (voir [05-actions.md](05-actions.md)).

| Domaine | Missions v1 | Par où |
|---|---|---|
| Mails | trier, résumer, répondre comme vous, relancer, se désabonner | Gmail, Outlook (connecteurs) |
| Agenda | proposer des créneaux, accepter ou décliner, déplacer, préparer un rendez-vous | Google Agenda, Outlook (connecteurs) |
| Administratif | télécharger et ranger factures et relevés, remplir un formulaire, suivre un dossier | navigateur (C6), Drive ou Dropbox (connecteurs) |
| Achats et abonnements | comparer, suivre une commande, retourner un article, résilier | navigateur (C6) |
| Messages | répondre sur WhatsApp ou Telegram comme vous, dans les limites fixées | WhatsApp (déjà dans le noyau), autres plus tard |
| Mémoire | « rappelle-moi », « retrouve le mail où... », « qu'avait dit ma banque ? » | modèle de soi |
| Briefing | le point du matin et du soir : ce qui a été fait, ce qui attend, ce qui arrive | app, WhatsApp, vocal |

Plus tard : appels téléphoniques avec la voix clonée (C7), logiciels de l'ordinateur (C8), visios avec l'avatar (C9).

## Une journée avec son clone

- **7 h 30**, le point du matin, en vocal sur WhatsApp : « Trois mails ont besoin de toi, j'ai répondu à huit autres. Ta facture d'électricité est arrivée, je l'ai rangée. Le plombier propose jeudi 10 h ou vendredi 14 h ; je lui dis jeudi ? »
- **Dans la journée**, l'app montre la file « À valider » : deux réponses à relire, un formulaire de mutuelle prêt à partir. Un geste pour chaque.
- **Le soir**, le titulaire dicte : « Résilie mon abonnement à la salle de sport, et à partir de maintenant, refuse poliment toutes les sollicitations commerciales sans me demander. » Le clone le fait, et retient la nouvelle règle.
- **Chaque semaine**, il pose deux ou trois questions pour mieux le connaître (« Tu as répondu en tutoyant Marc, je le note comme proche ? »).

## Les canaux

| Canal | Pour quoi | Existant |
|---|---|---|
| L'app (la console devenue l'app Clone) | onboarding, portrait, « À valider », journal, réglages | console Next.js, CopilotKit, AG-UI ([spec 8.1](../superpowers/specs/2026-11-17-console-socle-design.md)) |
| WhatsApp | parler à son clone, valider, recevoir le point du jour | noyau WhatsApp, vocaux, voix |
| Vocal | dicter, écouter le point du jour | ElevenLabs (écoute et voix) |
| Notifications | « 2 actions à valider » | à ajouter (web push, puis app mobile) |
| App mobile | plus tard, si l'usage le demande | aucun |

Le titulaire parle à son clone par l'app ou par WhatsApp. Les tiers, eux, ne parlent jamais « au clone » directement en v1 : ils reçoivent des mails et des messages envoyés depuis les comptes du titulaire.

## La concurrence (à vérifier par une vraie veille avant C1)

Ce qui existe déjà, d'après ce qu'on sait au 21.11.2026 :

- **Les clones qui parlent** : des services qui créent un double conversationnel d'une personne, entraîné sur ses contenus, pour répondre à sa place (souvent pour des créateurs ou des experts). Ils parlent comme la personne, mais n'agissent pas dans ses comptes.
- **Les agents qui agissent** : les agents navigateur et « computer use » des grands laboratoires, et des assistants d'automatisation branchés sur des centaines d'applications. Ils agissent, mais ne connaissent pas la personne et n'écrivent pas comme elle.
- **Les assistants de messagerie** : rédaction de mails « dans votre style ». Un seul canal, peu d'action.

**Notre angle** : la combinaison des trois (connaître, ressembler, agir), un onboarding qui tient en une conversation, l'autonomie réglée par la personne, et la souveraineté des données de MEGGA (zones Suisse, Europe, États-Unis, déjà en place). Le dossier ne prétend pas que rien de proche n'existe : la veille dira où est la vraie différence.

## Le nom

« Clone Agent » reste le nom du projet dans le dépôt et dans le code (`clone`). Pour la marque publique, à tester auprès de vrais utilisateurs :

| Piste | Pour | Contre |
|---|---|---|
| **Clone** (« Mon Clone », « MEGGA Clone ») | dit exactement la promesse, colle au pitch | peut inquiéter (usurpation, science-fiction) |
| **Double** (« votre double numérique ») | élégant en français, rassurant | moins clair à l'international |
| **Twin** (« MEGGA Twin ») | international, évoque le jumeau numérique | déjà très employé dans l'industrie |

Recommandation : garder « Clone » dans le pitch (il porte l'effet), et tester « Double » et « Twin » comme nom de produit.

## Le modèle économique (hypothèses à valider)

- **Abonnement mensuel** avec un volume de missions inclus, et des recharges (le mécanisme existe déjà avec Stripe : forfaits, enveloppe, recharge sous un seuil).
- **L'unité vendue** n'est plus la conversation (les agents d'entreprise) mais l'**action** ou la **mission** : un mail traité, un formulaire rempli, une démarche menée.
- **Un essai gratuit** court, qui doit montrer le premier service rendu dans les 20 premières minutes.
- **Des options payantes** : voix clonée, avatar, zone Suisse, app sur l'ordinateur.
- **Ce qui coûte** : les modèles (beaucoup de lecture pendant l'ingestion, puis chaque tour), le navigateur dans le cloud (minutes de session), la voix et l'avatar. Le coût par mission se mesure dès C4, avant de fixer un prix ; la règle de Julien (le prix vise trois fois notre coût) reste le repère.

## Comment on saura que ça marche

| Mesure | Pourquoi |
|---|---|
| Temps jusqu'au premier service rendu | l'onboarding doit être une conversation, pas un formulaire |
| Part des brouillons envoyés sans retouche | c'est la mesure de la ressemblance |
| Distance moyenne entre le brouillon et ce qui part | baisse semaine après semaine si l'apprentissage marche |
| Part des domaines passés en « agir seul » | c'est la mesure de la confiance |
| Heures rendues par semaine (estimées par mission) | c'est la promesse vendue |
| Rétention à 30 et 90 jours | un clone qui ne sert pas est abandonné vite |
| Incidents : action hors permission, fuite, injection réussie | doivent rester à zéro |
