# Les modèles WhatsApp de Four Seasons sur le socle

Un modèle Meta est le seul message permis hors des 24 heures. Ceux-ci remplacent, pour le socle, les modèles posés à la hâte pour Alix : un seul jeu, rédigé d'un bloc, sur le compte WhatsApp « Four Seasons Properties » (portefeuille MEGGA, branché sur l'app « Alix MEGGA »), celui du numéro de l'essai, +1 669 328 2299. Soumis à Meta le 16.11.2026.

## Les règles du jeu

- Toujours « Bonjour, » (ou « Bonjour {{1}}, » quand on a le nom), puis une phrase qui dit le fait, puis une phrase qui dit quoi faire.
- Le vouvoiement partout.
- Pour un visiteur ou un partenaire, l'expéditeur se nomme « Four Seasons Properties ».
- Un bouton seulement quand quelque chose attend : il s'appelle par ce qu'on reçoit (« Lire le message », « Voir la demande »). Sans rien qui attende, la dernière phrase invite à répondre ici.
- Une variable ne porte jamais de retour à la ligne ; ni point médian, ni tiret long.
- Les noms commencent par `fsp_socle_`.

## Le jeu

| Usage du socle | Nom | Pour | Texte | Bouton |
|---|---|---|---|---|
| `message` (le repli de tous) | `fsp_socle_attente` | tous | Bonjour, {{1}} a une mise à jour concernant votre échange en cours. Touchez le bouton pour l'afficher. | Afficher |
| `message_en` | `fsp_socle_attente` (en) | tous | Hello, {{1}} has an update on your ongoing conversation. Tap the button to view it. | View |
| `rappel` | `fsp_socle_rappel_2` | le gestionnaire | Bonjour, voici le rappel que vous avez programmé : {{1}}. Répondez ici pour le traiter. | |
| `demande` | `fsp_socle_demande_2` | le gestionnaire | Bonjour, une demande d'information est arrivée pour votre agence.<br>Objet : {{1}}<br>De : {{2}}<br>Contact : {{3}}<br>Touchez le bouton pour la voir en entier. | Voir la demande |
| `partenaire` | `fsp_socle_partenaire_2` | le gestionnaire | Bonjour, {{1}}, partenaire de votre réseau, vous adresse une demande pour un client ({{2}}). Touchez le bouton pour y répondre. | Répondre |
| `veille`, `zone`, `rapprochement` | `fsp_socle_suivi_maj` | le gestionnaire | Bonjour, voici la mise à jour d'un de vos suivis : {{1}}. Touchez le bouton pour voir le détail. | Voir le détail |
| `livraison` | `fsp_socle_livraison` | un partenaire | Bonjour, Four Seasons Properties a répondu à votre demande : la référence {{1}}. Touchez le bouton pour recevoir le dossier. | Recevoir le dossier |
| `reponse_visiteur` | `fsp_socle_reponse` | un visiteur | Bonjour, Four Seasons Properties vous a répondu : « {{1}} ». Touchez le bouton pour lire la réponse en entier. | Lire la réponse |
| `reponse_visiteur_en` | `fsp_socle_reponse` (en) | un visiteur | Hello, Four Seasons Properties has replied to you: “{{1}}”. Tap the button to read the full reply. | Read the reply |
| `suivi_visiteur` | `fsp_socle_suivi` | un visiteur | Bonjour, Four Seasons Properties a bien reçu votre demande concernant {{1}}. Nous revenons vers vous très vite. Répondez ici si vous souhaitez ajouter quelque chose. | |
| `suivi_visiteur_en` | `fsp_socle_suivi` (en) | un visiteur | Hello, Four Seasons Properties has received your enquiry about {{1}}. We will get back to you very soon. Reply here if you would like to add anything. | |
| `ouverture` | `fsp_socle_ouverture` | un contact | Bonjour {{1}}, Four Seasons Properties souhaite vous transmettre {{2}}. Touchez le bouton pour le recevoir. | Recevoir |
| `ouverture_en` | `fsp_socle_ouverture` (en) | un contact | Hello {{1}}, Four Seasons Properties would like to send you {{2}}. Tap the button to receive it. | Receive |

Ce que valent les variables, par exemple :
- `message` : le nom de l'agent, « Alix » ;
- `rappel` : « appeler M. Martin pour la villa de Cologny » ;
- `demande` : « information sur la villa MBOL-1E00 à Marbella », « Jeanne Martin », « jeanne@exemple.ch, +41 79 123 45 67 » ; ou « nouveau contact (acheteur) », « Marc Dupont », « +41 79 111 22 33 par WhatsApp » ; ou « question « le prix est-il négociable ? » », « un visiteur », « +971 50 123 4567 par WhatsApp » ;
- `partenaire` : « Marc Dupont (Riviera Immobilier) », « G8LR-2DW8 et MBOL-1E00 » ;
- `suivi_maj` : « 3 nouvelles annonces pour la veille villas à Cologny », « le suivi Marbella, villas se termine aujourd'hui », « le bien « Villa avec vue » pourrait intéresser un client » ;
- `livraison` : « G8LR-2DW8 » ; `reponse` : le début de la réponse ; `suivi` : « la villa MBOL-1E00 à Marbella » ; `ouverture` : « Marie Dupont », « une annonce ».

L'anglais sert quand le socle connaît la langue de la personne : le suivi, le premier contact, la réponse à une question, et le message en attente qui les annonce. Tout ce qui va au gestionnaire reste en français ; le dossier d'un partenaire aussi (sa langue n'est pas gardée).

Catégorie : utilitaire pour tous, sauf `ouverture` (un premier message à un contact) déclaré marketing, comme Meta l'a classé pour Alix. Le premier jeu (16.11.2026) a vu six modèles reclassés en marketing par Meta (`message`, `rappel`, `demande`, `partenaire`, `nouveau`) : ils ont été réécrits pour dire la démarche précise de la personne (son échange en cours, son rappel programmé, une demande pour son agence, un de ses suivis), soumis sous de nouveaux noms, et les anciens supprimés. Une règle pour la suite : un modèle utilitaire nomme toujours ce que la personne a demandé ou ce qui la concerne, jamais un « nouveau message » vague.
