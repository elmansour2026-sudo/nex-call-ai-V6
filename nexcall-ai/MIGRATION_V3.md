# NexCall AI v2 → v3 — Migration (Specialisation Mutuelle / Resiliation)

## Resume

NexCall AI v3 specialise la plateforme dans la **relance de clients ayant resilie
leur mutuelle**. Une nouvelle page **Contacts** devient le centre de gestion, avec
10 statuts metier, import enrichi, blacklist Do-Not-Call, Script Builder et analytics.

**Aucune fonctionnalite v2 supprimee** : agents, campagnes, CRM, leads, appels restent.

---

## 1. Modeles

### Modifies
| Modele | Changement |
|--------|-----------|
| `Prospect` | + `resiliation_date`, `old_offer`, `notes`, `last_call_at`, `agent_id` ; `campaign_id` devient nullable ; **10 statuts metier** (nouveau, en_attente, appele, interesse, pas_interesse, ne_repond_pas, a_rappeler, transfere_conseiller, refus_definitif, do_not_call) |
| `Campaign` | + `call_hours_start`, `call_hours_end`, `transfer_number`, `max_attempts`, `ring_timeout` |

### Nouveaux
| Modele | Fichier | Role |
|--------|---------|------|
| `Blacklist` | `app/models/blacklist.py` | Numeros Do-Not-Call (bloques a l'import) |
| `CallScript` | `app/models/call_script.py` | Script structure (intro/qualif/objections/offre/fermeture) |

## 2. Services nouveaux
- `app/services/blacklist_service.py` — normalisation telephone, verif batch, ajout/retrait
- `app/services/contact_service.py` — import enrichi (dedup + invalides + blacklist), export CSV, filtres pagines, stats

## 3. Routers nouveaux
- `app/routers/contacts.py` — table principale, import/export, filtres, blacklist contact
- `app/routers/blacklist.py` — gestion Do-Not-Call
- `app/routers/scripts.py` — CRUD scripts + apercu variables
- `app/routers/analytics.py` — vue d'ensemble, par statut, par agent

## 4. Pages nouvelles
- `/contacts` — table des clients resilies (recherche, filtres statut/campagne/agent, pagination, export)
- `/scripts` — Script Builder
- `/analytics` — resultats des appels
- `/blacklist` — Do Not Call

## 5. Logique d'appel (webhooks)
- **Auto-blacklist** : si le client dit "ne m'appelez plus" (detection deterministe + LLM),
  le numero est ajoute a la blacklist et le contact passe en `do_not_call`.
- **Transfert humain** : si le client demande "un conseiller / une personne / parler a quelqu'un",
  transfert automatique vers le numero configure.
- **Retry** : un appel sans reponse passe le contact en `ne_repond_pas` ; il sera rappele
  jusqu'a `max_attempts` tentatives.
- **Blacklist respectee** : `launch_campaign` ne compose jamais un numero blacklists.

## 6. IMPORTANT — Base de donnees

Le schema a change (nouvelles colonnes + nouvelles tables). En developpement SQLite :

```bash
rm nexcall.db
python -m uvicorn main:app --reload
```

En production (PostgreSQL), ajoutez les colonnes via migration Alembic ou recreez le schema.

## 7. Format d'import CSV (Contacts)

```csv
nom,prenom,telephone,date_naissance,date_resiliation,ancienne_offre,informations_client
Dupont,Marie,0612345678,15/03/1968,15/01/2026,Formule Confort+,Cliente depuis 2015
```

A l'import : doublons ignores, numeros invalides rejetes, numeros blacklists bloques.
Le resultat affiche : importes / doublons / invalides / blacklists.
