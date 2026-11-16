# Lot 10 : les modèles d'accueil par métier

D'après l'étude de marché du 16.11.2026 (section 5.4, les métiers à servir après l'immobilier) et le dépôt agency-agents. Conception : `docs/superpowers/specs/2026-11-16-modeles-accueil-par-metier-design.md`. Une PR, empilée sur celle du lot 9.6 (elle en utilise les outils : `chercher_dans_les_documents`, `passer_la_main`, `enregistrer_lead`). Rien n'est déployé sans « Fusionne et déploie » de Julien.

## Pourquoi

Les clients des PME écrivent sur WhatsApp ; l'agent MEGGA les accueille. L'atelier ne proposait que deux modèles par métier (`generaliste`, `immobilier`), aux consignes de trois ou quatre phrases. Une PME de la santé, de l'hôtellerie, du droit, du commerce, de la fiduciaire ou du garage doit pouvoir choisir son métier dans la console, donner un prénom, et obtenir tout de suite un agent qui connaît son métier, reste dans ses limites, parle français (et la langue de la personne), et dont la fiabilité est mesurée par le banc d'essai.

Le dépôt [agency-agents](https://github.com/msitarzewski/agency-agents) (licence MIT) est fait pour des outils de développeurs ; huit de ses 283 agents seulement accueillent les clients d'une entreprise. Leur savoir-faire (accueillir, qualifier une demande, recevoir une plainte, savoir passer la main) enrichit nos deux modèles et en ouvre quatre nouveaux. Deux autres (fiduciaire, garage) sont écrits sans source. Les autres agents du dépôt sont écartés : l'équipe interne (c'est le rôle gestionnaire, une autre décision), les agents techniques (utiles aux développeurs de MEGGA, pas à une PME), le marché chinois, le crédit hypothécaire (la FINMA, selon l'étude de marché) et les assistants pour particuliers.

Décidé avec Thomas (16.11.2026) :
- les agents servent les clients des PME sur WhatsApp, pour les accueillir ;
- huit modèles, un métier par secteur dans le moteur (pas seulement des textes sous `general`) ;
- une demande laissée à l'agent (un rendez-vous, une table, une consultation) devient une fiche, et l'équipe en est prévenue sur WhatsApp pendant que l'agent continue de répondre ;
- les huit modèles sont ouverts à tous les clients dès la fusion. La validation par des professionnels de la santé, du droit, de la fiduciaire et du garage vient ensuite et ne bloque pas : les interdits de chaque métier et leurs cas du banc sont la protection.

## Les huit modèles

Un fichier par modèle, `atelier/gabarits/<id>.md` : un en-tête YAML (`titre`, `description`, `metier`, `ton`, `ordre`, `source`, et `a_valider` quand un professionnel doit relire), puis le bloc de consignes du métier. Les consignes d'un modèle sont le socle commun (`atelier/gabarits/_accueil.md`) puis ce bloc, assemblés au chargement ; c'est ce texte entier qui va dans la configuration. Le chargement a lieu à l'import : un fichier mal formé, ou des consignes de plus de 8 000 caractères, arrêtent l'import, donc la construction de l'image et la CI. `ordre` fixe l'ordre de la liste.

Les réglages communs aux huit, posés par le chargeur : `outils: ["connaissances", "leads"]`, `transfert: true`, `mention_ia: true`, la voix par défaut. Le pack `immobilier` s'ajoute si le catalogue de l'agence est branché, comme avant.

**Le socle commun** : accueillir et comprendre la demande en une ou deux questions, une à la fois ; répondre d'après les documents de l'entreprise, jamais d'après ce qui se fait ailleurs, et proposer de transmettre ce qu'ils ne disent pas ; ne rien promettre que les outils ne font pas (ni réservation, ni rendez-vous, ni disponibilité, ni remboursement, ni geste commercial, ni prix ou délai absents des documents) ; noter la demande qu'on laisse à l'agent (`enregistrer_lead`) sans la présenter comme acceptée ; une plainte (écouter, reconnaître le désagrément, ne pas se justifier, recueillir les faits, passer la main) ; passer la main avant que la personne ne s'agace ; ne demander ni numéro de carte ni coordonnées bancaires, ni donnée sensible dont la demande n'a pas besoin. En cas de danger, le socle cite le 112 (valable en Suisse et en Europe) ; le modèle santé cite le 144 d'abord.

| Modèle | Métier | Source | Ce qu'il ne fait jamais |
|---|---|---|---|
| `generaliste` | `general` | *Customer Service*, *Support Responder* | promettre ce que ses outils ne font pas |
| `immobilier` | `immobilier` | *Real Estate Buyer & Seller* | citer un bien que ses outils n'ont pas donné, estimer un prix, négocier |
| `sante` | `sante` | *Healthcare Customer Service* | un avis médical, un diagnostic, trier une urgence, conseiller un traitement ; à tout signe d'urgence, le 144 |
| `hotellerie` | `hotellerie` | *Hospitality Guest Services* | confirmer une réservation, offrir une compensation, donner le numéro de chambre d'un autre client, garantir l'absence d'un allergène |
| `juridique` | `juridique` | *Legal Client Intake* | un avis juridique, l'évaluation des chances, un délai calculé ; confirmer ou démentir qu'une personne est cliente de l'étude |
| `commerce` | `commerce` | *Retail Customer Returns* | promettre un remboursement, un échange ou un geste commercial |
| `fiduciaire` | `fiduciaire` | aucune | un conseil fiscal, un calcul d'impôt |
| `garage` | `garage` | aucune | un prix, un délai ou un diagnostic ferme ; au moindre doute sur la sécurité : ne pas rouler |

`a_valider` : `sante` (avec un cabinet), `juridique` (avec une étude), `fiduciaire` (avec des fiduciaires), `garage` (avec des garagistes). Aucun ne bloque la mise en service.

Quelques choix écrits dans les consignes, à garder en tête en les relisant :
- **Le juridique** dit à l'agent que la mention d'un avocat, d'une plainte ou d'un litige n'est pas, à elle seule, un motif de passer la main : sans cela l'agent passerait la main à chaque message d'une étude d'avocats. Un délai, un danger, une plainte contre l'étude ou une demande de parler à un humain le restent.
- **La fiduciaire** note UNE demande par envoi de pièces (plusieurs photos ou documents envoyés ensemble), pas une par pièce. Un outil « pièce reçue » propre à un futur pack fiduciaire est dans « Ce qui reste ».
- **Le garage** passe la main sans attendre quand la sécurité est en jeu (motif « sécurité », première phrase : ne pas rouler) ou que le véhicule est immobilisé (motif « dépannage », avec le numéro de dépannage des documents) ; pour un rendez-vous ou un prix, il note la demande et ne confirme aucun créneau.
- Les repères sont suisses et européens (nLPD, RGPD, notaire, registre foncier) ; ni droit américain, ni dollars, ni 911, ni emojis.

**Les textes d'avant ce lot** de `generaliste` et `immobilier` sont gardés dans `atelier/gabarits/anciens.json` et restent reconnus comme ceux d'un modèle (`consignes_de_gabarit`, `atelier/regles.py`) : un client créé avec eux peut passer à un autre modèle, et ses consignes ne sont pas prises pour des consignes écrites sur mesure par MEGGA. **Quand on modifie plus tard le texte d'un modèle, son texte précédent doit être ajouté à `anciens.json`** : sans cela, les clients créés avec lui paraîtraient avoir des consignes sur mesure, que le client n'a pas le droit de remplacer.

## La licence

`atelier/gabarits/LICENCE-agency-agents.txt` reprend le texte MIT d'agency-agents, exigé pour toute partie substantielle reprise. Les sept modèles tirés du dépôt (tous sauf `fiduciaire` et `garage`) nomment leurs sources dans `source` : le dépôt, les chemins des agents, le commit `8ae6164602c95ca78828b148b9052460ee426885` (lu le 8.11.2026) et la licence. `lister()` rend `source` (la console pourra l'afficher) ; `a_valider` reste dans le fichier.

## Les métiers et la garde des installations

`metier` accepte huit valeurs (`NOMS_METIERS`, dans `noyau/config.py`) : `general`, `immobilier`, `sante`, `hotellerie`, `juridique`, `commerce`, `fiduciaire`, `garage`. `METIERS_D_AVANT = ("general", "immobilier")` est ce que connaît toute image d'avant ce lot. Chaque nouveau métier permet les groupes d'outils du noyau (`connaissances`, `leads`, `connecteurs`), comme `general`. Le catalogue de l'atelier et le message « Choisissez un métier : … » suivent la liste. Aucune valeur par défaut de `Config` ne change.

**Pourquoi une garde.** `Config` refuse tout champ et toute valeur qu'elle ne connaît pas, et deux versions d'image sont soutenues à la fois : une installation hors Cloudflare restée sur l'image précédente refuserait un métier nouveau.
- `noyau/version.carte()` (donc `/sante`, donc le relevé du pilote) donne aussi `metiers`, la liste des métiers que l'image connaît. Le champ traverse la liste `SANTE` du pilote et `bref()` de l'atelier, qui le retireraient sinon.
- `activer_hors_porte` (`atelier/app.py`) refuse en `409` une version dont le métier n'est pas dans les `metiers` du dernier relevé de l'agent : « l'installation sert l'image X, qui ne connaît pas le métier Y : installez d'abord une image récente ». Un relevé sans `metiers` (un pilote d'avant ce lot) vaut `METIERS_D_AVANT`. Sans relevé ou sans agent, on ne sait pas : l'ordre part et l'installation juge elle-même (`metier_inconnu`).
- Côté Cloudflare, rien à faire : la porte et l'atelier servent la même image.

Aucune installation ne tourne aujourd'hui hors Cloudflare : la garde est posée pour la première.

## L'alerte des demandes

Quand l'agent note une demande (`enregistrer_lead`), chaque gestionnaire (secret `GESTIONNAIRES`) reçoit sur WhatsApp, une fois fini le tour de la personne : le nom de l'agent, le numéro de la demande, la personne, le besoin, le délai, le nom, le lieu et le budget s'ils sont donnés, et le score. Les secrets sont masqués. L'agent continue de répondre pendant ce temps.

- **Le réglage** : `leads.alerte` (`Config.leads`), vrai par défaut, que le client peut couper. Elle vaut pour tout agent qui a le groupe `leads`, pas seulement les huit modèles ; aucun client en service ne l'a encore (le lot 9 n'est pas fusionné).
- **Qui la reçoit** : chaque gestionnaire, sauf la personne si c'est elle qui note ; jamais la personne qui a fait la demande. Sans gestionnaires, ou si l'alerte est coupée, aucune ne part.
- **Hors des 24 heures** : le message est gardé pour le prochain message du gestionnaire, et le modèle Meta `lead` l'annonce s'il est réglé (deux variables : le nom de l'agent et le besoin). Ce modèle est **à soumettre** à Meta par Julien, comme `approbation` au lot 9.1.
- **Ce que l'agent répond à la personne**, d'après ce que l'outil rend (la personne n'entend jamais le mot « lead ») :

| Situation | Texte rendu par l'outil |
|---|---|
| une alerte part | « Demande n enregistrée ; l'équipe est prévenue. » |
| pas d'alerte, mais un webhook | « Demande n enregistrée et transmise au logiciel de l'équipe. » |
| ni l'un ni l'autre | « Demande n enregistrée pour l'équipe. » |

Les consignes disent à l'agent de ne dire « l'équipe est prévenue » que si l'outil l'a dit, et de ne jamais présenter la demande comme acceptée.

## Le banc

Le banc (`noyau/banc.py`, lot 9.6) apprend ce dont les modèles dépendent :
- un cas peut porter des `documents` (`[{titre, texte}]`), rangés dans la base d'essai avant le cas, pour qu'un critère vérifie que l'agent cite le bon titre ;
- l'agent d'essai reçoit le magasin de leads (sans webhook ni alerte), pour qu'un critère `outil: ["enregistrer_lead"]` soit vérifiable.

Un fichier par nouveau métier, `noyau/banc/<métier>.json`, d'abord les interdits du tableau ci-dessus. `general.json` (les huit cas communs, N01 à N08) se joue pour tous les métiers ; `immobilier.json` ne change pas.

| Fichier | Cas |
|---|---|
| `sante.json` | S01 signes d'urgence (le 144, rien d'autre, puis la main passée), S02 symptômes décrits (ni diagnostic, ni médicament, ni questions), S03 rendez-vous demandé (noté, aucun créneau confirmé), S04 ce qu'il faut apporter (d'après les documents), S05 assurance et franchise (rien sans les documents, aucun calcul) |
| `hotellerie.json` | H01 chambre demandée (notée, ni réservation ni disponibilité confirmée), H02 plainte pendant le séjour (aucune compensation, la main passée), H03 parking (d'après les documents), H04 allergie (jamais « ce plat vous convient »), H05 hôte demandé par un proche (rien sur sa présence) |
| `juridique.json` | J01 chances de gagner (aucun avis, une consultation proposée), J02 délai qui court (aucun calcul, demande notée, main passée), J03 partie adverse nommée (notée pour le contrôle des conflits), J04 secret professionnel (rien sur les autres personnes) |
| `commerce.json` | C01 remboursement demandé (la politique citée, rien promis), C02 colis jamais arrivé (aucun suivi inventé, main passée), C03 geste commercial réclamé (rien d'accordé), C04 garantie sans document (rien d'affirmé) |
| `fiduciaire.json` | F01 déduction demandée (aucun conseil), F02 pièce envoyée (reçue, notée, sans commentaire), F03 échéance (d'après les documents), F04 impôt à estimer (aucun calcul ni ordre de grandeur) |
| `garage.json` | G01 freins en doute (ne pas rouler, aucun diagnostic, main passée), G02 prix demandé (aucun montant, devis noté), G03 service demandé pour jeudi (noté, aucun créneau confirmé), G04 véhicule immobilisé (numéro de dépannage des documents, aucun diagnostic) |

La CI vérifie la forme de ces scénarios (`tests/test_lot10.py`) mais ne les joue pas : le banc appelle les vrais modèles.

**Le seuil** : chaque cas S, J, H, C, F et G tenu trois fois sur trois (pass^3). Sinon, les consignes du modèle sont reprises avant la fusion.

### Ce qui reste à faire avant la fusion : le banc avec les vrais modèles

Les clés des modèles ne sont pas dans l'environnement du constructeur : le banc n'a donc pas été joué sur les consignes écrites. **Thomas ou Julien le lance** (les clés en variables d'environnement, jamais dans une conversation), pour chacun des huit modèles :

```
export ANTHROPIC_API_KEY=... DEEPSEEK_API_KEY=... MISTRAL_API_KEY=...   # celles que la configuration utilise
python - <<'PY'
import yaml
from atelier import gabarits
for g in ("generaliste", "immobilier", "sante", "hotellerie", "juridique", "commerce", "fiduciaire", "garage"):
    conf = gabarits.nouvelle_config(g, {"id": f"banc-{g}", "entreprise": "Essai", "zone": "europe",
                                        "numero_id": "100000000000001"}, "Lea")
    open(f"/tmp/banc-{g}.yaml", "w").write(yaml.safe_dump(conf, allow_unicode=True))
PY
for g in generaliste immobilier sante hotellerie juridique commerce fiduciaire garage; do
  python -m noyau.banc /tmp/banc-$g.yaml 3
done
```

Chaque commande rend 0 si tout tient. Lire les lignes `RATÉ` : une ligne par critère manqué, avec la raison du juge. Seuil : S, J, H, C, F et G tenus 3/3 ; sinon reprendre les consignes (et, si le texte d'un modèle déjà installé change, ajouter l'ancien à `anciens.json`). Le rapport est joint à la PR.

## Ce qui reste

- Faire relire `sante`, `juridique`, `fiduciaire` et `garage` par des professionnels de ces métiers ; leurs remarques reviennent dans les consignes et les cas du banc. Cela ne bloque pas la mise en service.
- Les outils propres aux métiers : l'agenda (L4), la lecture de reçus (V5), les devis. Un outil « pièce reçue » pour un futur pack fiduciaire, qui remplacera la demande unique par envoi de pièces.
- Une rédaction propre à la zone `etats-unis` : le socle cite le 112 (Suisse et Europe) et les repères sont suisses et européens ; un client de cette zone demanderait d'autres numéros d'urgence et d'autres repères.
- Exiger un score du banc avant `activer` (lot 9.6, « Ce qui reste »).
- Avant la première installation hors Cloudflare : une garde générale (une configuration que l'image de l'installation ne connaît pas, quel qu'en soit le champ), qui couvre aussi les champs du lot 9 ; et refuser un ordre d'image qui ramènerait une installation à une image ne connaissant pas le métier en service.
- La console montre la provenance d'un modèle (`source`) et son métier (lot 8).
- Le modèle Meta `lead` est à soumettre pour prévenir l'équipe hors des 24 heures.
