# 06. La ressemblance : écrire, parler, apparaître comme la personne

Décision de Thomas : la ressemblance est complète, dans cet ordre. D'abord l'écriture et les décisions (le cœur), puis la voix, puis l'avatar vidéo. Chaque étape a son propre consentement.

## 1. Écrire et décider comme la personne (C3, C5)

C'est ce qui fait le produit au quotidien. Le détail est dans [04-modele-de-soi.md](04-modele-de-soi.md) ; en bref :

- **Le style par contexte** : la même personne n'écrit pas pareil à son banquier, à un client et à sa sœur. Le clone choisit le style d'après le destinataire (sa fiche dans le modèle de soi), la langue et le canal.
- **Des exemples plutôt que des descriptions** : 3 à 5 vrais extraits du titulaire, proches de la situation, dans le contexte du tour.
- **Les décisions apprises** : accepter, refuser, relancer, déléguer, ignorer, d'après ce qu'il a fait avant et ce qu'il a corrigé.
- **Ce qu'il ne sait pas, il le demande** : un clone qui invente une préférence se trompe en public. Dans le doute, il propose au lieu d'agir.
- **La typographie** : le noyau a déjà un point d'envoi qui nettoie et remplace (`noyau/typographie.py`, `remplacements`). Le clone y ajoute les tics du titulaire (ses formules, ses emojis, ses fautes volontaires s'il en a), et y retire ce qu'il n'écrit jamais.

**Ce qu'on vise** : après un mois, la majorité des brouillons partent sans retouche, et le titulaire ne gagne plus au jeu « Qui a écrit ça ? ».

## 2. La voix clonée (C7)

La plateforme a déjà la voix (ElevenLabs : écoute, voix par langue, réécriture pour l'oral, `noyau/voix.py`, `noyau/oral.py`). Le clone y ajoute **la voix du titulaire**.

**Pour quoi faire** :
- le point du jour, dit avec sa propre voix (ou une voix neutre, au choix) ;
- des vocaux envoyés à ses proches sur WhatsApp, quand il l'a permis ;
- plus tard, des appels téléphoniques simples : prendre ou déplacer un rendez-vous, suivre une commande, appeler un service client (avec un fournisseur de téléphonie, à choisir).

**Le consentement, prouvé** :
1. Le titulaire enregistre sa voix dans l'app (quelques minutes de lecture), **en direct**, pas en téléversant un fichier : un fichier pourrait être la voix d'un autre.
2. Il lit à voix haute une phrase de vérification tirée au hasard ; le service de voix vérifie que la voix qui lit est celle qui est clonée (les offres de clonage professionnel d'ElevenLabs ont une vérification de ce genre : à confirmer en C7).
3. Le consentement est gardé, daté, avec l'empreinte de l'enregistrement ; il se retire d'un geste, et la voix est alors supprimée chez le fournisseur.
4. La voix n'appartient qu'à ce titulaire et ne sert qu'à son clone.

**La transparence** :
- Un appel avec la voix clonée **commence toujours** par dire que c'est l'assistant IA de la personne (« Bonjour, je suis l'assistant de Camille Martin, une IA, j'appelle pour... »). Ce n'est pas réglable : voir [07-securite-conformite.md](07-securite-conformite.md).
- Un vocal envoyé à un proche porte la mention qu'il est généré, sauf si ce proche l'a accepté une fois pour toutes (à valider par le juriste).
- Les fichiers audio générés portent un marquage lisible par machine quand le fournisseur le permet.

**Ce que la voix ne fera jamais** : s'identifier comme le titulaire auprès d'une banque, d'une administration ou de tout service qui reconnaît la voix ; passer un appel d'urgence ; appeler une personne qui a dit ne pas vouloir parler à une IA.

## 3. L'avatar vidéo (C9)

Le plus spectaculaire, et le plus sensible. En dernier, quand l'écriture et la voix ont fait leurs preuves.

**Pour quoi faire** :
- des messages vidéo courts (une réponse à un client, un mot à la famille, une présentation) ;
- plus tard, une présence en visio pour des réunions simples (prendre des notes, répondre à des questions factuelles), toujours annoncée.

**Le consentement, prouvé** : comme la voix, en plus fort. Une vidéo enregistrée en direct dans l'app, avec un contrôle de présence (bouger la tête, lire un code), une vérification que le visage est celui du titulaire du compte (pièce d'identité, à décider avec le juriste), et un consentement écrit, daté, retirable.

**La transparence** : toute vidéo générée est marquée comme telle, visiblement et dans le fichier (norme de provenance du contenu, quand le fournisseur la sait poser). Dans une visio, l'avatar se présente comme un assistant IA au début, et son nom affiché le dit.

**Le fournisseur** : plusieurs services d'avatars vidéo existent ; le choix se fait en C9 sur la qualité, la zone de traitement, la vérification du consentement qu'ils imposent eux mêmes, et le coût. Aucun fournisseur qui garde ou réutilise les visages pour entraîner ses modèles.

## Le portrait vivant

Dans l'app, le clone a un visage : la mascotte de la console (couleur, yeux, déjà dessinée), puis, si le titulaire le veut, son propre avatar. Le portrait du modèle de soi et ce visage se retrouvent sur la même page : « voici qui je suis, voici comment je parle, voici ce que je fais pour vous ».

## Questions pour Julien

1. La voix sur les appels téléphoniques : dans C7, ou plus tard (téléphonie, numéros, coûts) ?
2. L'avatar : vérification d'identité par pièce d'identité, ou seulement le contrôle de présence ?
3. Le point du jour avec la propre voix du titulaire : le proposer par défaut une fois la voix créée, ou garder une voix neutre ?
