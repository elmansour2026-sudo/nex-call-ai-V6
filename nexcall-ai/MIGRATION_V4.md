# NexCall AI v3 → v4 — Migration (Interface FR + Dashboard telecom)

## Resume

Cette version finalise la francisation de l'interface, ajoute un tableau de bord
professionnel facon telecom (style Keyyo), un import rapide par numeros, une page
dediee de parametrage de l'agent IA, et l'enchainement automatique des appels.

**Aucune fonctionnalite supprimee.**

---

## 1. Modele modifie

| Modele | Changement |
|--------|-----------|
| `Agent` | + `rules` (Text) : regles que l'IA doit suivre, une par ligne, injectees dans le prompt systeme |

**IMPORTANT** : le schema a change (nouvelle colonne `rules`). En developpement SQLite :

```bash
rm nexcall.db
python -m uvicorn main:app --reload
```

Les 6 agents par defaut sont recrees avec des regles type mutuelle pre-remplies.

## 2. Interface en francais

- Sidebar : Tableau de bord, Contacts, Agents IA, Editeur de script, Parametres IA,
  Campagnes, Appels, Statistiques, Suivi commercial, Prospects qualifies, Liste rouge,
  Configuration.

## 3. Tableau de bord (style telecom / Keyyo)

- Nouveau `dashboard.html` : bandeau KPI, cartes resultats, repartition en barres,
  tableau des campagnes, filtre par campagne, bouton d'export.
- 7 indicateurs metier : Total contacts, Appeles, Interesses, Sans reponse,
  Transferes conseiller, Refuses, Liste rouge.

## 4. Endpoints analytics ajoutes

- `GET /api/analytics/campagne?campaign_id=` — les 7 indicateurs + taux contact/interet
- `GET /api/analytics/campagne/export?campaign_id=` — export CSV de la synthese

## 5. Import contacts simplifie

- Onglet "Coller des numeros" : un numero par ligne, telephone seul suffit.
- Endpoint `POST /api/contacts/import-numbers` (numbers[], campaign_id?, agent_id?).
- L'import CSV reste disponible ; seul le telephone est obligatoire.

## 6. Page Parametres IA (`/agent-settings`)

- Choix de l'agent, edition de l'intro et du script systeme.
- Champ "Regles a respecter" dedie (une par ligne) + bouton "regles type mutuelle".
- Numero de transfert conseiller, bouton de test en direct.

## 7. Workflow d'appel

- Sonnerie 45 s (`ring_timeout`), sans reponse -> statut "ne repond pas" (retry).
- Enchainement automatique : a la fin de chaque appel sortant d'une campagne active,
  `launch_next` appelle le prospect suivant (saute liste rouge et tentatives max).
- Transfert humain : sur "un conseiller / une personne / parler a quelqu'un".
- "Ne m'appelez plus" -> ajout liste rouge + statut do_not_call.
