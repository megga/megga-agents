# Lot 11 : le catalogue complet d'agency-agents

Décision de Julien (20.11.2026) : la plateforme doit pouvoir répondre à n'importe quelle demande de n'importe quel client, donc tous les agents du dépôt [agency-agents](https://github.com/msitarzewski/agency-agents) (licence MIT) deviennent des modèles prêts à l'emploi. L'agent sur mesure, installé pour un client dans son environnement, reste à part. Rien n'est déployé sans « Fusionne et déploie » de Julien.

Le lot a d'abord été préparé au-dessus des lots 9 et 10, encore ouverts. Cette version le porte seul sur `main` : le catalogue ne dépend que de son propre chargement, écrit ici, et de réglages que `main` connaît déjà.

## Ce qui est installé

Les 283 agents du commit `8ae6164602c95ca78828b148b9052460ee426885`, un fichier par agent, rangés par catégorie : `atelier/gabarits/catalogue/<catégorie>/<id>.md`. L'id est le nom du fichier source (`security-architect`, `unity-architect`...). Aucun n'est écarté. Les deux modèles écrits dans le code (`generaliste`, `immobilier`) ne changent pas et passent en premier.

| Catégorie | Agents | Catégorie | Agents |
|---|---|---|---|
| engineering | 66 | sales | 9 |
| specialized | 59 | project-management | 7 |
| marketing | 37 | paid-media | 7 |
| game-development | 21 | support | 6 |
| gis | 13 | spatial-computing | 6 |
| security | 12 | product | 6 |
| design | 10 | academic | 6 |
| testing | 9 | finance | 5 |
| | | healthcare | 3 |
| | | research | 1 |

## Comment

`scripts/catalogue_agency_agents.py <clone d'agency-agents>` lit chaque agent au commit épinglé (`git show`, quel que soit l'état du clone) et réécrit tout le catalogue ; `--verifier` compare sans écrire, `--liste` donne la liste en Markdown. Même commit, mêmes socles, même résultat.

- **L'en-tête** : le nom et la description de la source (en anglais), `metier: general`, la catégorie, le ton, les garde-fous, la source (dépôt, chemin, commit, MIT) et, s'il a fallu changer le texte, `adapte`.
- **Les consignes** : le socle `catalogue/_catalogue.md`, les garde-fous de l'en-tête, puis le rôle. Le rôle est le texte de l'agent, en anglais, raccourci pour que le tout tienne dans les 8 000 caractères de `Config` : sans blocs de code, emojis, filets ni tirets longs (`noyau.typographie`) ; d'abord l'introduction, l'identité, les règles et la mission, puis le reste tant qu'il y a la place.
- **Le socle** : répondre dans la langue de la personne, d'après ce qu'on sait de l'entreprise et ce que rendent les outils ; ne jamais faire comme si une action avait eu lieu ; ne confirmer ni commande, ni rendez-vous, ni paiement ; aucun avis médical ni juridique ; le 112 en cas de danger ; ni attaquer, ni surveiller, ni tromper quelqu'un, ni contourner une protection ; aucune donnée bancaire, aucun mot de passe.
- **Les réglages** : ceux du généraliste (métier `general`, aucun pack, voix par défaut). Sur `main`, l'agent n'a ni le transfert à un humain ni les demandes notées : le socle ne promet donc pas de « transmettre » une question, il invite la personne à s'adresser à l'équipe. Quand ces outils arriveront, le socle les nommera et le script réécrira le catalogue.
- **Les routes** : les mêmes que pour les autres modèles (`POST /clients`, `POST /clients/{id}/gabarit`) ; `GET /gabarits` rend les deux modèles écrits dans le code puis le catalogue, avec `categorie`, `garde_fous` et `source`. Les consignes d'un modèle du catalogue sont reconnues comme celles d'un modèle (`regles.consignes_de_gabarit`) : un client peut passer de l'un à l'autre.
- **Le chargement** vérifie tout à l'import : un fichier mal formé, une source qui n'est pas MIT, un agent de `security` sans le garde-fou sécurité ou des consignes trop longues arrêtent l'import, donc la CI et le démarrage de l'atelier.

## Les garde-fous

**Sécurité** (`_securite.md`, les 12 agents de `security`) : la règle strictement défensive. Protéger, surveiller, détecter, auditer ce que l'entreprise possède ; jamais d'attaque d'un tiers, de logiciel malveillant ni de contournement ; une preuve d'exploitation devient la description de la faille, sa correction et un test sur le code de l'entreprise ; un test d'intrusion se commande à un prestataire. Cinq passent tels quels avec la règle. Sept sont adaptés, phrase par phrase dans le script (une phrase introuvable dans la source l'arrête) :

| Agent | Adaptation |
|---|---|
| `security-penetration-tester` | réécrit en *Penetration Test Coordinator* : cadrage, autorisation écrite, lecture du rapport, corrections, contre-test |
| `security-blockchain-security-auditor` | plus de code d'exploitation : scénario, correction et test de non-régression local |
| `security-threat-detection-engineer` | les détections se valident sur des journaux enregistrés, plus par des attaques simulées |
| `security-threat-intelligence-analyst` | plus de forums clandestins, d'échantillons de logiciels malveillants ni de balayage d'infrastructures tierces |
| `security-appsec-engineer` | ateliers sur des applications d'entraînement ; le test d'intrusion est commandé à un prestataire |
| `security-cloud-security-architect` | tests d'intrusion et red team commandés à un prestataire |
| `security-architect` | la preuve d'exploitation devient la description de l'abus possible |

**Santé** (`_sante.md`) : aucun avis médical, le 144 d'abord à tout signe d'urgence, le 145 pour une intoxication, les données de santé sensibles (nLPD). Sept modèles, refusés pour la zone `etats-unis` (`PAS_AUX_ETATS_UNIS`), où ces numéros seraient faux.

**Juridique** (`_juridique.md`) : aucun avis juridique, aucun délai calculé ; organiser, résumer, préparer les questions pour un avocat ; une échéance rend la demande urgente. Huit modèles.

## Ce qui reste

- Les agents de finance (`finance-investment-researcher`, `loan-officer-assistant`, `chief-financial-officer`...) n'ont pas de garde-fou propre. À trancher avec Julien.
- Le banc d'essai avec les vrais modèles n'existe pas sur `main` (il vient du lot 9.6) : le catalogue n'est vérifié que par les tests et l'essai de l'atelier.
- Les titres, descriptions et rôles sont ceux de la source, en anglais ; l'agent répond dans la langue de la personne.
- `GET /gabarits` rend 285 modèles avec leurs consignes entières (environ 2 Mo) : un filtre par catégorie pourra servir à la console.
