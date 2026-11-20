# Lot 11 : le catalogue complet d'agency-agents

Décision de Julien (20.11.2026) : la plateforme doit pouvoir répondre à n'importe quelle demande de n'importe quel client, donc tous les agents du dépôt [agency-agents](https://github.com/msitarzewski/agency-agents) (licence MIT) deviennent des modèles prêts à l'emploi. Le lot 10 n'en reprenait que six, réécrits en modèles d'accueil ; ceux-là ne changent pas. L'agent sur mesure, installé pour un client dans son environnement, reste à part. Une PR, empilée sur celle du lot 10. Rien n'est déployé sans « Fusionne et déploie » de Julien.

## Ce qui est installé

Les 283 agents du commit `8ae6164602c95ca78828b148b9052460ee426885` (le même que le lot 10), un fichier par agent, rangés par catégorie : `atelier/gabarits/catalogue/<catégorie>/<id>.md`. L'id est le nom du fichier source (`security-architect`, `unity-architect`...). Aucun n'est écarté.

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

`scripts/catalogue_agency_agents.py <clone d'agency-agents>` lit chaque agent au commit épinglé (`git show`, quel que soit l'état du clone) et réécrit tout le catalogue ; `--verifier` compare sans écrire, `--liste` donne la liste en Markdown. Même commit, même résultat.

- **L'en-tête** : le nom et la description de la source (en anglais), `metier: general`, la catégorie, le ton, les garde-fous, la source (dépôt, chemin, commit, MIT) et, s'il a fallu changer le texte, `adapte`.
- **Les consignes** : le socle `catalogue/_catalogue.md`, les garde-fous de l'en-tête, puis le rôle. Le rôle est le texte de l'agent, en anglais, raccourci pour que le tout tienne dans les 8 000 caractères de `Config` : sans blocs de code, emojis, filets ni tirets longs (`noyau.typographie`) ; d'abord l'introduction, l'identité, les règles et la mission, puis le reste tant qu'il y a la place, jamais « Learning & Memory ».
- **Le socle** : répondre dans la langue de la personne, d'après les documents et les outils ; ne jamais faire comme si une action avait eu lieu (le rôle parle souvent de logiciels que l'agent n'a pas) ; noter une demande sans la confirmer ; aucun avis médical ni juridique ; le 112 en cas de danger ; ni attaquer, ni surveiller, ni tromper quelqu'un, ni contourner une protection ; aucune donnée bancaire, aucun mot de passe.
- **Les réglages** : ceux des modèles d'accueil (outils `connaissances` et `leads`, transfert, mention de l'IA, rôles gestionnaire et visiteur, voix par défaut). Ils se choisissent par les mêmes routes (`POST /clients`, `POST /clients/{id}/gabarit`) ; `GET /gabarits` rend les huit modèles d'accueil puis le catalogue, avec `categorie` et `garde_fous`.
- **Le chargement** vérifie tout à l'import, comme au lot 10 : en plus, un modèle de la catégorie `security` sans le garde-fou sécurité, ou sans source, arrête l'import.

## Les garde-fous

**Sécurité** (`_securite.md`, les 12 agents de `security`) : la règle du pack sécurité de Julien, strictement défensive. Protéger, surveiller, détecter, auditer ce que l'entreprise possède ; jamais d'attaque d'un tiers, de logiciel malveillant ni de contournement ; une preuve d'exploitation devient la description de la faille, sa correction et un test sur le code de l'entreprise ; un test d'intrusion se commande à un prestataire. Cinq passent tels quels avec la règle (`security-ai-generated-code-auditor`, `security-compliance-auditor`, `security-incident-responder`, `security-secrets-credential-engineer`, `security-senior-secops`). Sept sont adaptés, phrase par phrase dans le script (une phrase introuvable dans la source l'arrête) :

| Agent | Adaptation |
|---|---|
| `security-penetration-tester` | réécrit en *Penetration Test Coordinator* : cadrage, autorisation écrite, lecture du rapport, corrections, contre-test ; plus de reconnaissance, d'exploitation, de pivot ni d'ingénierie sociale |
| `security-blockchain-security-auditor` | plus de code d'exploitation : scénario, correction et test de non-régression local |
| `security-threat-detection-engineer` | les détections se valident sur des journaux enregistrés, plus par des attaques simulées (red team, purple team) |
| `security-threat-intelligence-analyst` | plus de forums clandestins, d'échantillons de logiciels malveillants ni de balayage d'infrastructures tierces |
| `security-appsec-engineer` | ateliers sur des applications d'entraînement ; le test d'intrusion est commandé à un prestataire |
| `security-cloud-security-architect` | tests d'intrusion et red team commandés à un prestataire |
| `security-architect` | la preuve d'exploitation devient la description de l'abus possible |

Hors de `security`, aucun agent n'attaque un tiers ; le socle interdit de toute façon d'attaquer ou de contourner.

**Santé** (`_sante.md`) : aucun avis médical, le 144 d'abord à tout signe d'urgence, le 145 pour une intoxication, les données de santé sensibles (nLPD). Sept modèles : `healthcare-clinical-evidence-agent`, `healthcare-innovation-strategist`, `healthcare-sovereign-health-systems-agent`, `healthcare-aging-parent-care-companion`, `healthcare-customer-service`, `healthcare-marketing-compliance`, `medical-billing-coding-specialist`.

**Juridique** (`_juridique.md`) : aucun avis juridique, aucun délai calculé ; organiser, résumer, préparer les questions pour un avocat ; une échéance est notée puis passée à l'équipe. Huit modèles : `legal-billing-time-tracking`, `legal-client-intake`, `legal-document-review`, `support-legal-compliance-checker`, `data-privacy-officer`, `healthcare-marketing-compliance`, `finance-tax-strategist`, `study-abroad-advisor` (les visas).

**Zone États-Unis** : comme `sante` et `garage` au lot 10, les sept modèles santé donnent des numéros suisses (144, 145) ; ils sont refusés pour la zone `etats-unis` (`PAS_AUX_ETATS_UNIS`). Les autres y restent ouverts : leur socle nomme le 112 comme celui de la Suisse et de l'Europe.

## Ce qui reste

- Le banc avec les vrais modèles (`python -m noyau.banc`, `docs/lot10.md`) n'est pas joué : aucune clé de modèle sur le poste qui a fait le lot. Les cas communs (`general.json`) valent pour tout le catalogue.
- Les titres et descriptions sont ceux de la source, en anglais ; le rôle aussi (l'agent répond dans la langue de la personne).
- Les agents de finance (`finance-investment-researcher`, `loan-officer-assistant`, `chief-financial-officer`...) n'ont pas de garde-fou propre : le lot 10 avait écarté le crédit hypothécaire (FINMA). À trancher.
- `GET /gabarits` rend 291 modèles avec leurs consignes entières (environ 2 Mo) : un filtre par catégorie pourra servir à la console.
