# Les appels WhatsApp (20.11.2026)

Greg appelle Alix sur WhatsApp et lui parle en direct. ElevenLabs décroche les appels du numéro d'Alix, et seulement les
appels : les messages restent à la plateforme. Une seule Alix, une seule mémoire (`noyau/appels.py`).

Décisions de Julien : Greg et Julien seulement au début, lecture seule pendant l'appel (lire, chercher, noter, envoyer),
le +1 650 actuel. Dix minutes au plus par appel.

## Le parcours d'un appel

1. **Au décrochage**, ElevenLabs appelle `POST /appels/<client>/debut` (porte), avec le numéro de l'appelant. Le conteneur
   répond qui c'est (gestionnaire, partenaire, visiteur, ou refusé), son prénom, ses rappels du jour, la conversation
   récente, la date du jour et l'accueil (« Salut Greg, c'est Alix. »). Les réglages de la gestion sont relus à chaque
   décrochage : un clic de Greg vaut pour l'appel suivant. Un appel refusé (un numéro bloqué, un visiteur quand seuls les
   gestionnaires peuvent appeler, les appels coupés dans la gestion, un numéro appelé qui n'est pas dans `appels.numeros`)
   entend le refus de la configuration (`appels.refus`), puis l'agent raccroche (soixante secondes au plus, le minimum
   d'ElevenLabs). Un appel permis ouvre les 24 heures de WhatsApp, comme un message.
2. **Pendant l'appel**, chaque outil de l'agent vocal est un webhook vers `POST /appels/<client>/outils/<nom>`. Le
   conteneur fait tourner l'outil d'Alix au nom de l'appelant (`system__caller_id`, que remplit ElevenLabs, jamais le
   modèle), vers un numéro d'`appels.numeros` (`system__called_number`). Seuls ceux d'`appels.OUTILS`, et seulement pour un
   gestionnaire. Rien n'écrase une donnée de la gestion : le propriétaire d'un bien et la recherche existante d'un client
   restent à l'écrit ; une recherche dictée se crée, les rappels et les souvenirs se notent. Un outil trop long n'est
   jamais annulé : il va au bout. Une fiche, des cartes ou une vidéo qui traînent continuent après la réponse ; un échec
   arrive par écrit.
3. **Après l'appel**, ElevenLabs envoie le texte à `POST /appels/<client>/fin`, signé. Le conteneur répond tout de suite,
   recalcule qui appelait (jamais le rôle que porte le webhook), puis : les répliques entrent au fil (genre `appel`), un
   résumé part à l'appelant sur WhatsApp (genre `resume_appel` ; hors des 24 heures, le modèle « message » l'annonce et il
   part au message suivant), l'appel est noté (table `megga_appels`) pour l'Activité de la gestion (`/site/journal`, clé
   `appels`), et le résumé reste deux jours dans le Contexte de l'écrit. Un traitement en échec se reprend au webhook
   suivant.

## Ce qui est réglé où

| Où | Quoi |
|---|---|
| `clients/four-seasons-properties.yaml`, `appels` | accepter, qui (`gestionnaires` ou `tous`), duree_max (dix minutes au plus), les numéros appelés permis, l'agent vocal, le refus |
| Gestion de Greg, Paramètres d'Alix, « Les appels » | `appels`, `appels_qui`, `appels_duree` (5 ou 10 minutes) : posés par-dessus la version (`packs/immobilier/reglages.py`) |
| Secrets du conteneur | `APPELS_CLE` (la clé du début et des outils), `APPELS_SIGNATURE` (le secret du webhook de fin) |
| ElevenLabs | l'agent `agent_5101m7v709c4fdnrj1grysk9pr93`, le secret `fsp_appels_cle` (« Bearer <APPELS_CLE> »), les 21 outils, le webhook de début propre à l'agent |

Les outils d'ElevenLabs se tirent du code d'Alix, pour que la voix et l'écrit aient les mêmes :

```bash
.venv/bin/python scripts/appels_outils.py four-seasons-properties https://megga-agents.api-963.workers.dev <secret_id> > outils.json
```

Un outil d'Alix qui change (paramètre, description) : régénérer, puis mettre à jour l'outil du même nom chez ElevenLabs.

## Mise en service

1. **Déployer** (seulement sur « Fusionne et déploie » de Julien) : l'image et la porte, puis `scripts/apres_deploiement.sh`.
2. **La version de la configuration** avec `appels` mise en service dans l'atelier.
3. **Le webhook de fin** : Julien le crée dans ElevenLabs (Agents, Settings, Webhooks), adresse
   `https://megga-agents.api-963.workers.dev/appels/four-seasons-properties/fin`, signature HMAC ; il copie le secret.
   Claude le relie à l'agent seul (`platform_settings.workspace_overrides.webhooks.post_call_webhook_id`, événement
   `transcript`).
4. **Les secrets** : `scripts/secrets_appels.sh four-seasons-properties https://megga-agents.api-963.workers.dev`
   (la clé vient du trousseau, le secret de signature se colle masqué ; le conteneur redémarre). Vérifier qu'il démarre.
5. **Le numéro de test** (+1 555-141-7274) relié à l'agent, puis un appel de Julien. Puis le +1 650 de Greg (ci-dessous).

## Le banc d'appels

Dix essais attachés à l'agent vocal (`agents_run_attached_tests`), rejoués à chaque changement du prompt ou des outils :
sept réponses jugées (chercher à Cologny sous vingt millions, un rappel lundi à neuf heures, un prix ne se change pas au
téléphone, un appel refusé ne reçoit rien, toujours « Greg » en tutoyant, un appelant anglophone, trois biens au plus à
l'oral) et trois conversations simulées, outils factices (l'appel type de Greg, Greg qui veut modifier pendant l'appel,
un visiteur anglophone). Ils coûtent des jetons du modèle, aucune minute d'appel. Côté plateforme,
`tests/test_appels.py` et `tests/test_appels_bout_en_bout.py` (un appel de Greg de bout en bout, vrais outils).

## Le numéro de Greg (+1 650 710 7070)

Seulement quand tout marche sur le numéro de test, et quand Julien le dit :

1. Limite de messages du numéro à 2 000 destinataires par jour au moins (WhatsApp Manager, le numéro, Limites) : Meta
   l'exige pour les appels (le 022, à 250, a été refusé : erreur #2593145).
2. « Autoriser les appels vocaux » (WhatsApp Manager, le numéro, Paramètres des appels).
3. Importer le numéro dans ElevenLabs (Julien, connexion Meta), le relier à l'agent, **messages coupés**
   (`enable_messaging` à faux) : les messages restent à la plateforme.
4. Aussitôt : un message de Greg arrive-t-il toujours à Alix (suivi du conteneur) ?

Un numéro des États-Unis ne peut pas appeler lui-même : Alix ne peut pas appeler Greg depuis le +1 650.
