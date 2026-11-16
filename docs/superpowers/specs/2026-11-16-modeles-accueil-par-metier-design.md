# Les modèles d'accueil par métier, d'après agency-agents : conception

Le 16.11.2026, avec Thomas. Rien n'est déployé sans « Fusionne et déploie » de Julien.

## L'intention

Les clients des PME écrivent sur WhatsApp ; l'agent MEGGA les accueille. L'atelier propose aujourd'hui deux modèles par métier (`generaliste`, `immobilier`), aux consignes de trois ou quatre phrases.

Le dépôt [agency-agents](https://github.com/msitarzewski/agency-agents) (licence MIT, 283 agents, lu au commit `8ae6164602c95ca78828b148b9052460ee426885` du 8.11.2026) est fait pour des outils de développeurs (Claude Code, Cursor). Seuls huit de ses agents accueillent les clients d'une entreprise ; leur savoir-faire (accueillir, qualifier une demande, recevoir une plainte, savoir passer la main) peut enrichir nos deux modèles et en ouvrir quatre nouveaux. L'étude de marché du 16.11.2026 (`livrables/etude-marche.md`, section 5.4) classe les métiers à servir après l'immobilier : fiduciaires, santé ambulatoire (partie administrative), hôtellerie, artisans et garages, gérance.

**Le but** : qu'une PME de ces métiers choisisse son métier dans la console, donne un prénom, et ait tout de suite un agent d'accueil qui connaît son métier, qui reste dans ses limites, qui parle français (et la langue de la personne), et dont la fiabilité est mesurée par le banc d'essai.

## Les objectifs

- Huit modèles d'accueil : `generaliste` et `immobilier` enrichis ; `sante` (accueil administratif d'un cabinet), `hotellerie` (hôtels et restaurants), `juridique` (premier contact d'une étude d'avocats), `commerce` (retours et service après-vente), `fiduciaire`, `garage`.
- Un métier par secteur dans le moteur : `sante`, `hotellerie`, `juridique`, `commerce`, `fiduciaire`, `garage`.
- Des scénarios par métier dans le banc (`noyau/banc/<métier>.json`) : un score de fiabilité par secteur.
- La provenance de chaque texte et la licence MIT gardées.

## Les non-objectifs

- Les 275 autres agents du dépôt (équipe interne, technique, marché chinois) : voir « Ce qui a été écarté ».
- De nouveaux outils par métier (agenda, lecture de reçus, devis, logiciel hôtelier) : les modèles n'utilisent que les outils qui existent. Les métiers leur préparent la place.
- Une synchronisation avec le dépôt d'origine.
- Des écrans : l'interface est le lot 8.

## Les anti-objectifs (un échec, même si tout marche)

- Un agent qui promet ce que ses outils ne font pas : réserver une table ou une chambre, fixer un rendez-vous dans un agenda qu'il ne voit pas, rembourser, accorder un geste commercial.
- Un agent de santé qui pose un diagnostic, trie une urgence, conseille un traitement ou demande des symptômes ; un agent juridique qui donne un avis ou évalue les chances ; un agent fiduciaire qui donne un conseil fiscal ou calcule un impôt ; un agent de garage qui annonce un prix, un délai ou un diagnostic ferme.
- Des consignes traduites de l'américain (HIPAA, assurances américaines, 911, dollars, « closing ») ou des méthodes pour humains (indicateurs, tableaux de bord, formation d'équipe).
- Changer le comportement d'un client en service (Four Seasons, `essai-megga`, `megga-estates`) : un modèle ne s'applique qu'à la création d'un client ou quand il le choisit.

## Les contraintes

- `Config.consignes` : 8 000 caractères au plus, sans tiret long, tiret moyen ni point médian (`sans_artefacts`) ; `Config.ton` : 200 au plus.
- `Config` refuse tout champ et toute valeur qu'elle ne connaît pas (`extra="forbid"`, `Literal`) : une image d'avant ce lot refuse un métier nouveau.
- Deux versions d'image sont soutenues à la fois ; une installation hors Cloudflare peut rester sur la précédente.
- Ne jamais changer une valeur par défaut de `Config` sans changer `VERSION` : ce lot n'en change aucune.
- Le banc n'est pas joué par la CI (il appelle les vrais modèles) ; la CI vérifie que les scénarios sont bien formés.
- Le noyau ajoute déjà aux consignes « Réponds dans la langue de la personne », le ton et la langue par défaut (`noyau/agent.py`, `consignes`) : un modèle ne les répète pas.
- Une PR par lot. Celle-ci s'empile sur la #44 (lot 9.6), dont elle utilise les outils : documents (`chercher_dans_les_documents`), transfert (`passer_la_main`), leads (`enregistrer_lead`).

## Les approches considérées

- **A. Des modèles seulement**, tous sous le métier `general`. Aucun changement du moteur, toutes les images les acceptent. Mais ni banc ni catalogue par secteur, et les futurs outils d'un secteur n'auraient pas de place : il faudrait plus tard changer de métier des configurations en service.
- **B. Un métier par secteur (retenue par Thomas).** Le banc, la console et les futurs packs ont un métier par secteur. En échange, la liste des métiers du moteur change, et l'atelier doit protéger les installations restées sur l'image précédente.
- **C. Un seul modèle « accueil » avec un choix de secteur** : écarté, il a les défauts de A. Son bon côté, un socle commun écrit une fois, est repris dans B.

Écartés aussi : convertir les 283 agents tels quels (une liste inutilisable pour une PME, des consignes en anglais deux fois trop longues, des rôles sans rapport avec l'accueil) ; une réimportation automatique (elle mettrait en service des consignes que personne n'a relues).

## Ce qui a été décidé (Thomas, 16.11.2026)

1. Les agents servent les clients des PME sur WhatsApp, pour les accueillir.
2. Huit modèles : les six tirés du dépôt, et deux écrits sans source, fiduciaire et garage.
3. Un métier par secteur (approche B).
4. Une demande laissée à l'agent (un rendez-vous, une table, une consultation) devient une fiche, et l'équipe en est prévenue sur WhatsApp pendant que l'agent continue de répondre (section 6).
5. Les huit modèles sont ouverts à tous les clients dès la fusion. La validation par des professionnels (santé, juridique, fiduciaire, garage) vient ensuite et ne bloque pas ; les interdits de chaque métier et leurs cas du banc sont la protection.

## La conception

### 1. Les métiers (`noyau/config.py`)

- `metier: Literal["general", "immobilier", "sante", "hotellerie", "juridique", "commerce", "fiduciaire", "garage"]`, `"general"` par défaut (inchangé).
- `METIERS` et `OUTILS_DES_ROLES` : chaque nouveau métier permet `GROUPES_DU_NOYAU` (connaissances, leads, connecteurs), comme `general`.
- `METIERS_D_AVANT = ("general", "immobilier")` : ce que connaît toute image d'avant ce lot.
- Le catalogue de l'atelier (`atelier/regles.py`, `metiers`) et le message « Choisissez un métier : … » (`atelier/messages.py`) suivent la liste sans autre changement.

### 2. Les installations restées sur l'image précédente

- `noyau/version.carte()` (donc `/sante`, donc le relevé du pilote) donne aussi `metiers` : les métiers que l'image connaît.
- `activer_hors_porte` (`atelier/app.py`) refuse en `409` une version dont le métier n'est pas dans les `metiers` du dernier relevé de l'agent : « l'installation sert l'image X, qui ne connaît pas le métier Y : installez d'abord une image récente ». Un relevé sans `metiers` vaut `METIERS_D_AVANT`. Sans relevé ou sans agent, on ne sait pas : l'ordre part et l'installation juge elle-même, comme `trop_ancienne` le fait pour le schéma.
- Le champ doit traverser deux filtres qui le retireraient : la liste `SANTE` du pilote (`pilote/service.py`), qui choisit ce qu'il remonte de `/sante`, et `bref()` (`atelier/pilotage.py`), qui choisit ce que l'atelier garde de l'agent. Un pilote d'avant ce lot, qui ne l'envoie pas, passe toujours.
- Côté Cloudflare, rien à faire : la porte et l'atelier servent la même image.
- Aujourd'hui, aucune installation ne tourne hors Cloudflare (tous les clients de `clients/` sont en zone `europe`). La garde est posée pour la première. Les champs du lot 9 (`transfert`, `mention_ia`, les outils `connaissances` et `leads`) posent la même question face à une image d'avant le lot 9 : elle est hors de ce lot (voir « Ce qui reste après ce lot »).

### 3. Les modèles deviennent des fichiers (`atelier/gabarits/`)

- `atelier/gabarits.py` devient le paquet `atelier/gabarits/`. Son `__init__.py` garde la même API (`GABARITS`, `lister`, `gabarit`, `reglages_pour`, `nouvelle_config`, `VOIX_PAR_DEFAUT`, `IDENTITE`, `NUMERO`) : aucun import ne change.
- Un fichier par modèle, `atelier/gabarits/<id>.md` : un en-tête YAML, puis le bloc de consignes propre au métier.

  ```
  ---
  titre: Garage
  description: Accueille les demandes de vos clients (photos, vocaux), prépare la prise en charge et passe la main à l'atelier.
  metier: garage
  ton: chaleureux, simple et précis, vouvoie en français
  ordre: 8
  source: null
  a_valider: avec des garagistes (ne bloque pas la mise en service)
  ---
  Tu réponds pour un garage. ...
  ```

  `source`, pour un modèle tiré du dépôt : `{depot, chemins, commit, licence: MIT}`.
- Un socle commun, `atelier/gabarits/_accueil.md`, écrit une fois (section 5). Les consignes d'un modèle sont le socle puis le bloc du métier, assemblés au chargement : c'est ce texte entier qui va dans la configuration. Comme aujourd'hui, seul MEGGA modifie ensuite les consignes (elles ne sont pas dans `CHAMPS_CLIENT`). Visé : 3 000 à 5 000 caractères au total ; jamais plus de 8 000.
- Les textes d'avant ce lot de `generaliste` et `immobilier` restent reconnus comme ceux d'un modèle (`consignes_de_gabarit`, `atelier/regles.py`) : un client créé avec eux peut toujours passer à un autre modèle, et ses consignes ne sont pas prises pour celles que MEGGA a écrites sur mesure. Le chargeur garde ces anciens textes à part (par exemple `atelier/gabarits/anciens.json`).
- Les réglages communs aux huit, posés par le chargeur : `outils: ["connaissances", "leads"]`, `transfert: true`, `mention_ia: true`, `voix: {voix: VOIX_PAR_DEFAUT}`. `reglages_pour` garde sa règle : le pack `immobilier` s'ajoute si le catalogue de l'agence est branché.
- Le chargement a lieu à l'import : un fichier mal formé ou trop long arrête l'import, donc la construction de l'image et la CI. `ordre` fixe l'ordre de la liste (généraliste, immobilier, puis les nouveaux).
- `lister()` rend aussi `source` (l'attribution, lisible par la console) ; `a_valider` reste dans le fichier.
- `pyproject.toml` : le paquet `atelier.gabarits` et ses `*.md` en données du paquet.

### 4. La licence

- `atelier/gabarits/LICENCE-agency-agents.txt` : le texte MIT d'agency-agents (« Copyright (c) 2025 AgentLand Contributors »), exigé par la licence pour toute partie substantielle reprise.
- Chaque modèle tiré du dépôt nomme ses sources dans `source`. `docs/atelier.md` le mentionne.

### 5. Ce que disent les consignes

**Le socle commun** (`_accueil.md`), d'après *Customer Service* et *Support Responder* :
- accueillir, comprendre la demande en une ou deux questions, une à la fois ;
- répondre d'après les documents de l'entreprise (`chercher_dans_les_documents`) en citant la source ; dire simplement ce qu'on ne sait pas, et proposer de transmettre ;
- ne rien promettre que les outils ne font pas (réservation, rendez-vous ferme, remboursement, prix, délai) ; recueillir la demande et la transmettre à la place ;
- une plainte : écouter, reconnaître le désagrément, ne pas se justifier ni accuser, recueillir les faits, passer la main ;
- passer la main (`passer_la_main`, avec un résumé) quand la personne demande un humain, pour une réclamation, un litige, une urgence, ou quand l'agent ne peut pas aider ;
- noter une demande (`enregistrer_lead`) quand une personne laisse quelque chose à traiter (un rendez-vous, une réservation, une consultation, un devis) : son besoin, son délai, ce qu'elle a donné pour être recontactée ; puis lui dire ce que l'outil a rendu (« l'équipe est prévenue » seulement si elle l'est, section 6) ;
- ne demander que ce qui sert la demande : jamais de mot de passe ni de numéro de carte ; pas de donnée sensible (santé, opinions, poursuites) sans nécessité (nLPD, RGPD) ;
- le style de WhatsApp : des messages courts, sans titres ni tableaux.

**Les blocs par métier.** Ce qui vient du dépôt : la suite d'un accueil, les questions de qualification, les cas de plainte et d'escalade. Ce qui n'en vient pas : les indicateurs, les tableaux de bord, les scripts pour humains, le droit américain, les emojis.

| Modèle (métier) | Sources (agency-agents) | Ce que fait l'agent | Ce qu'il ne fait jamais | Repères suisses et européens |
|---|---|---|---|---|
| `generaliste` (`general`) | *Customer Service*, *Support Responder* (`specialized/customer-service.md`, `support/support-support-responder.md`) | le socle, les rappels | | |
| `immobilier` (`immobilier`) | *Real Estate Buyer & Seller* (`specialized/real-estate-buyer-seller.md`), partie besoins de l'acheteur et retour après visite | les consignes actuelles ; les questions utiles (type, lieu, budget, délai, financement), le retour après une visite | citer un bien que ses outils n'ont pas donné ; estimer un prix ; négocier | notaire, registre foncier ; ni « MLS » ni « closing » |
| `sante` (`sante`) | *Healthcare Customer Service* (`specialized/healthcare-customer-service.md`) | horaires, accès, documents à apporter ; demandes de rendez-vous et de renouvellement transmises au cabinet ; questions administratives et de facturation d'après les documents | diagnostiquer, trier, conseiller un traitement, demander des symptômes ; à tout signe d'urgence : le 144 (le 112 en Europe), sans autre conseil | données de santé : données sensibles (nLPD) ; assurance de base et complémentaire seulement d'après les documents |
| `hotellerie` (`hotellerie`) | *Hospitality Guest Services* (`specialized/hospitality-guest-services.md`) | avant et pendant le séjour ou le repas : horaires, accès, parking, services, d'après les documents ; demandes particulières et demandes de réservation recueillies et transmises ; plainte prise en charge | confirmer une réservation, une disponibilité ou un prix qu'il ne voit pas ; offrir une compensation | taxe de séjour, langues des hôtes |
| `juridique` (`juridique`) | *Legal Client Intake* (`specialized/legal-client-intake.md`) | premier contact : le domaine, les faits essentiels, l'urgence (une échéance, une audience), les noms des parties adverses pour le contrôle des conflits par l'étude ; demande de consultation transmise | donner un avis, évaluer les chances, calculer un délai, promettre que l'étude prendra le dossier | secret professionnel de l'avocat ; ne recueillir que le nécessaire |
| `commerce` (`commerce`) | *Retail Customer Returns* (`specialized/retail-customer-returns.md`) | retours, échanges, suivi : d'après la politique de la boutique (documents) ; numéro de commande et motif recueillis ; passer la main | promettre un remboursement, un échange ou un geste ; soupçonner une fraude devant la personne | les garanties seulement d'après les documents de la boutique |
| `fiduciaire` (`fiduciaire`) | aucune (étude de marché, 5.4) | accuser réception des pièces envoyées (photos de reçus, documents) et les signaler à l'équipe ; rappeler les échéances données par les documents ; répondre aux questions pratiques (TVA, impôts) seulement d'après les documents, avec la source ; prendre une demande pour le fiduciaire | conseil fiscal ou comptable personnalisé ; calculer un impôt ; affirmer une déduction | **à valider avec des fiduciaires** |
| `garage` (`garage`) | aucune (étude de marché, 5.4) | prise en charge : le véhicule (marque, modèle, année, kilométrage), ce que la personne constate, ses photos et vocaux, l'urgence (véhicule immobilisé) ; demande de rendez-vous transmise | annoncer un prix, un délai ou un diagnostic ferme ; en cas de doute sur les freins, la direction ou un voyant rouge : dire de ne pas rouler et passer la main | dépannage : le numéro que donnent les documents du garage ; **à valider avec des garagistes** |

`juridique` tient au secret professionnel et `sante` aux données sensibles : ce sont les deux modèles où une erreur coûte le plus. Leurs scénarios du banc portent d'abord sur leurs interdits.

### 6. L'équipe prévenue d'une demande (`noyau/connecteurs.py`)

Aujourd'hui, `enregistrer_lead` range la fiche (et l'envoie au webhook du client s'il est réglé) sans prévenir personne sur WhatsApp. Une demande d'accueil qui dort dans la console est une demande perdue.

- Quand l'agent enregistre une fiche, chaque gestionnaire (secret `GESTIONNAIRES`) la reçoit sur WhatsApp, une fois fini le tour de la personne : le besoin, le délai, le nom donné, le score, et le numéro de la personne. Même mécanique que l'alerte d'un transfert (`noyau/reprises.py`, `apres_le_tour`). L'agent, lui, continue de répondre à la personne.
- Hors des 24 heures d'un gestionnaire : le modèle Meta `lead` s'il est réglé ; sinon l'alerte attend son prochain message, comme une demande d'accord (9.1).
- Sans gestionnaires : la console seule, et le webhook s'il est réglé. Les numéros de l'équipe sont donc à poser à la mise en service (`scripts/secrets_client.sh`).
- Le client peut couper l'alerte (un CRM branché lui suffit) : `Leads.alerte`, vrai par défaut, dans `leads`, déjà réglable par le client. Un champ ajouté, aucune valeur par défaut changée.
- Ce que l'outil rend au modèle dit la vérité : « Demande n enregistrée ; l'équipe est prévenue. » quand une alerte part, « Demande n enregistrée pour l'équipe. » sinon. Les consignes demandent à l'agent de le répéter tel quel, sans promettre de rappel.
- Cela vaut pour tout agent qui a les leads, pas seulement les huit modèles. Aucun client en service ne les a encore (le lot 9 n'est pas fusionné).
- Essais : l'alerte part après le tour, à chaque gestionnaire, jamais à la personne ; aucune sans gestionnaires ; aucune si coupée ; hors des 24 heures, le modèle Meta ou l'attente.
- Le modèle Meta `lead` est à soumettre (Julien) pour prévenir hors des 24 heures.

### 7. Le banc

- Un fichier par nouveau métier, `noyau/banc/<métier>.json`, au format de `general.json` (`etapes`, `faits`, `criteres` : `juge`, `outil`, `pas_outil`, `motifs`, `pas_motif`), trois à cinq cas chacun, d'abord les interdits du tableau ci-dessus. Par exemple, pour la santé : une douleur dans la poitrine (renvoie au 144, aucun conseil, passe la main), des symptômes décrits (aucun diagnostic), une demande de rendez-vous (transmise, aucun créneau confirmé).
- `general.json` (les huit cas communs) se joue déjà pour tous les métiers ; `immobilier.json` ne change pas.
- **Le banc apprend ce dont les modèles dépendent.** Aujourd'hui, l'agent d'essai n'a ni documents ni leads : `chercher_dans_les_documents` ne trouve jamais rien, et `enregistrer_lead` n'est pas proposé. Ce lot y ajoute :
  - un cas peut porter des `documents` (`[{titre, texte}]`), rangés dans la base d'essai avant le cas ; un critère peut alors vérifier que l'agent cite le bon titre ;
  - l'agent d'essai reçoit le magasin de leads (sans webhook), pour qu'un critère `outil: ["enregistrer_lead"]` soit vérifiable.
- `tests/test_lot9_6.py` vérifie la forme des scénarios de tous les métiers, et les deux ajouts ci-dessus.
- Avant la fusion : le banc joué (k = 3) sur une configuration tirée de chacun des huit modèles, `python -m noyau.banc` avec les clés en variables ; le rapport va dans la PR. Seuil : chaque cas d'un interdit tenu trois fois sur trois ; sinon, les consignes sont reprises avant la fusion. Les clés des modèles ne sont pas dans l'environnement du constructeur : Thomas ou Julien lance le banc (ou pose les clés dans l'environnement, jamais dans une conversation).

### 8. Les essais de la CI

- Chaque modèle donne une configuration valide (`nouvelle_config`, pour chaque zone) ; ses consignes font 8 000 caractères au plus, sans caractère refusé ; son métier est le bon ; les six tirés du dépôt nomment leur source.
- Le catalogue liste les huit métiers ; le message d'erreur d'un métier inconnu les cite ; un client peut appliquer lui-même chacun des huit modèles (décision 5).
- Changer de métier retire les outils qui ne vont pas avec le nouveau (comme `test_changer_de_metier_retire_les_outils`).
- `carte()` donne les métiers ; `activer_hors_porte` refuse un métier absent du relevé, accepte un métier présent, laisse partir l'ordre sans relevé, et vaut `METIERS_D_AVANT` pour un relevé sans `metiers`.
- Les essais existants qui listent les métiers ou les deux modèles sont mis à jour, pas retirés.

### 9. La documentation

- `docs/atelier.md`, « Les modèles par métier » : la table des huit, leur provenance, la licence.
- `docs/lot10.md` : ce lot (pourquoi, quoi, ce qui reste), comme `docs/lot9.md`.
- `docs/plan.md` : le lot 10 dans la liste des lots.

## Ce qui reste au constructeur

- Le texte exact des consignes, dans le cadre de la section 5 et sous les contraintes.
- La forme exacte de l'en-tête des fichiers et le nom du socle commun.
- Le détail des scénarios du banc.
- Le découpage en commits.

## Ce qui a été écarté

- **Les agents de l'équipe interne** (environ 70 : marketing, ventes, finance, notes de réunion) : ils serviraient le patron et son équipe (le rôle gestionnaire), pas ses clients. Une autre décision, un autre lot.
- **Les agents techniques** (environ 140 : développement, jeux, SIG, sécurité, essais, design) : utiles aux développeurs de MEGGA dans Claude Code, pas à une PME.
- **Les agents du marché chinois** (environ 17) : hors de la Suisse et de l'Europe.
- **Loan Officer Assistant** (crédit hypothécaire) : l'étude de marché écarte la banque et le courtage (FINMA).
- **Aging Parent Care Companion, Study Abroad Advisor, Language Translator, Personal Growth Mentor** : des assistants pour particuliers, pas l'accueil d'une entreprise.

## Ce qui reste après ce lot

- Faire relire `sante`, `juridique`, `fiduciaire` et `garage` par des professionnels de ces métiers ; leurs remarques reviennent dans les consignes et les cas du banc (décision 5 : cela ne bloque pas).
- Les outils propres aux métiers : l'agenda (L4), la lecture de reçus (V5), les devis.
- Exiger un score du banc avant `activer` (lot 9.6, « Ce qui reste »).
- Avant la première installation hors Cloudflare : une garde générale (une configuration que l'image de l'installation ne connaît pas, quel qu'en soit le champ), qui couvre aussi les champs du lot 9 ; et refuser un ordre d'image qui ramènerait une installation à une image ne connaissant pas le métier en service.
- La console montre la provenance d'un modèle (`source`) et son métier (lot 8).
