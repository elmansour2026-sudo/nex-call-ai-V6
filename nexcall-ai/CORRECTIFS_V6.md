# NexCall AI — Correctifs & mode TEST

## 1. Correction du bug 500 (scheduled_at)

**Erreur** : `AttributeError: 'str' object has no attribute 'isoformat'` dans
`app/models/campaign.py` → `to_dict()`.

**Cause racine** : lors d'une modification de campagne, `update_campaign` faisait
`setattr(c, "scheduled_at", "2026-...")` avec la **chaine** recue, sans la convertir
en `datetime`. Ensuite `to_dict()` appelait `.isoformat()` sur une chaine → crash.

**Corrections (2 niveaux)** :
- `app/models/campaign.py` : helper `_iso()` defensif applique a tous les champs date
  (`scheduled_at`, `started_at`, `ended_at`, `created_at`). Accepte datetime, chaine
  ou None sans jamais planter.
- `app/routers/campaigns.py` : `update_campaign` convertit desormais `scheduled_at`
  en datetime via `_parse_dt()` avant l'enregistrement (correction de la cause racine).

## 2. Mode TEST / SIMULATION

- Nouveau champ **`test_phone_number`** sur la campagne (modele + formulaire).
- Nouveau bouton **« 🧪 Tester l'appel »** sur chaque carte de campagne.
- Endpoint : `POST /api/campaigns/{id}/test-call` (body optionnel `{test_phone_number}`).
- Service : `outbound_service.launch_test_call()` :
  - appelle directement le numero de test avec **l'agent IA configure** ;
  - si Ringover n'est **pas** configure → **mode simulation** : aucun appel reel,
    mais l'appel est **journalise** dans la table `calls` (statut completed +
    resume `[SIMULATION]`). Permet de valider que le flux fonctionne.
  - si Ringover est configure → appel reel via l'API.
- **Aucun blocage** si `WEBHOOK_SECRET` est absent (la validation de signature
  renvoie deja `True` quand le secret est vide).

## 3. Logique « Date de lancement »

- Champ date conserve, logique changee dans `create_campaign` :
  - date **future** (> 1 min) → campagne **programmee** (`scheduled`).
  - date **immediate / vide** → pas de programmation (`draft`, lancement direct).
- Nouvelle case **« Lancer maintenant »** dans le formulaire (ignore la date).

## 4. Migration automatique des colonnes (IMPORTANT pour Railway)

`app/database.py` ajoute desormais au demarrage les colonnes manquantes sur les
tables existantes (`test_phone_number`, `rules`, `ai_provider`, `ai_model`,
`ai_temperature`, ...). **Plus besoin de supprimer la base** en production
PostgreSQL : les colonnes sont ajoutees automatiquement, sans perte de donnees.

## Comment tester un premier appel

1. Deployer la nouvelle version (les colonnes manquantes seront ajoutees au boot).
2. Creer ou ouvrir une campagne, choisir un agent IA.
3. Renseigner le **Numero de telephone de test**.
4. Cliquer **« 🧪 Tester l'appel »**.
   - Sans Ringover : reponse `mode=simulation`, appel journalise → flux valide.
   - Avec Ringover : appel reel lance vers le numero.
5. Verifier le resultat dans la page **Appels** (l'appel de test y figure).
