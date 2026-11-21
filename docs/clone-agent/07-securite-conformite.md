# 07. Sécurité, données et conformité

Un clone a les clés de la vie numérique de quelqu'un. Une faille ne coûte pas une réponse ratée : elle peut vider un compte, envoyer un document d'identité au mauvais destinataire, ou faire parler quelqu'un à sa place. Ce fichier liste les risques et ce qu'on y oppose. **Rien ici n'est un avis juridique** : un juriste doit relire les points marqués avant C4 (le clone agit) et avant C7 (la voix).

## Les risques, par ordre de gravité

| Risque | Ce qu'on y oppose | Où |
|---|---|---|
| Une instruction cachée dans un mail ou une page fait agir le clone | contenus balisés comme données, contrôle de cohérence séparé, sorties bornées, banc d'attaques à chaque PR | 05 |
| Un titulaire voit les données d'un autre | sécurité par ligne, chiffrement par titulaire, tests d'isolation, revue de chaque requête du stockage | 02 |
| Le clone engage le titulaire au delà de ce qu'il a permis | curseur d'autonomie, règles dures, plancher proposé, première fois toujours proposée | 05 |
| Une voix ou un visage cloné sans consentement | enregistrement en direct, vérification, consentement prouvé et retirable | 06 |
| Un compte MEGGA est volé et sert à prendre la main sur des clones | aucun accès de MEGGA aux contenus ; actions d'administration journalisées, à deux personnes pour couper un clone ; clés de zone dans un coffre | 02 |
| Le compte du titulaire est volé | double authentification obligatoire avant de brancher un compte ou de passer un domaine en « agir » ; alerte à chaque nouvel appareil | C1 |
| Une session de site (cookie) fuit du coffre | chiffrée par titulaire, jamais vue par le modèle, durée courte, révocable depuis l'app | 05 |
| Le clone hallucine un fait et agit dessus | un fait incertain ne sert jamais à agir ; une action n'est dite faite que confirmée par le service | 04, 05 |
| Les coûts explosent (ingestion, boucle d'un agent) | plafonds par titulaire (le `Plafond` du noyau, étendu), 25 outils par tour au plus (déjà là), alertes de coût | 02 |

## Les données

**Ce qu'on traite** : les données du titulaire, et celles des **tiers** qui apparaissent dans ses mails, son agenda et ses documents. Les secondes sont le point le plus délicat.

| Principe | En pratique |
|---|---|
| Minimisation | on extrait ce qui sert ; les textes bruts chiffrés ne sont gardés que le temps de l'extraction (proposition : 30 jours), puis seulement les extraits choisis ; les originaux restent chez le fournisseur |
| Finalité | les données ne servent qu'au clone de ce titulaire : jamais à entraîner un modèle, jamais à un autre titulaire, jamais à MEGGA |
| Zone | tout reste dans la zone du titulaire ; les fournisseurs (modèles, voix, navigateur, embeddings) sont vérifiés un par un pour chaque zone, comme le plan le prévoit déjà |
| Données sensibles | santé, finances, opinions, vie sexuelle, données biométriques : marquées, rangées dans leur domaine, jamais utilisées ailleurs |
| Droits | accès (le portrait et l'export), rectification (corriger), effacement (oublier, tout effacer avec un reçu), portabilité (l'export) |
| Sous traitants | liste publique : hébergement, modèles, Composio, voix, navigateur, avatar ; un contrat de traitement avec chacun |
| Pas de lecture par MEGGA | même règle que pour les conversations des agents d'entreprise (décision de Julien, 20.11.2026) : le support ne lit rien sans une demande écrite du titulaire, limitée dans le temps |

**À faire relire par le juriste** :
- le rôle de MEGGA (sous traitant du titulaire, ou responsable de traitement pour le service grand public ?) et la base légale pour traiter les données des tiers contenues dans les mails ;
- l'analyse d'impact (AIPD) : elle sera très probablement nécessaire (traitement à grande échelle, données sensibles possibles, nouvelles technologies) ;
- en Suisse, la nLPD (en vigueur depuis le 1er septembre 2023) ; aux États-Unis, les lois des États (Californie d'abord) et les règles sur les enregistrements d'appels.

## Le règlement européen sur l'IA (AI Act)

Ce qu'on en retient pour le clone, à faire confirmer par le juriste :

- **Les obligations de transparence** (article 50, applicables à partir du 2 août 2026) : une personne qui interagit avec un système d'IA doit en être informée, sauf si c'est évident ; un contenu audio, image ou vidéo généré ou manipulé qui ressemble à une vraie personne (un « hypertrucage ») doit être signalé comme tel ; les contenus générés doivent porter un marquage lisible par machine.
- **Pour le clone, ça veut dire** :
  - **la voix et l'avatar sont toujours signalés** (non réglable : `voix_signalee: true`) ;
  - **un appel ou une visio** commence par dire que c'est l'assistant IA du titulaire ;
  - **les textes** (mails, messages) : c'est la zone grise. Le titulaire envoie depuis son propre compte, et le texte peut avoir été relu par lui. Proposition : un réglage `signature_ia` (aucune, discrète, explicite), « discrète » par défaut (une ligne en bas, « Rédigé avec mon assistant »), et « explicite » imposée pour un envoi autonome à un tiers qui n'a jamais reçu de message du titulaire. **À trancher avec le juriste.**
- **Pas de catégorie interdite** : le clone ne fait ni notation sociale, ni manipulation, ni reconnaissance des émotions au travail. Le jeu « Qui a écrit ça ? » et le style ne tombent pas dans ces catégories, à confirmer.

## Les conditions des services tiers

- **Les connecteurs officiels** (Gmail, Outlook...) : leur usage est prévu. Pour Gmail, l'accès aux mails demande une validation de sécurité de Google pour une app grand public (les accès dits « restreints ») : un délai et un coût à prévoir avant le lancement public, ou passer par Composio si son app validée couvre notre usage (à vérifier).
- **Le navigateur sur des sites sans API** : certains sites interdisent l'automatisation dans leurs conditions. Le clone agit au nom du titulaire, avec ses identifiants et sa session, à un rythme humain, sans contourner une protection (ni CAPTCHA, ni limites) : c'est le choix le plus défendable, mais il faut une liste de sites **interdits** (ceux qui l'excluent clairement, ou où le risque est trop haut : jeux d'argent, courtage) et l'avis du juriste.
- **WhatsApp** : envoyer au nom du titulaire depuis son propre numéro n'est pas ce que l'API Cloud de Meta permet (elle sert un numéro d'entreprise). En v1, WhatsApp sert à **parler à son clone** (le numéro de MEGGA), pas à écrire aux proches à sa place. Écrire à sa place sur WhatsApp, c'est l'app sur l'ordinateur (C8), et seulement si les conditions de Meta le permettent.

## La sécurité du produit

- **Double authentification** obligatoire avant de brancher un compte, de confier un identifiant au coffre ou de passer un domaine en « agir ».
- **Chiffrement** : en transit partout ; au repos par titulaire (clé de données chiffrée par une clé de zone, dans un coffre de clés) ; effacement par destruction de la clé.
- **Secrets** : jamais dans le contexte du modèle ; masqués à la sortie (déjà fait dans le noyau, `secret_masque`).
- **Journal d'audit** : chaque action du clone, chaque changement d'autonomie, chaque accès d'un humain de MEGGA à une donnée de support, gardé et lisible par le titulaire.
- **Tests de sécurité** : banc d'injections à chaque PR, test d'isolation entre titulaires à chaque PR, test d'intrusion commandé à un prestataire avant le lancement public (la règle strictement défensive du catalogue s'applique à nous aussi).
- **Programme de signalement** de failles, avant le lancement public.

## Les mineurs et les personnes vulnérables

- Réservé aux majeurs. Vérification renforcée avant la voix et l'avatar.
- Le clone ne prend aucune décision médicale, juridique ou financière importante seul (les garde-fous santé et juridique du catalogue, lot 11, s'appliquent aux réponses du clone).
- Une personne en détresse : le clone le dit, donne les numéros d'urgence de sa zone (déjà fait pour les agents de santé du catalogue), et ne prend pas le rôle d'un proche.

## Questions pour le juriste (à rassembler avant C4)

1. Rôle de MEGGA et base légale pour les données des tiers.
2. AIPD : périmètre et calendrier.
3. AI Act : transparence des textes envoyés par le clone ; marquage des contenus.
4. Voix et avatar : forme du consentement, vérification d'identité, durée de conservation.
5. Automatisation de sites tiers : liste des sites exclus, clauses des conditions d'utilisation de MEGGA.
6. Responsabilité : qui répond d'une action autonome mal faite (conditions d'utilisation, assurance).
