# L'équipe dans la configuration (lot 11.1) : conception

Le 17.11.2026, avec Thomas ; reprise le même jour d'après le plan relu par Julien (`docs/lot8.md`, « Ce que Julien a changé »). À valider par Julien : l'approche (section « Les approches ») et les sept points de « Ce qui reste à décider ». Rien n'est déployé sans « Fusionne et déploie » de Julien.

La première version a été relue par un agent neuf dans le rôle du constructeur, et ses remarques sont intégrées. La reprise d'après Julien (l'accueil, les changements immédiats, le redémarrage) et l'accord avec la console fusionnée le même jour (PR #54) ne l'ont pas été.

## L'intention

Thomas a décidé le 17.11.2026 que le lancement vise une équipe d'agents internes : le patron d'une PME ouvre la console et parle à plusieurs agents, chacun avec son prénom, son métier, ses consignes et ses outils. L'agent qui accueille les clients sur WhatsApp est un agent de cette équipe qui a, en plus, un numéro.

Aujourd'hui, une entreprise a un agent. **Le but de ce sous-lot** : qu'une entreprise ait plusieurs agents dans le même conteneur et sur la même base, qu'elle les crée elle-même et qu'ils servent aussitôt, sans rien changer pour une entreprise qui n'en a qu'un. C'est la fondation du reste du lot 11 : l'entrée console (11.2) parlera à ces agents, le catalogue (11.3) élargira les métiers.

## Ce que le plan relu par Julien change à cette conception

1. **Un agent est en service dès sa création** (décision 10). Dans la première version, tout nouvel agent était un brouillon à essayer. Créer, mettre en pause et archiver deviennent des changements immédiats (section 7).
2. **L'accueil se branche sur un agent, plus tard, par l'essai** (décision 12). Dans la première version, l'accueil appartenait d'office à l'agent écrit en haut de la configuration, qui existait toujours. Désormais n'importe quel agent de l'équipe peut le tenir, et une entreprise peut n'avoir encore ni accueil ni agent : c'est le premier lancement (section 1).
3. **Le client crée ses agents lui-même**, depuis les huit modèles d'accueil du lot 10 en attendant le catalogue. Dans la première version, MEGGA seul créait un membre.
4. **Chaque création redémarre le conteneur.** C'était un détail ; c'est maintenant ce que l'utilisateur attend après « Créer » (section 8).
5. **L'apparence, c'est la couleur et les yeux** (décision 8) : hors de la configuration, donc hors de ce sous-lot.

## Ce que la console fusionnée attend du moteur (PR #54, sur `main` depuis le 17.11.2026)

La console (`console/`, Next.js, shadcn, Better Auth, CopilotKit) crée déjà un agent et lui parle, contre un serveur d'essai local (`console/agents/serveur.py`) qui « tient la place de l'atelier ». Sa PR liste six manques de l'API. Ce sous-lot en ferme trois :

| Ce qui manque (PR #54) | Où |
|---|---|
| 1. Plusieurs agents par compte | Ici : `Config.equipe` |
| 2. La création par le client lui-même | Ici : la création d'un membre, ouverte au client |
| 3. La mise en service immédiate | Ici : les changements immédiats |
| 4. Une entrée AG-UI au fil de l'eau pour un agent en service | 11.2 |
| 5. Le lien entre un compte Better Auth et un client de l'atelier | Hors de ce sous-lot ; en attendant, MEGGA crée l'entreprise, vide, et la console garde son jeton côté serveur |
| 6. L'historique d'une conversation | 11.2 |

Trois choses de la console fixent des choix de cette conception :

- **C'est la console qui tire l'identifiant d'un agent** (`ag_` puis vingt caractères) et l'inscrit par `PUT /agents/{id}`, qu'elle peut rejouer sans risque. La création d'un membre prend donc cette forme (section 7), et `Membre.id` accepte ces identifiants (section 1).
- **La couleur, les yeux et l'épingle sont déjà gardés par la console**, dans sa propre base (table `agent`). Ils n'ont pas à aller dans la configuration.
- **La conversation passe par AG-UI**, vers `…/agents/{id}/agui`, sur l'interface d'Agno (`run_entity`). Elle ne passera donc pas par `Conversations.repondre_api` : la section 3 dit ce que le tour d'un membre garantit, quelle que soit l'entrée.

## Ce qui existe (branche `megga/lot-10-modeles`, PR #53)

- **Une configuration décrit un agent** (`noyau/config.py`, `Config`) : `nom_agent`, `ton`, `consignes`, `metier`, `outils`, et jusqu'à trois rôles (gestionnaire, partenaire, visiteur) qui ajoutent leurs consignes et leurs outils. Le noyau lit `conf.nom_agent` à dix endroits : les consignes, le nom de l'agent, les leads, le transfert, les demandes d'accord, la réécriture pour l'oral, la mention de l'IA, les modèles Meta.
- **Le conteneur construit déjà plusieurs agents** (`noyau/app.py`, `creer`) : un agent « public », et un agent par rôle, tous sur la même base, avec le même gardien des accords et la même base de documents. Le rôle de la personne choisit l'agent (`Conversations.agent_du_role`).
- **Une conversation est une personne** : `arun(..., user_id=personne, session_id=personne)` (`noyau/tour.py`). Dans Agno 3.2.0, `session_id` est la clé de la table des sessions : deux agents qui servent la même personne sous le même `session_id` partageraient un seul historique. La mémoire, elle, se lit par `user_id` seul : elle est commune à tous les agents d'une même base.
- **Nos tables ne connaissent que la personne** : le fil (`megga_fil`) et le journal d'audit n'ont pas de colonne pour dire quel agent. Les demandes d'accord portent le rôle de la personne, et c'est lui qui retrouve l'outil à exécuter une fois l'accord donné (`noyau/approbations.py`, `Gardien._faire`).
- **Un modèle par métier** (`atelier/gabarits/`) donne des consignes, un ton et un métier, et des réglages d'accueil : les documents, les leads, le transfert, la mention de l'IA, la voix (`reglages_pour`).
- **L'atelier range un client comme un composant d'Agno et ses versions** (`atelier/versions.py`). Une nouvelle version part de la dernière, brouillon compris (`atelier/app.py`, `nouvelle`). Mettre une version en service, c'est l'inscrire dans l'annuaire de la porte, qui vide puis redémarre le conteneur (`porte/src/agent.js`, `traiterAlarme`). Un brouillon jamais essayé ne se met pas en service, sauf `forcer`, réservé à MEGGA.
- **L'annuaire reçoit la configuration entière, valeurs par défaut comprises** (`atelier/porte.py`, `activer`). Un ordre à une installation part, lui, sans les valeurs par défaut (`noyau/pilotage.py`, `config_a_envoyer`), pour qu'une image précédente le lise encore.
- **La configuration arrive au conteneur dans une variable d'environnement**, `CLIENT_CONFIG` (`porte/src/agent.js`, `environnement`). Le seul secret qu'un client doit avoir pour démarrer est sa base (`SECRETS_CLIENT_REQUIS`).
- **Les gestionnaires n'ont pas de plafond de tours** (`noyau/garde.py`, `SANS_PLAFOND`).

## Les objectifs

- Une équipe dans la configuration : `Config.equipe`, une liste de membres. Chacun a un identifiant, un prénom, un métier, un ton, ses consignes, ses connecteurs, ses règles d'accord, un état (en service, en pause).
- N'importe quel membre peut tenir l'accueil. Une entreprise peut n'avoir encore ni accueil ni agent.
- Le conteneur construit un agent par membre en service, à côté de ceux de l'accueil.
- Un tour peut se faire avec un membre : sa conversation, son historique, son fil, ses accords et son journal sont les siens.
- Un document dit quels agents le consultent.
- L'atelier crée un membre depuis un modèle et le met en service aussitôt ; il le met en pause et l'archive de même ; il passe par un brouillon et un essai pour le modifier, et pour tout ce qui touche à l'accueil.
- Un plafond de tours par compte et par jour pour l'équipe, à part de celui de l'accueil.
- Une image d'avant ce lot ne reçoit pas une configuration qu'elle ne sait pas lire.

## Les non-objectifs

- **Parler à un membre en service.** Ce sous-lot ne donne aucune entrée vers un membre : ni route publique, ni WhatsApp. C'est le 11.2. Ici, un membre répond dans l'essai de l'atelier, et le conteneur dit qu'il l'a construit.
- Le catalogue des métiers d'équipe (11.3). En attendant, un agent se crée depuis les huit modèles d'accueil du lot 10.
- Brancher WhatsApp ou un connecteur en un clic depuis la conversation (11.6, 8.7). Ici, l'accueil se branche par une version que MEGGA prépare.
- Les agents qui se parlent ou travaillent à plusieurs (11.7), et donc `agno.team` (voir « Ce qui a été écarté »).
- Les tâches planifiées (11.4), les pièces jointes (11.5).
- La couleur, les yeux, le groupe et l'épingle d'un agent. Ils ne changent rien à son comportement, et n'entrent pas dans la configuration. La console garde déjà la couleur, les yeux et l'épingle dans sa base ; le groupe les y rejoindra.
- Mettre en pause l'agent qui tient l'accueil (voir « Ce qui reste à décider », 2).
- Un modèle de langage par membre : tous ont ceux de l'entreprise.
- Le banc d'essai par membre : il vient avec les métiers du 11.3.

## Les anti-objectifs (un échec, même si tout marche)

- **Changer quoi que ce soit pour Four Seasons** ou pour tout client sans équipe : ses consignes, ses outils, les identifiants de ses agents, ses clés de conversation, son historique. La mesure : un essai de la CI qui compare, à l'octet, les agents construits avant et après ce lot pour `clients/four-seasons-properties.yaml`.
- **Un agent ouvert au public sans être passé par l'essai.**
- **Un document interne lu par l'accueil.** Une grille de marges donnée à l'agent comptable ne doit jamais sortir dans une réponse à un visiteur.
- **Deux agents qui partagent un historique** parce qu'ils servent la même personne.
- **Une équipe interne bavarde qui coupe l'accueil** en épuisant le plafond du jour, ou l'inverse.
- **Un identifiant de membre réutilisé** : le nouvel agent hériterait des conversations de l'ancien.

## Les contraintes

- `Config` refuse tout champ qu'elle ne connaît pas (`extra="forbid"`) : une image d'avant ce lot refuse une configuration qui porte `equipe`.
- Deux versions d'image sont soutenues à la fois, et un retour à l'image précédente doit rester possible.
- Ne jamais changer une valeur par défaut de `Config` sans changer `VERSION` : ce lot ajoute des champs, vides par défaut, et n'en change aucune.
- Chaque migration de la base est additive (`noyau/stockage.py`).
- **La taille de la configuration.** Linux refuse une variable d'environnement de plus de 131 072 octets. Aujourd'hui, les consignes d'une configuration font 44 000 caractères au plus (8 000 pour l'agent, 12 000 par rôle). Vingt membres à 8 000 caractères en ajouteraient 160 000. Cloudflare ne documente pas de limite propre pour l'environnement d'un conteneur : à vérifier par un essai.
- Un conteneur `basic` a 1 Gio de mémoire et un quart de processeur ; chaque zone a au plus 50 conteneurs en marche à la fois (`porte/wrangler.jsonc`).
- Le contenu d'une conversation ne passe pas par l'atelier (principe du plan).
- La pile des PR #38 à #53 part de `main` à la PR #47 ; `main` a avancé de 23 commits depuis (dont le mot du matin, #51, le site de Genève, #52, et la console, #54). Elle est à rebaser avant d'y empiler ce lot.
- Une PR pour ce sous-lot, empilée sur la #53 : il se sert des accords (9.1), des documents (9.2), des serveurs MCP (9.4) et des modèles par métier (lot 10).

## Les approches considérées

- **A. L'équipe s'ajoute à la configuration, et l'accueil désigne son agent (recommandée).** `Config` gagne `equipe`, la liste des agents, tous pareils, et `agent_accueil`, qui nomme celui qui tient l'accueil. L'écriture d'aujourd'hui, où l'agent d'accueil est décrit en haut de la configuration (`nom_agent`, `ton`, `consignes`), reste valide telle quelle : Four Seasons n'est pas réécrit. Le moteur lit qui tient l'accueil à un seul endroit, quelle que soit l'écriture. L'atelier, la porte et le pilote gardent « un client, une configuration, des versions ». En échange : deux écritures de l'agent d'accueil vivent côte à côte ; tout changement d'un agent est une version de toute la configuration, donc un redémarrage du conteneur ; la configuration grossit.
- **B. La configuration passe en version 2 : une seule écriture.** Les champs de l'agent quittent le haut de `Config` ; une configuration en version 1 est convertie à la lecture, et réécrite en version 1 pour une image précédente tant qu'elle n'a qu'un agent. Le modèle est le plus net. Mais Four Seasons passe par une conversion dans les deux sens à chaque lecture et à chaque envoi, et c'est là qu'une erreur lui coûterait.
- **C. Une configuration par agent, réunies par entreprise.** Chaque agent a son composant et ses versions dans l'atelier. Mais il faut une entité « entreprise » au-dessus des clients : dans l'atelier (les droits, les jetons, les listes), dans l'annuaire de la porte (un conteneur pour plusieurs configurations, les secrets), dans le pilote (les ordres signés). Les réglages communs (zone, serveurs MCP, numéro) finissent quand même dans une configuration principale, et le redémarrage reste le même.

**Pourquoi A.** Elle donne le même modèle que B à tout ce qui est nouveau (des agents tous pareils, un accueil qui en désigne un), sans faire passer Four Seasons par une conversion. B reste possible plus tard : ce sera retirer l'ancienne écriture, quand plus aucun client ne l'emploiera. C refait l'atelier et la porte pour un gain (des versions par agent) que A obtient en comparant deux versions agent par agent (section 7).

## Ce qui a été décidé

1. Le lancement vise l'équipe d'agents internes (Thomas, 17.11.2026).
2. L'accueil reste : un agent de l'équipe qui a, en plus, un numéro WhatsApp (plan, 17.11.2026).
3. Un agent est en service dès sa création ; ensuite, un changement est une version (Julien, décision 10).
4. Ouvrir un agent au public passe par l'essai, comme aujourd'hui (Julien, décision 12).
5. L'apparence d'un agent n'est pas dans `Config` (Julien, décision 8). La décision dit « la base de l'atelier » ; la console fusionnée la garde dans la sienne. Dans les deux cas, le moteur n'en sait rien.
6. En attendant le catalogue, les métiers proposés sont les huit modèles d'accueil du lot 10 (Julien).

## Ce qui reste à décider (Julien, avec Thomas)

1. **L'approche** : A, recommandée. Tout ce qui suit la suppose, en particulier `agent_accueil` et un `nom_agent` devenu facultatif.
2. **Mettre en pause l'agent qui tient l'accueil.** Il faut dire ce que reçoit le client : rien, un message fixe, ou un passage à l'équipe. Proposé : hors de ce sous-lot ; ici, l'agent qui tient l'accueil ne se met ni en pause ni aux archives tant qu'il le tient.
3. **La mémoire commune.** Ce qu'un gestionnaire dit à un agent, les autres agents le savent quand il leur parle (la mémoire d'Agno se lit par personne). Proposé : on la garde commune, c'est ce qu'on attend d'une équipe. Chaque gestionnaire garde sa propre mémoire.
4. **Les chiffres** : vingt membres au plus ; 300 tours par compte et par jour avec l'équipe ; 2 000 par jour pour toute l'équipe ; 100 000 octets pour une configuration qui a une équipe. Ce sont des propositions.
5. **Ce que l'atelier inscrit dans l'annuaire.** Après ce lot, toute mise en service écrirait `"equipe": []`, même pour Four Seasons, et l'image précédente la refuserait : le retour arrière casserait pour tous les clients. Proposé : inscrire la configuration sans ses valeurs par défaut, comme `config_a_envoyer` le fait déjà pour les ordres (section 9). C'est le seul endroit où ce lot touche au chemin de tous les clients ; un essai vérifie que chaque fichier de `clients/` se relit à l'identique. L'autre voie, plus étroite : ne retirer que les champs de ce lot quand ils sont vides.
6. **Le redémarrage à chaque création.** Créer un agent redémarre le conteneur de l'entreprise ; l'attente ressemble à celle d'un conteneur qu'on réveille. Proposé : mesurer, du clic « Créer » à la première réponse du nouvel agent ; au-delà de 10 secondes, le rechargement à chaud des membres (section 8) entre dans ce sous-lot.
7. **Un agent d'accueil pas encore ouvert au public.** Les huit modèles du lot 10 parlent de noter une demande et de passer la main. Ces deux outils sont ceux de l'accueil : un agent créé depuis un tel modèle ne les a pas tant qu'il ne tient pas l'accueil. Proposé : on l'accepte, et ses consignes lui disent de ne jamais faire comme s'il avait un outil qu'il n'a pas.

## La conception

### 1. La configuration (`noyau/config.py`)

```python
EQUIPE_MAX = 20
CONFIG_MAX = 100_000  # octets, en JSON : seulement pour une configuration qui a une équipe
NOMS_RESERVES = ("principal", "accueil", "tous", "public", "gestionnaire", "partenaire", "visiteur", "bloque")

class Membre(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,31}$")      # tiré par la console (ag_…), ne change jamais
    prenom: str = Field(min_length=1, max_length=40)
    metier: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,40}$")  # le modèle d'où il vient : generaliste, garage…
    ton: str | None = Field(default=None, max_length=200)    # vide : celui de l'entreprise
    consignes: str = Field(default="", max_length=8000)
    connecteurs: tuple[str, ...] = ()                        # des noms de serveurs de Config.mcp
    approbations: dict[str, REGLE_OUTIL] = {}
    etat: Literal["service", "pause"] = "service"

class Config(Strict):
    ...
    nom_agent: str | None = Field(default=None, min_length=1, max_length=40)   # facultatif désormais
    equipe: tuple[Membre, ...] = Field(default=(), max_length=EQUIPE_MAX)
    agent_accueil: str | None = None                         # le membre qui tient l'accueil
```

- **L'accueil**, c'est l'entrée publique de l'entreprise (son numéro WhatsApp, l'entrée de ses logiciels par API, son site) et ses réglages, qui restent en haut de la configuration : `whatsapp`, `roles`, `voix`, `modeles_meta`, `metier`, `outils`, `catalogue`, `gestion`, `marche`, `transfert`, `leads`, `mention_ia`, `bonjour`.
- **Qui tient l'accueil s'écrit de deux façons, jamais les deux.** Celle d'aujourd'hui : `nom_agent`, `ton` et `consignes` en haut de la configuration. Four Seasons reste écrit ainsi, et cet agent porte l'identifiant réservé `principal`. La nouvelle : `agent_accueil` nomme un membre de `equipe`, en service ; `nom_agent` et `consignes` du haut sont alors vides. Une configuration à l'ancienne écriture peut avoir une équipe : ses membres s'ajoutent à l'agent `principal`, qui garde l'accueil.
- **Sans l'une ni l'autre, l'entreprise n'a pas d'accueil** : `whatsapp`, `roles`, `transfert`, `leads` et les packs d'outils sont refusés (« ces réglages demandent un agent d'accueil »). Une configuration sans aucun agent est valide : c'est l'entreprise qui vient d'être créée, celle du premier lancement.
- `Config.accueil()` rend l'agent qui tient l'accueil (`id`, `prenom`, `ton`, `consignes`), ou rien. C'est le seul endroit où le moteur lit son identité : les dix lectures de `conf.nom_agent` passent par lui. Pour l'écriture d'aujourd'hui, il rend ce qu'elles lisaient.
- `metier` d'un membre est une étiquette libre : l'identifiant du modèle d'où il vient, celui que la console connaît (`generaliste`, `garage`). Ce n'est pas la liste fermée de `Config.metier`, qui reste le secteur de l'accueil. Ajouter un métier au catalogue (11.3) ne change donc pas l'image.
- `prenom`, `ton` et `consignes` passent par `sans_artefacts` (ni tiret long ni point médian), `approbations` par `_approbations`.
- `Config` vérifie aussi : les identifiants sont uniques et hors de `NOMS_RESERVES` ; chaque nom de `connecteurs` est celui d'un serveur de `Config.mcp` ; **quand `equipe` n'est pas vide**, la configuration entière, en JSON et en UTF-8, fait `CONFIG_MAX` octets au plus (« raccourcissez des consignes »). Une configuration sans équipe n'a pas cette vérification : rien ne change pour elle.
- Il n'y a ni « brouillon » ni « archivé » dans la configuration. Un agent en cours de modification est un agent qu'un brouillon change (section 7). Un agent archivé est retiré de la configuration ; ses conversations restent dans la base sous son identifiant.

### 2. La construction des agents (`noyau/agent.py`, `noyau/app.py`)

- **Les agents de l'accueil** (l'agent « public » et un agent par rôle) se construisent comme aujourd'hui, avec l'identité que rend `Config.accueil()`. Leurs identifiants ne changent pas (`config.id`, `config.id-rôle`). Sans accueil, ils ne sont pas construits : `/whatsapp` répond `404` et `/api/messages` `403`, et rien de ce qui en dépend (leads, transfert, rappels) n'est monté.
- **Un agent par membre en service**, celui qui tient l'accueil compris : `construire(..., membre=m)`, d'identifiant `f"{config.id}-{m.id}"`, de nom `m.prenom`. Ils partagent la base, le gardien, la base de documents et les boîtes MCP. Un membre en pause n'est pas construit. L'agent `principal` de l'ancienne écriture n'a pas d'agent de membre dans ce sous-lot : rien ne se construit de plus pour Four Seasons.
- `consignes(config, role=None, membre=None)`. Pour un membre : « Tu es {prenom}, et tu travailles pour {entreprise}, avec son équipe. », le ton (le sien, sinon celui de l'entreprise), les règles communes, ses consignes, puis la consigne des documents, et celle des connecteurs s'il en a. `REGLES` se sépare en deux : les règles communes (ne rien inventer, jamais de mot de passe, la langue, la mémoire, pas de tiret long) et les règles de WhatsApp (des messages courts sans titres, les rappels), qui ne vont qu'aux agents de l'accueil. Un membre reçoit une règle de plus : si ses consignes parlent d'un outil qu'il n'a pas, il dit que ce n'est pas encore branché, et ne fait jamais comme s'il l'avait (point 7 à décider). Le serveur d'essai de la console ajoute déjà une consigne de ce genre (`ESSAI`). **L'ordre et le texte des consignes des agents de l'accueil ne changent pas d'un caractère.**
- `regles_pour(conf, role=None, membre=None)` : les règles de la configuration, puis celles du membre. Les outils de ses serveurs MCP attendent un accord, sauf règle « auto », comme aujourd'hui.
- Les outils d'un membre : `chercher_dans_les_documents`, que tout membre reçoit (borné aux documents qu'il consulte, section 5), et les boîtes MCP des serveurs qu'il nomme. Rien d'autre. Donner un document à un agent n'est donc pas un changement de configuration : il suffit de l'écrire dans la liste du document, sans version ni redémarrage. Le modèle de recherche ne se charge qu'au premier document, comme aujourd'hui.
- Une demande d'accord garde le rôle de la personne, comme aujourd'hui, et le membre dans sa nouvelle colonne (section 4). `Gardien.connaitre` range les outils par agent, et `Gardien._faire` les retrouve de même : par le membre s'il y en a un, sinon par le rôle. Une action accordée s'exécute ainsi avec l'outil du membre qui l'a demandée. Un identifiant de membre ne peut pas être un nom de rôle (`NOMS_RESERVES`).
- `GET /interne/equipe` (jeton interne) : les membres construits, `[{id, prenom, metier, etat, connecteurs, accueil}]`. Rien de privé. La porte le relaie (`/admin/clients/:id/equipe`) : c'est par là que l'atelier montre qu'une équipe est en service. Hors Cloudflare, l'atelier ne le lit pas, comme le suivi.

### 3. Un tour avec un membre (`noyau/tour.py`)

- **Deux sortes de conversations.** Celle de l'accueil appartient au numéro, pas à l'agent : sa clé reste la personne seule, comme aujourd'hui. Si l'accueil passe d'un agent à un autre, la conversation d'un client continue. Celle d'un membre a pour clé `f"{personne}~{membre}"` (fonction `cle`). Le `~` n'apparaît ni dans un numéro ni dans un identifiant de personne venu par API.
- `_executer(personne, entendu, role, images, membre=None)` : l'agent du membre, `user_id=personne`, `session_id=cle(personne, membre)`. La mémoire reste par personne (point 3 à décider).
- `repondre_api(personne, texte, role, membre=None)` porte le tour d'un membre. Avec un membre : pas d'accueil, pas de mention de l'IA, pas de transfert vers un humain, pas de fil résumé (`fil_tenu`). Un membre inconnu ou en pause : un refus clair, sans tour de modèle.
- Le verrou, le débit et la session sont par conversation, c'est-à-dire par `cle(personne, membre)` : parler à deux agents à la fois ne bloque pas l'un derrière l'autre.
- Tout ce qui nomme l'agent dans un message (une demande d'accord) prend le prénom du membre.
- **Aucune route ne mène encore à un membre en service.** Le 11.2 ouvrira l'entrée AG-UI que la console attend (`POST …/agents/{membre}/agui`, sur `run_entity` d'Agno), dans la zone du client. `repondre_api(..., membre=...)` sert ici aux essais, et de modèle à cette entrée.
- **Ce que le 11.2 devra reprendre de ce tour**, parce que `run_entity` parle à l'agent sans passer par `Conversations` : la clé de conversation, le verrou, le débit, le plafond de l'équipe, le refus d'un membre en pause, et le fil. Ce qui est attaché à l'agent lui-même tient dans tous les cas : ses consignes, ses documents, ses accords et le journal d'audit.
- **La session ne vient jamais du navigateur.** AG-UI envoie un identifiant de fil choisi par l'écran. L'entrée du 11.2 tirera la session du compte connecté et du membre (`cle`), sinon un compte pourrait relire le fil d'un autre en donnant son identifiant.
- Le 11.2 dira aussi quel agent répond au patron quand il écrit, dans la console, à celui qui tient l'accueil : son agent de membre, ou l'agent du rôle gestionnaire, qui a les outils du métier.

### 4. La base (`noyau/stockage.py`)

- Une colonne `membre` (32 caractères, vide permis) sur `megga_fil`, `megga_audit` et `megga_approbations`. Vide : l'accueil, donc toutes les lignes d'aujourd'hui.
- Une colonne `membres` (du JSON, vide permis) sur `megga_documents` (section 5).
- Elles s'ajoutent par `_completer`, sans valeur requise : l'image précédente continue d'écrire et de lire ces tables. Le constructeur vérifie si `SCHEMA_VERSION` doit avancer ; a priori non, comme pour les tables du lot 9.
- **Les lectures d'aujourd'hui ne voient que l'accueil.** Celles du fil (`stockage.Fil`) filtrent `membre` vide. Celles du suivi qui relisent les tours d'Agno par `user_id` (`Suivi.conversations`, `Suivi.messages`) ne gardent que les tours de l'accueil, ceux dont la session est la personne seule. Sans cela, les tours d'un gestionnaire avec un agent interne se mêleraient à son fil WhatsApp dans la console. Les volumes et les coûts (`Suivi.tours`) comptent tout, équipe comprise.
- Un filtre `membre=` s'ajoute aux lectures du journal d'audit et des demandes d'accord.
- Le droit d'accès et le droit à l'effacement (`donnees_personne`, `effacer_personne`) suivent déjà `user_id` dans les tables d'Agno et `personne` dans les nôtres : les conversations avec les membres sont couvertes. Un essai le vérifie.

### 5. Les documents (`noyau/connaissances.py`)

- Un document porte `membres` : la liste de ceux qui le consultent, des identifiants de membres ou `accueil` (les agents qui répondent au public). Vide : tous. Les documents d'aujourd'hui, donnés à l'accueil, restent donc lus par lui, et deviennent lisibles par les membres : ils étaient faits pour le public.
- **Dans une entreprise qui a une équipe, ajouter un document sans dire qui le consulte est refusé.** On écrit la liste, ou `tous`. C'est la garde contre le document interne servi à un visiteur. Elle se tient à un seul endroit, `Base.ajouter`, qui sait si l'entreprise a une équipe : les trois voies d'ajout y passent.
- Les trois voies acceptent donc `membres` et rendent le refus : `POST /interne/connaissances` (`400`), la route de l'atelier `POST /clients/{id}/connaissances` (qui refuse aujourd'hui toute clé hors de sa liste), et la commande `python -m noyau.connaissances ajouter` (`--membres`), seule voie hors Cloudflare, qui lit pour cela la configuration du conteneur.
- Un document donné à l'agent qui tient l'accueil n'est pas pour autant donné à l'accueil : `accueil` s'écrit en toutes lettres. Ce que le patron confie à son agent dans la console ne part pas chez les visiteurs.
- `Base.chercher(question, pour)` ne rend que les passages des documents que `pour` consulte ; l'outil de chaque agent est construit avec son `pour`. Le modèle de recherche reste chargé une seule fois.
- La liste des documents rend `membres`.

### 6. Les plafonds (`noyau/garde.py`)

- Un second compteur, à part de celui de l'accueil : `EQUIPE_PAR_COMPTE_JOUR = 300` tours par compte et par jour avec des membres, `EQUIPE_JOUR = 2000` pour toute l'équipe. Il compte aussi les gestionnaires : `SANS_PLAFOND` ne vaut que pour l'accueil.
- Les deux compteurs ne se touchent pas : une équipe bavarde ne coupe pas l'accueil, et un abus sur WhatsApp ne coupe pas l'équipe.
- En mémoire, comme `Plafond` : un conteneur endormi repart à zéro.

### 7. L'atelier (`atelier/regles.py`, `atelier/app.py`, `atelier/essai.py`, `atelier/versions.py`)

**Trois sortes de changements.**

| Changement | Chemin | Pourquoi |
|---|---|---|
| Créer un membre ; le mettre en pause, le reprendre ; l'archiver | Immédiat : la version est faite, publiée et inscrite à la porte dans le même geste. Ni brouillon ni essai | Décision 10 pour la création ; une pause et un archivage n'ont rien à essayer |
| Modifier un agent en service : prénom, ton, consignes, connecteurs, règles d'accord | Un brouillon, l'essai de cet agent, puis la mise en service | Principe du plan |
| Tout ce qui touche à l'accueil : qui le tient, son numéro, ses rôles, ses réglages | Un brouillon, un essai, puis la mise en service. Jamais immédiat | Décision 12 |

La liste des changements immédiats est une constante de l'atelier. Le 11.6 dira si brancher un connecteur en un clic, depuis la conversation, la rejoint.

- **Créer une entreprise** : `POST /clients` accepte déjà une configuration entière ; elle peut désormais n'avoir aucun agent. Cette première version se met en service sans essai : il n'y a rien à essayer.
- **Créer un membre** : `PUT /clients/{id}/equipe/{membre}`, `{prenom, gabarit}`, ouvert au client. C'est la forme du `PUT /agents/{id}` que la console envoie aujourd'hui à son serveur d'essai : elle tire l'identifiant, et peut rejouer l'appel sans créer deux agents (son `metier` est notre `gabarit`). L'atelier refuse un identifiant mal formé, réservé, ou déjà vu dans une version de ce client pour un autre agent ; le même appel rejoué rend le membre tel qu'il est. Le modèle donne les consignes, le ton et le métier ; ses réglages d'accueil ne s'appliquent pas (ils viendront avec l'accueil). MEGGA peut donner à la place des `consignes` et un `metier` sur mesure. Les refus par zone d'un modèle valent (`reglages_pour`). La réponse rend le membre et la version en service, sans attendre le redémarrage : la porte le lance et répond aussitôt (`redemarrer`).
- **Modifier, mettre en pause** : `PATCH /clients/{id}/equipe/{membre}`. Avec `etat` seul, c'est immédiat ; sinon, c'est un brouillon.
- **Avec quel droit** : la console appelle ces routes depuis son serveur, avec le jeton du client, jamais depuis le navigateur. Relier un compte Better Auth à un client de l'atelier reste à faire (manque 5 de la PR #54).
- **Archiver** : `DELETE /clients/{id}/equipe/{membre}`, immédiat. Refusé (`409`) pour l'agent qui tient l'accueil, comme sa mise en pause (point 2 à décider).
- **Un changement immédiat** part de la version en service, pas du dernier brouillon, et passe par le chemin de `activer` : l'annuaire d'abord, puis la version publiée, et le retour à la version d'avant si la porte refuse.
- **Le dernier brouillon suit.** Après un changement immédiat, le brouillon ouvert est refait sur la nouvelle version en service : les mêmes changements, agent par agent, et les mêmes essais. Un agent archivé entre-temps en sort. Créer un agent n'annule donc pas une modification en cours sur un autre.
- **Ouvrir un agent au public** : pas de route nouvelle dans ce sous-lot. MEGGA prépare une version par `POST /versions` : `agent_accueil`, le numéro, et les réglages d'accueil du modèle de cet agent (`reglages_pour`). Elle suit le chemin de toute version : l'essai, puis la mise en service. Le clic « Brancher WhatsApp » du client viendra avec le 11.6 et le 8.7, sur ce même chemin.
- **Les droits.** Un client crée un membre depuis un modèle, change son `prenom`, son `ton`, ses `connecteurs`, ses `approbations` et son `etat`, lui applique un autre modèle, et l'archive. MEGGA seul écrit des `consignes` sur mesure et règle l'accueil (`agent_accueil`, le numéro, les rôles), comme aujourd'hui. `reglages_de_megga` compare aussi, agent par agent, ce qui est réservé à MEGGA.
- **Ce qui a changé entre deux versions.** `regles.changes(avant, apres)` rend les agents dont la définition diffère, hors `etat` : des identifiants de membres, et `accueil` quand celui qui le tient ou l'un de ses réglages diffère. C'est ce qui dit à la console qu'un agent a une modification en cours.
- **L'essai** : `POST /versions/{v}/essai` accepte `membre` (ou `role`, pas les deux). L'agent du membre répond dans la base d'essai, avec ses consignes ; ses connecteurs ne sont pas branchés dans l'essai (l'atelier n'appelle pas les outils du client). Le compte des essais se tient par agent dans les notes de la version (`essais_membres`). Un brouillon parti d'un autre brouillon reprend de lui les essais des agents qu'il ne change pas.
- **La mise en service d'un brouillon** : chaque agent rendu par `changes`, entre la version en service et celle qu'on active, doit avoir été essayé au moins une fois ; pour `accueil`, c'est un essai par un rôle ou par l'agent public. Cette règle remplace celle d'aujourd'hui (un essai de la version). `forcer` reste à MEGGA.
- **Un brouillon dépassé est refusé à la mise en service** (`409`, « refaites ce changement sur la version en service »). Il est dépassé quand, en remontant ses bases (`notes.base`), la première version publiée qu'on rencontre n'est pas celle en service. C'est le filet sous « le dernier brouillon suit » ; il vaut dès que l'une des deux versions a une équipe.
- `GET /clients/{id}` rend tous les agents de l'entreprise, celui de l'ancienne écriture compris (sous `principal`) : son état, s'il tient l'accueil, s'il a une modification en cours. `GET /clients` rend, pour chaque client, le nombre de ses membres en service. Le composant de l'atelier prend pour nom le prénom de l'agent qui tient l'accueil, sinon celui de l'entreprise.

### 8. Le redémarrage

- Tout changement mis en service redémarre le conteneur, comme aujourd'hui : la porte le vide (`/interne/vider`, qui laisse finir les tours en cours), l'arrête, le relance, puis rejoue les webhooks gardés. Aucun message WhatsApp n'est perdu.
- Avec la décision 10, cela arrive à chaque agent créé, mis en pause ou archivé. Pour celui qui crée, l'attente est celle d'un conteneur qu'on réveille. Pour un collègue en pleine conversation avec un autre agent, son tour finit, puis le suivant attend le redémarrage.
- **La mesure, avant d'aller plus loin** (point 6 à décider) : du clic « Créer » à la première réponse du nouvel agent, sur `essai-megga`. Jusqu'à 10 secondes, on en reste là. La création elle-même répond vite, dans les 10 secondes que la console lui laisse : c'est le premier message qui attend le redémarrage.
- **Au-delà, le rechargement à chaud des membres entre dans ce sous-lot.** Quand la nouvelle configuration ne diffère de celle que sert le conteneur que par `equipe`, la porte ne le redémarre pas : elle lui envoie la configuration (`POST /interne/equipe`), et le conteneur la valide, puis remplace d'un coup ses agents de membres et ce qui dépend de l'équipe (la garde des documents). S'il ne tourne pas, il n'y a rien à faire : il lira l'annuaire à son réveil. S'il refuse ou ne répond pas, la porte redémarre comme aujourd'hui. Tout ce qui touche à l'accueil redémarre toujours.

### 9. Les images d'avant, et le retour arrière

- `noyau/version.carte()` donne aussi `champs` : les noms des champs de `Config` que l'image connaît. Il doit traverser les deux filtres que le lot 10 a trouvés : la liste `SANTE` du pilote et `bref()` de l'atelier.
- `activer_hors_porte` refuse en `409` une version qui se sert d'un champ absent des `champs` du dernier relevé de l'installation. Un relevé sans `champs` est celui d'une image d'avant ce lot : elle connaît tout sauf `equipe` et `agent_accueil`, et elle exige `nom_agent` : ce sont les trois cas alors refusés (l'image du lot 10, la précédente soutenue, connaît les champs du lot 9 ; aucune installation ne tourne aujourd'hui hors Cloudflare). Sans relevé, l'ordre part et l'installation juge elle-même, comme aujourd'hui. Pour les images à venir, cela ferme la garde générale que le lot 10 avait laissée ouverte.
- **Côté Cloudflare, l'annuaire** (point 5 à décider). `Porte.activer` inscrit la configuration par `config_a_envoyer` : sans les valeurs par défaut. Une configuration sans équipe ne porte alors aucun champ que l'image précédente ignore, et un retour arrière la relit. Un essai vérifie, pour chaque fichier de `clients/`, que la configuration relue de cette forme est égale à l'originale.
- **Un défaut de `config_a_envoyer` à corriger d'abord** (vérifié le 17.11.2026 sur le `Config` du lot 10). Une configuration dont le modèle principal est de Mistral et dont le secours choisi est celui par défaut (`deepseek-v4-pro`) perd son secours à l'envoi, puis est refusée à la relecture : `Modeles._secours_choisi` exige un secours écrit. Les ordres aux installations ont déjà ce défaut depuis le lot 9.5. La correction : `config_a_envoyer` écrit toujours `modeles.secours` quand il écrit `modeles`. Un essai la couvre.
- **Le retour arrière.** Une image d'avant ce lot ne démarre pas sur une configuration qui a une équipe ou qui n'a pas d'agent d'accueil. Règle d'exploitation : tant que l'image précédente ne connaît pas `equipe`, seul `essai-megga` a une équipe en service. `GET /clients` permet de lister les clients qui en ont une avant tout retour à une image plus ancienne.

### 10. Les essais de la CI, et les mesures avant la fusion

Les essais (`tests/test_lot11_1.py`) :

- Une configuration sans équipe donne les mêmes agents qu'avant : mêmes identifiants, mêmes consignes à l'octet, mêmes outils, même `session_id`. Jouée sur `clients/four-seasons-properties.yaml`, `essai-megga.yaml` et `megga-estates.yaml`.
- L'accueil : `Config.accueil()` rend la même identité pour les deux écritures ; un membre qui le tient donne des agents d'accueil aux mêmes identifiants qu'aujourd'hui ; les deux écritures à la fois, un membre inconnu ou en pause, un numéro sans agent d'accueil sont refusés ; une configuration sans agent est valide, et son conteneur répond `404` à WhatsApp.
- `Membre` et `Config.equipe` : un identifiant en double ou réservé, un connecteur inconnu, vingt et un membres, une configuration de plus de `CONFIG_MAX` sont refusés, avec un message lisible en français (`atelier/messages.py`).
- Trois membres : trois agents aux identifiants, aux consignes et aux outils distincts ; un membre en pause n'est pas construit, et lui parler rend le refus.
- Deux membres et la même personne : deux sessions, deux historiques ; la mémoire est commune. La conversation WhatsApp d'une personne garde sa clé quand l'accueil change d'agent.
- Le fil, le journal et les demandes d'accord portent le membre ; les lectures d'aujourd'hui ne voient pas ses lignes.
- Un document réservé au membre A n'est trouvé ni par B ni par l'accueil, même quand A tient l'accueil ; un document sans liste est refusé quand il y a une équipe, accepté sinon ; les trois voies d'ajout rendent le même refus.
- Une action accordée s'exécute avec l'outil du membre qui l'a demandée.
- Le plafond de l'équipe arrête un gestionnaire au 301e tour du jour, sans toucher l'accueil.
- L'atelier, les changements immédiats : un membre créé depuis chacun des huit modèles, sous un identifiant de la console (`ag_` et vingt caractères), est en service sans essai, avec les consignes du modèle et sans ses réglages d'accueil ; le même appel rejoué ne crée pas un second agent, et un identifiant déjà pris par un autre est refusé ; la pause, la reprise et l'archivage de même ; l'archivage de l'agent qui tient l'accueil est refusé ; un refus de la porte laisse la version d'avant en service.
- L'atelier, les brouillons : modifier un agent demande son essai ; trois modifications à la suite tiennent dans le dernier brouillon, qui reprend les essais des agents inchangés ; après une création, le brouillon ouvert suit, avec ses essais ; un brouillon dépassé est refusé.
- L'atelier, l'accueil : une version qui change `agent_accueil` ou le numéro ne se met pas en service sans essai, pour le client comme pour MEGGA sans `forcer` ; un client ne peut pas l'écrire.
- Les droits du client et de MEGGA sur un membre ; `changes`.
- `carte()` donne `champs` ; `activer_hors_porte` refuse une équipe pour un relevé sans `champs`, et laisse passer les champs du lot 9.
- L'annuaire reçoit la configuration sans ses valeurs par défaut ; relue, elle est égale à l'originale pour chaque fichier de `clients/` ; sans équipe, elle ne porte ni `equipe` ni `agent_accueil` ; une configuration Mistral au secours par défaut se relit.
- L'effacement d'une personne retire ses conversations avec les membres.

Les mesures, dont les chiffres vont dans la PR :

- Du clic « Créer » à la première réponse du nouvel agent, sur `essai-megga` (section 8).
- La mémoire et le temps de démarrage du conteneur avec vingt membres, comparés à un agent seul. Si un conteneur `basic` ne tient pas vingt membres avec le modèle de recherche chargé, `EQUIPE_MAX` baisse.
- Une configuration de 100 000 octets démarre bien dans un conteneur de Cloudflare.
- Le banc de parité de Four Seasons (`parite/`, 36 cas), joué une fois par Thomas ou Julien avec les clés, comparé au dernier rapport (`docs/parite-7-7.md`, 89 sur 100). L'essai de la CI est la garde ; le banc est la confirmation.

**Fini quand** : sur `essai-megga`, deux agents créés par l'atelier depuis deux modèles sont en service aussitôt, à côté d'Alix (`GET /interne/equipe` les rend) ; chacun répond dans l'essai de l'atelier avec ses consignes et ses outils ; modifier l'un d'eux demande un essai avant la mise en service ; Alix répond sur WhatsApp comme avant ; les agents de Four Seasons sont identiques à l'octet.

### 11. La documentation

- `docs/atelier.md` : l'équipe, l'accueil et ses deux écritures, les trois sortes de changements, l'essai par agent.
- `docs/lot11.md` : ce sous-lot (pourquoi, quoi, ce qui reste), comme `docs/lot9.md` et `docs/lot10.md`.
- `docs/lot8.md`, 11.1 : trois reprises, que Julien valide avec cette conception. Un agent n'a pas d'état « brouillon » (décision 10). Le groupe reste hors de la configuration, comme l'apparence (décision 8). L'accueil peut être tenu par n'importe quel agent, au lieu de rester à un agent fixe (décision 12).
- `clients/exemple.yaml` : une équipe en exemple, commentée.

## Ce qui reste au constructeur

- Le texte exact de la phrase d'identité d'un membre et des listes de règles, tant que celles des agents de l'accueil ne bougent pas.
- La forme de la fonction `cle` et de ce qu'elle rend, tant que l'accueil garde la personne seule.
- La liste exacte des réglages d'accueil refusés sans agent d'accueil, à partir de celle de la section 1.
- La façon de filtrer les passages par document dans `Base.chercher`.
- Le nom des compteurs du plafond et leur place dans `noyau/garde.py`.
- Le découpage en commits, et l'ordre : la configuration et l'accueil, la construction, le tour, la base et les documents, l'atelier, la garde des images.

## Ce qui a été écarté

- **Un conteneur par agent.** Quinze conteneurs et quinze bases par entreprise ; chaque zone n'en fait tourner que 50 à la fois ; les agents ne partageraient ni documents ni mémoire.
- **Un agent d'accueil fixe, toujours présent**, écrit en haut de la configuration (la première version de cette conception). Il fallait alors créer chaque entreprise avec un agent, et le numéro ne pouvait aller qu'à lui : contraire aux décisions 10 et 12.
- **Déplacer l'agent en haut de la configuration quand il prend l'accueil**, au lieu de le désigner. Le moteur n'aurait rien eu à lire de nouveau, mais l'atelier aurait eu deux endroits où chercher un même agent selon le jour.
- **`agno.team` comme socle de l'équipe.** Ses modes (`coordinate`, `route`, `broadcast`, `tasks`) font passer chaque message par un agent chef qui délègue. Ici, le patron choisit lui-même à qui il parle : un chef ajouterait un appel de modèle à chaque tour, et brouillerait la règle « un seul agent écrit et agit à la fois ». À réévaluer pour les conversations à plusieurs (11.7).
- **La pause par un réglage à chaud** (une table lue à chaque tour). Il y aurait deux vérités sur l'état d'un agent : la configuration et la table. Le rechargement à chaud de la section 8 garde la configuration pour seule vérité.
- **Une configuration par fichier ou lue à la porte au démarrage**, pour lever la limite de taille. À reprendre si 100 000 octets ne suffisent pas.

## Ce qui reste après ce lot

- L'entrée AG-UI vers un membre et l'historique d'une conversation (11.2), avec ce que la section 3 lui demande de reprendre.
- Relier un compte de la console à un client de l'atelier ; et dire qui crée le client (sa base, ses secrets) quand une PME s'inscrit seule, comme la console le permet aujourd'hui.
- Où tourne le serveur de la console. Il relaie la conversation (CopilotKit) : pour un client en zone suisse ou une installation chez lui, le principe du plan (« le contenu ne passe pas par l'atelier ») vaut aussi pour ce serveur.
- Le catalogue et le banc par métier (11.3).
- « Brancher WhatsApp » en un clic par le client (11.6, 8.7), sur le chemin de l'essai.
- Mettre en pause l'agent qui tient l'accueil, une fois décidé ce que reçoit le client.
- Un nombre de membres selon l'offre du client (la facturation, hors du plan).
- Le suivi des volumes et des coûts par agent (8.6, 8.9) : les tours d'Agno portent déjà l'identifiant de l'agent.
- Retirer l'ancienne écriture de l'agent d'accueil (approche B), quand plus aucun client ne l'emploiera.
