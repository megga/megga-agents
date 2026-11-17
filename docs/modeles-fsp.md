# Les modèles WhatsApp de Four Seasons sur le socle

Un modèle Meta est le seul message permis hors des 24 heures. Ceux-ci remplacent, pour le socle, les modèles posés à la hâte pour Alix : un seul jeu, rédigé d'un bloc, sur le compte WhatsApp « FSP » (portefeuille MEGGA), celui du +1 650-710-7070, le numéro d'Alix, que le socle sert depuis la bascule du 16.11.2026. Le même jeu existe sous les noms `fsp_socle_` sur le compte « Four Seasons Properties » du +1 669 328 2299, le numéro de l'essai, rendu à MEGGA.

## Les règles du jeu

- Toujours « Bonjour, » (ou « Bonjour {{1}}, » quand on a le nom), puis une phrase qui dit le fait, puis une phrase qui dit quoi faire.
- Le vouvoiement partout.
- Pour un visiteur ou un partenaire, l'expéditeur se nomme « Four Seasons Properties ».
- Un bouton seulement quand quelque chose attend : il s'appelle par ce qu'on reçoit (« Lire le message », « Voir la demande »). Sans rien qui attende, la dernière phrase invite à répondre ici.
- Une variable ne porte jamais de retour à la ligne ; ni point médian, ni tiret long.
- Les noms commencent par `fsp_agent_`.

## Le jeu

| Usage du socle | Nom | Pour | Texte | Bouton |
|---|---|---|---|---|
| `message` (le repli de tous) | `fsp_agent_attente` | tous | Bonjour, {{1}} a une mise à jour concernant votre échange en cours. Touchez le bouton pour l'afficher. | Afficher |
| `message_en` | `fsp_agent_attente` (en) | tous | Hello, {{1}} has an update on your ongoing conversation. Tap the button to view it. | View |
| `rappel` | `fsp_agent_rappel` | le gestionnaire | Bonjour, voici le rappel que vous avez programmé : {{1}}. Répondez ici pour le traiter. | |
| `demande` | `fsp_agent_demande` | le gestionnaire | Bonjour, une demande d'information est arrivée pour votre agence.<br>Objet : {{1}}<br>De : {{2}}<br>Contact : {{3}}<br>Touchez le bouton pour la voir en entier. | Voir la demande |
| `partenaire` | `fsp_agent_partenaire` | le gestionnaire | Bonjour, {{1}}, partenaire de votre réseau, vous adresse une demande pour un client ({{2}}). Touchez le bouton pour y répondre. | Répondre |
| `veille`, `zone`, `rapprochement` | `fsp_agent_suivi_maj` | le gestionnaire | Bonjour, voici la mise à jour d'un de vos suivis : {{1}}. Touchez le bouton pour voir le détail. | Voir le détail |
| `livraison` | `fsp_agent_livraison` | un partenaire | Bonjour, Four Seasons Properties a répondu à votre demande : la référence {{1}}. Touchez le bouton pour recevoir le dossier. | Recevoir le dossier |
| `reponse_visiteur` | `fsp_agent_reponse` | un visiteur | Bonjour, Four Seasons Properties vous a répondu : « {{1}} ». Touchez le bouton pour lire la réponse en entier. | Lire la réponse |
| `reponse_visiteur_en` | `fsp_agent_reponse` (en) | un visiteur | Hello, Four Seasons Properties has replied to you: “{{1}}”. Tap the button to read the full reply. | Read the reply |
| `suivi_visiteur` | `fsp_agent_suivi` | un visiteur | Bonjour, Four Seasons Properties a bien reçu votre demande concernant {{1}}. Nous revenons vers vous très vite. Répondez ici si vous souhaitez ajouter quelque chose. | |
| `suivi_visiteur_en` | `fsp_agent_suivi` (en) | un visiteur | Hello, Four Seasons Properties has received your enquiry about {{1}}. We will get back to you very soon. Reply here if you would like to add anything. | |
| `ouverture` | `fsp_agent_ouverture` | un contact | Bonjour {{1}}, Four Seasons Properties souhaite vous transmettre {{2}}. Touchez le bouton pour le recevoir. | Recevoir |
| `ouverture_en` | `fsp_agent_ouverture` (en) | un contact | Hello {{1}}, Four Seasons Properties would like to send you {{2}}. Tap the button to receive it. | Receive |
| `transfert` | `fsp_agent_transfert` | le gestionnaire | Bonjour, {{1}} vous transmet une conversation qui demande l'attention de l'équipe : {{2}}. Touchez le bouton pour la voir et la prendre en charge. | Voir la conversation |
| `reprise` | `fsp_agent_reprise` | un visiteur | Bonjour, un membre de l'équipe de Four Seasons Properties vous a répondu au sujet de votre échange avec {{1}}. Touchez le bouton pour lire sa réponse. | Lire la réponse |
| `reprise_message` | `fsp_agent_reprise_message` | le gestionnaire | Bonjour, {{1}} vous a écrit dans la conversation que vous avez prise en charge. Touchez le bouton pour lire son message. | Lire le message |
| `approbation` | `fsp_agent_approbation` | le gestionnaire | Bonjour, {{1}} attend votre accord avant de faire une action pour une personne qui lui a écrit : {{2}}. Touchez le bouton pour voir la demande et y répondre. | Voir la demande |
| `approbation_reponse` | `fsp_agent_approbation_reponse` | la personne | Bonjour, l'équipe a répondu à la demande que vous avez faite à {{1}}. Touchez le bouton pour lire sa réponse. | Lire la réponse |

Ce que valent les variables, par exemple :
- `message` : le nom de l'agent, « Alix » ;
- `rappel` : « appeler M. Martin pour la villa de Cologny » ;
- `demande` : « information sur la villa MBOL-1E00 à Marbella », « Jeanne Martin », « jeanne@exemple.ch, +41 79 123 45 67 » ; ou « nouveau contact (acheteur) », « Marc Dupont », « +41 79 111 22 33 par WhatsApp » ; ou « question « le prix est-il négociable ? » », « un visiteur », « +971 50 123 4567 par WhatsApp » ;
- `partenaire` : « Marc Dupont (Riviera Immobilier) », « G8LR-2DW8 et MBOL-1E00 » ;
- `suivi_maj` : « 3 nouvelles annonces pour la veille villas à Cologny », « le suivi Marbella, villas se termine aujourd'hui », « le bien « Villa avec vue » pourrait intéresser un client » ;
- `transfert` : « Alix », « réclamation sur une visite » ; `reprise` : « Alix » ; `reprise_message` : « +41 79 123 45 67 » ;
- `livraison` : « G8LR-2DW8 » ; `reponse` : le début de la réponse ; `suivi` : « la villa MBOL-1E00 à Marbella » ; `ouverture` : « Marie Dupont », « une annonce ».

Les trois modèles du transfert vers un humain (lot 9.3) et les deux des approbations (lot 9.1) sont relus par Julien et soumis à Meta le 17.11.2026, en attente de son avis (utilitaires). `approbation` : le nom de l'agent, puis l'action demandée (« envoyer une fiche »). Le mot d'excuse quand personne de l'équipe n'a répondu à temps n'a pas de modèle propre : le repli `message` l'annonce.

L'anglais sert quand le socle connaît la langue de la personne : le suivi, le premier contact, la réponse à une question, et le message en attente qui les annonce. Tout ce qui va au gestionnaire reste en français ; le dossier d'un partenaire aussi (sa langue n'est pas gardée).

Catégorie : utilitaire pour tous, sauf `ouverture` (un premier message à un contact) déclaré marketing, comme Meta l'a classé pour Alix. Le premier jeu (16.11.2026) a vu six modèles reclassés en marketing par Meta (`message`, `rappel`, `demande`, `partenaire`, `nouveau`) : ils ont été réécrits pour dire la démarche précise de la personne (son échange en cours, son rappel programmé, une demande pour son agence, un de ses suivis), soumis sous de nouveaux noms, et les anciens supprimés. Une règle pour la suite : un modèle utilitaire nomme toujours ce que la personne a demandé ou ce qui la concerne, jamais un « nouveau message » vague.
