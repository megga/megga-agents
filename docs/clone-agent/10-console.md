# 10. La console de MEGGA, recentrée

Écrit le 21.11.2026, à la demande de Julien, après lecture du cadrage. Ce fichier dit ce que le clone change pour la console de MEGGA, déjà en service. C'est une proposition : rien n'est construit avant l'accord de Julien.

## Où en est la console

Elle est en ligne sur console.megga.ai, déployée depuis la branche `megga/console-vitesse`. Elle a été pensée pour des dizaines, puis des centaines d'agents d'entreprise.

| Écran | Ce qu'il montre aujourd'hui |
|---|---|
| Vue d'ensemble | la santé de chaque agent (en bonne santé, des soucis, écart de version, en panne, silencieux), tours, personnes et coût par jour, outils, délais de réponse, la carte des clients par pays |
| Analyses | conversations et vocaux par jour, coût par modèle, par client et par conversation |
| Clients | un client par ligne, avec son nom ; sa fiche : suivi, versions, accès, alertes, installation |
| Alertes | les règles à seuils et leurs envois |
| Installations | les installations chez le client, pilotées à distance |
| Clients payants | forfaits, enveloppe de conversations, recharges, Stripe, revenu et marge |
| Tarifs, Comptes, Équipe, Journal | les prix d'achat, les comptes de la console, les rôles, chaque geste de MEGGA |

Ses chiffres viennent du relevé chiffré : chaque agent envoie ses nombres toutes les quinze minutes, jamais un texte, un nom ni un numéro.

## Ce qui ne bouge pas

1. **Des chiffres, jamais de contenu.** C'est déjà la règle de la console (décision de Julien du 20.11.2026) et c'est le principe 2 du cadrage. Aucun écran de MEGGA ne montrera ce qu'un clone lit, écrit ou retient.
2. **Le relevé chiffré** reste la seule source des écrans. Le clone y ajoute des nombres, pas un autre canal.
3. **Les alertes à seuils, le journal, les rôles, Stripe** (forfait, enveloppe, recharge sous un seuil) servent tels quels.
4. **Les agents d'entreprise** gardent leurs écrans : rien ne change pour Four Seasons ni MEGGA Estates.
5. **La base de la console** : mêmes composants, même mise en page. On range autrement, on ne refait pas.

## Ce que le clone change

| Sujet | Aujourd'hui | Avec le clone | Lot |
|---|---|---|---|
| L'échelle | une ligne par client, lue par pages de 50 | des dizaines de milliers de titulaires : des totaux par zone et par cellule, jamais une liste de personnes par défaut | C1 |
| L'identité | le nom de l'entreprise | un identifiant opaque : ni nom, ni courriel, même pour MEGGA | C1 |
| La santé | un conteneur par client : démarré, version, pannes | les pools (conteneurs, tours en cours, marge), la file (taille, retard), les cellules (remplissage), la version de l'image par pool | C1 |
| L'unité vendue | la conversation : une personne servie sur une journée | l'action ou la mission, avec son coût | C4 |
| Les analyses | tours, personnes, jetons, coûts, outils, voix, délais | en plus : actions par domaine et par genre, coût par mission, coût d'ingestion, minutes de navigateur | C3, C4, C6 |
| La ressemblance | rien | part des brouillons envoyés sans retouche, distance entre le brouillon et ce qui part, en nombres | C5 |
| Le produit | rien | temps jusqu'au premier service, part des domaines en « agir », rétention à 30 et 90 jours | C2, C5 |
| Les alertes | par client : silence, panne, écart de version, échecs, plafond, coût, secrets masqués | en plus : pool trop chargé, file en retard, cellule pleine à 70 %, injection détectée, refus de la sécurité par ligne, clé demandée pour un autre titulaire | C1, C4 |
| Les clients payants | MEGGA abonne une entreprise et lui envoie son lien de paiement | le titulaire s'abonne seul : la console suit des cohortes (en essai, payant, parti) et les options (voix, avatar, zone Suisse, app ordinateur) | C1, prix après C4 |
| Les gestes de MEGGA | créer un client, régler l'avancé, reprendre la main, forcer une version | sur un clone, MEGGA ne règle rien et ne lit rien : elle peut seulement le couper, à deux personnes, ou ouvrir un accès de support demandé par écrit et limité dans le temps | C1, C4 |

Les pools, les cellules et leurs alertes sont décrits dans `09-infrastructure.md`, qui n'est pas encore sur `main` (voir plus bas).

## Les écrans, un par un

**Décidé par Julien le 21.11.2026** : la console reste une seule console. En tête de chaque écran, un choix entre deux populations : **Entreprises** et **Clones**. Les entreprises gardent l'affichage d'aujourd'hui.

| Écran | Côté Clones |
|---|---|
| Vue d'ensemble | l'état de chaque pool et de chaque cellule, par zone ; titulaires inscrits, actifs du jour, en essai ; les soucis en cours de la plateforme |
| Analyses | les mêmes courbes, comptées en actions et en missions ; la ressemblance et les mesures du produit |
| Clients | pas de liste : une recherche par identifiant opaque, pour le support. La fiche montre les nombres du titulaire (pour sa facture) et son état, jamais son portrait ni son journal |
| Alertes | les mêmes règles, avec les nouvelles mesures de la plateforme et de la sécurité |
| Clients payants | les cohortes, le revenu et la marge par forfait ; plus de ligne par personne |
| Monde | les titulaires par pays, et les cellules de chaque zone |
| Journal | les gestes de MEGGA sur un clone (coupure, accès de support), que le titulaire lit aussi de son côté |
| Installations, Tarifs, Équipe, Comptes | inchangés |

## Ce qu'il faut dans le moteur avant tout écran

Aucun écran des clones ne peut être honnête avant que ces nombres existent.

- Un relevé chiffré **par pool et par cellule**, à côté du relevé par agent (C1).
- Les nouveaux genres du journal du noyau : `injection_detectee`, actions par domaine et par genre, validations avec ou sans retouche, minutes de navigateur (C4 à C6).
- Une lecture des relevés **en totaux**, sans passer par chaque titulaire : la route d'aujourd'hui rend 50 clients par page.
- Le journal des gestes de MEGGA sur un clone, lisible par le titulaire, et la coupure à deux personnes (C1).

## L'ordre proposé

| Quand | Ce que la console reçoit |
|---|---|
| Avec C1 | le choix Entreprises ou Clones, la santé des pools et des cellules, les totaux de titulaires, les alertes de la plateforme, la recherche par identifiant, la coupure à deux |
| Avec C3 | le coût d'ingestion |
| Avec C4 | les actions par domaine et par genre, le coût par mission, les injections détectées, les forfaits comptés en missions |
| Avec C5 | la ressemblance et la rétention |
| Avec C6 | les minutes de navigateur et les recettes en échec |

Avant C1, rien à changer dans la console : elle sert les agents d'entreprise, et le cadrage ne les touche pas.

## À noter : un fichier du cadrage manque sur `main`

La description de la PR #109 annonce dix fichiers, dont `09-infrastructure.md`. Ce fichier est resté sur la branche `megga/clone-agent` : son commit (`afdcc96`) a été poussé quelques secondes avant la fusion et n'en fait pas partie. Il change aussi `02-architecture.md` (« Retenu : B, en cellules ») et la première question de `08-lots.md`. Tant qu'il n'est pas sur `main`, `main` dit encore que le choix entre A, B et C reste à trancher.

## À trancher par Julien

1. **La coupure d'un clone à deux personnes** (cadrage, `07-securite-conformite.md`) : qui sont les deux ?
2. **Le support** : sans demande écrite du titulaire, MEGGA ne voit que ses nombres. D'accord ?
