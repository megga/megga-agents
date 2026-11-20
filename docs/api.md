# Parler à un agent MEGGA depuis un logiciel

Pour le développeur d'un logiciel (dossier médical, site, application) qui veut envoyer un message à l'agent d'un client et recevoir sa réponse. Sans WhatsApp ni Meta.

## La requête

```bash
curl https://api.megga.ai/api/<client>/messages \
  -H "Authorization: Bearer $MEGGA_CLE" \
  -H "Content-Type: application/json" \
  -d '{"personne": "patient-42", "texte": "Bonjour, je voudrais déplacer mon rendez-vous."}'
```

```json
{"reponse": "Bonjour ! Bien sûr. Quel jour vous conviendrait ?"}
```

L'adresse :
- hébergé par MEGGA : `https://api.megga.ai/api/<client>/messages` (`<client>` : l'identifiant donné par MEGGA) ; en secours, `https://megga-agents.api-963.workers.dev/api/<client>/messages` ;
- installé chez le client : `https://<son-domaine>/api/messages`.

La réponse arrive dans la même requête, une fois le tour de l'agent fini : quelques secondes, parfois plus de 30. L'agent abandonne un tour au bout de 110 secondes (`503`, avec l'excuse) : prévoir un délai d'attente de 120 secondes.

## Les champs

- `personne` : l'identifiant de la personne dans votre logiciel, choisi par vous et stable. De 1 à 40 caractères (lettres, chiffres, `.`, `_`, `-`), avec au moins une lettre. **Jamais un numéro de téléphone** ni un nom : un identifiant opaque (`patient-42`, `u_8f3a2c`). L'agent se souvient de chaque personne d'une conversation à l'autre ; deux logiciels du même client ont chacun leurs personnes.
- `texte` : le message, de 1 à 4000 caractères. Rien d'autre dans le corps (16 Kio au plus).

La réponse est en texte, mise en forme comme sur WhatsApp (gras entre `*une étoile*`), sans tiret long. Une clé, un jeton ou une adresse de base qui apparaîtraient sont masqués.

## La clé

Une clé par logiciel, qui commence par `mga_`. Elle n'est montrée qu'une fois, à sa création : la garder dans un coffre, jamais dans le code ni dans une page web (un appel depuis un navigateur l'exposerait : passer par votre serveur).
- Hébergé par MEGGA : créée par MEGGA ou par le client dans l'atelier.
- Chez le client : créée sur son serveur, `docker compose exec agent python -m noyau.cles creer <logiciel>` (ou `kubectl exec`).

Une clé retirée cesse de servir tout de suite. Pour changer de clé sans coupure : créer la nouvelle sous le même nom de logiciel, la mettre en place, puis retirer l'ancienne. Le nom du logiciel, et non la clé, rattache les personnes : la mémoire suit.

## Les erreurs

Toujours en JSON : `{"erreur": "..."}`.

| Statut | Quand | Que faire |
|---|---|---|
| `400` | corps illisible, `personne` ou `texte` refusés | corriger la requête ; le message dit quel champ |
| `401` | clé absente, mal formée ou retirée | vérifier la clé |
| `404` | agent inconnu (hébergé par MEGGA) | vérifier l'identifiant du client |
| `411`, `413` | longueur non annoncée, corps de plus de 16 Kio | envoyer un corps entier, plus court |
| `429` | trop de messages : pour cette clé, ou pour cette personne | attendre `Retry-After` (en secondes, aussi dans `attente`), puis renvoyer |
| `503` | l'agent n'a pas pu répondre (`reponse` porte alors une excuse à montrer telle quelle), ou il est injoignable | réessayer plus tard, une fois |

## Les limites

- Par clé : 30 messages par minute par défaut ; MEGGA peut en régler davantage, jusqu'à 600.
- Par personne : 20 messages par 10 minutes, comme sur WhatsApp.
- Les messages d'une même personne passent l'un après l'autre : ne pas en envoyer un second avant la réponse au premier.
- Pas encore : les vocaux, la réponse au fil de l'eau, les rappels (l'agent dit qu'il ne peut pas en programmer ici).

## Les données

Les messages et la mémoire restent dans la base du client, dans sa zone (ou chez lui). Le texte part toutefois au fournisseur du modèle (Claude, chez Anthropic) pour chaque réponse : pour des données de santé, le client doit le savoir et l'accepter, ou demander à MEGGA un modèle par une voie qui lui convient. MEGGA voit dans sa console les volumes et la santé de l'agent, jamais les conversations : elles ne se lisent que par le client (décision du 20.11.2026).
