# NexCall AI v4 → v5 — Plateforme generique + IA multi-fournisseurs + design clair

## Resume

Cette version transforme NexCall AI en **plateforme generique de campagnes d'appels**
(plus seulement mutuelle), rend le **fournisseur IA flexible** (OpenAI, Anthropic,
Mistral ou endpoint compatible), et refait entierement l'interface en **style telecom
SaaS clair (Keyyo)**. Tout reste en francais.

**Aucune fonctionnalite supprimee.**

---

## 1. Modele Agent — nouveaux champs

| Champ | Role |
|-------|------|
| `ai_provider` | Fournisseur IA : `openai` (defaut), `anthropic`, `mistral`, `custom` |
| `ai_model` | Nom du modele (ex: `gpt-4o`, `claude-sonnet-4-5`, `mistral-large-latest`) |
| `ai_temperature` | Temperature de generation (0–1, defaut 0.7) |

**IMPORTANT** : le schema a change. En developpement SQLite :

```bash
rm nexcall.db
python -m uvicorn main:app --reload
```

## 2. Agents generiques par defaut

Les 3 agents crees au premier demarrage ne sont plus orientes mutuelle :

- **Agent Resiliation** — appelle les personnes ayant demande une resiliation.
- **Agent Relance Client** — relance les dossiers/devis en attente.
- **Agent Commercial** — presente une offre et qualifie les prospects.

Chaque agent a son propre script, ses regles, son contexte, son fournisseur/modele IA.
De nouveaux types de service generiques sont disponibles : `resiliation`,
`relance_client`, `commercial`, `sondage`, `prise_rdv` (les types assurance restent).

## 3. Fournisseur IA flexible

- `app/services/ai_agent.py` route desormais selon `agent.ai_provider` :
  - `openai` / `mistral` / `custom` → SDK OpenAI (avec `base_url` adapte).
  - `anthropic` → SDK Anthropic (`messages.create`, system separe).
- Repli automatique sur OpenAI si le fournisseur demande n'est pas configure.
- Cles dans `.env` (toutes optionnelles sauf celle reellement utilisee) :
  `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `MISTRAL_API_KEY`,
  `CUSTOM_AI_BASE_URL` + `CUSTOM_AI_API_KEY`.
- Choix du fournisseur/modele dans **Parametres IA** et a la creation d'agent.

## 4. Import contacts

- Telephone = seul champ obligatoire. Nom, prenom, date de naissance, ville,
  informations = optionnels. L'import par numeros seuls fonctionne.
- Deux modes : fichier CSV, ou collage de numeros (un par ligne).

## 5. Creation de campagne

- On selectionne l'agent IA, puis on importe la liste de contacts dans la campagne.
- La campagne utilise uniquement l'agent choisi (script/regles/fournisseur de cet agent).

## 6. Tableau de bord resultats

- 7 indicateurs : total contacts, appeles, interesses, sans reponse, transferes,
  refuses, liste rouge. Filtre par campagne + export CSV.
- Endpoints : `GET /api/analytics/campagne`, `GET /api/analytics/campagne/export`.

## 7. Nouveau design (style telecom Keyyo)

- Theme **clair professionnel** : fond gris tres clair, cartes blanches a ombres
  douces, accent bleu telecom, navigation epuree.
- Tout passe par les variables CSS de `base.html` : l'ensemble de l'app est transforme.

## 8. Workflow d'appel (inchange, conserve)

- Sonnerie 45 s, sans reponse → "ne repond pas", enchainement automatique.
- Transfert vers conseiller humain sur demande du client.
- "Ne m'appelez plus" → ajout liste rouge + statut do_not_call.

---

## Test runtime

Le sandbox de developpement n'ayant pas d'acces reseau, l'application doit etre
lancee dans votre environnement :

```bash
pip install -r requirements.txt
cp .env.example .env   # renseignez au moins OPENAI_API_KEY et RINGOVER_API_KEY
rm -f nexcall.db
python -m uvicorn main:app --reload
```

Puis ouvrez http://127.0.0.1:8000
