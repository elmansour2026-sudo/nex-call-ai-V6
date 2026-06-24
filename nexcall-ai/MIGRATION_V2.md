# NexCall AI v1 → v2 — Guide de Migration

## Resume des changements

NexCall AI passe d'un systeme mono-agent a une plateforme **multi-agents IA**
capable de gerer 6 agents commerciaux specialises avec campagnes outbound.

---

## 1. Nouveaux modeles de donnees

| Modele | Fichier | Role |
|--------|---------|------|
| `Agent` | `app/models/agent.py` | Commercial IA specialise (nom, prompt, voix, numero) |
| `Prospect` | `app/models/prospect.py` | Personne dans une liste d'appels (import CSV) |
| `Qualification` | `app/models/qualification.py` | Analyse IA detaillee post-appel |

## 2. Modeles modifies

| Modele | Changement |
|--------|-----------|
| `Call` | + `agent_id`, `prospect_id` (FK) |
| `Campaign` | + `agent_id`, `scheduled_at`, `max_concurrent`, `total_prospects` |

**IMPORTANT** : Ces colonnes sont ajoutees via `init_db()` qui execute
`CREATE TABLE IF NOT EXISTS`. Si vous avez deja une base SQLite existante
avec l'ancien schema, **supprimez `nexcall.db`** avant de relancer pour
forcer la recreation complete (ou utilisez Alembic en production).

```bash
rm nexcall.db
python -m uvicorn main:app --reload
```

## 3. Nouveaux services

- `app/services/agent_service.py` — Gestion des agents + 6 prompts par defaut
- `app/services/outbound_service.py` — Import CSV, lancement campagnes, qualifications

## 4. Nouveaux routers

- `app/routers/agents.py` — CRUD agents + test + seed
- `app/routers/prospects.py` — CRUD prospects + import CSV + appel manuel

## 5. Nouvelles pages

- `/agents` — Liste et gestion des 6 agents IA
- `/agents/{id}` — Detail d'un agent (stats, prompt, config)
- `/campaigns` — Nouvelle interface (remplace l'ancienne campaigns.html)
- `/prospects` — Liste des prospects importes
- `/crm` — Pipeline visuel (Kanban) des leads

## 6. Premiere mise en route

```bash
pip install -r requirements.txt
cp .env.example .env   # configurer OPENAI_API_KEY et RINGOVER_API_KEY
python -m uvicorn main:app --reload
```

Au demarrage, **les 6 agents par defaut sont crees automatiquement**
(Sophie/Mutuelle, Thomas/Auto, Chloe/Habitation, Antoine/Prevoyance,
Marc/Decennale, Lea/Moto) si la table `agents` est vide.

## 7. Configurer un agent pour la telephonie

1. Aller sur `/agents`
2. Cliquer sur "Modifier" sur l'agent souhaite
3. Onglet "Telephonie" : renseigner le numero Ringover dedie et le
   numero de transfert humain
4. Sauvegarder

## 8. Lancer une campagne outbound

1. `/campaigns` → "+ Nouvelle campagne"
2. Choisir l'agent IA, le type "Sortant"
3. Sauvegarder, puis "📥 Import CSV" pour charger la liste de prospects
   (colonnes: nom, prenom, telephone, date_naissance, ville, informations)
4. Cliquer "🚀 Lancer" — le systeme appelle les N premiers prospects
   (max_concurrent) via Ringover

## 9. Compatibilite avec l'existant

- Les tables `calls`, `leads`, `campaigns` v1 restent fonctionnelles
- Le flux IVR inbound classique (touches 1/2/3) fonctionne toujours
- Le simulateur `/api/calls/simulate` accepte maintenant un `agent_id`
  optionnel pour tester un agent specifique
