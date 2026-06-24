# Correctif — La config UI (OpenAI / Ringover) reste "Non configuré" apres Sauvegarde

## Cause racine

Le statut etait calcule uniquement a partir des variables d'environnement
(`settings.is_openai_configured` / `settings.is_ringover_configured`), lues une
seule fois au demarrage. Les cles saisies via l'interface etaient bien
enregistrees en BDD (table `configurations`), mais :
- l'endpoint `/api/config/status` ne lisait jamais la BDD ;
- les services (`AIAgentService`, `RingoverService`) gardaient en cache un client
  cree avec l'ancienne cle (ou aucune).

## Corrections apportees

### 1. Nouveau service `app/services/config_service.py`
- `get_value(db, key)` : renvoie la valeur effective d'une cle — **BDD prioritaire**,
  repli sur `settings` (.env). Ignore les valeurs masquees `***`.
- `is_openai_configured(db)` / `is_ringover_configured(db)` : bases sur la BDD.
- `apply_to_services(db)` : pousse les cles actives dans les services en cours
  d'execution (sans redemarrage).

### 2. `app/routers/configuration.py`
- `/status` interroge desormais la **BDD d'abord**, puis `settings` (point 1 & 3).
- `POST /api/config` :
  - enregistre les cles en BDD (inchange) ;
  - appelle `config_service.apply_to_services(db)` pour mettre a jour les clients
    a chaud (point 2) ;
  - renvoie directement le `status` recalcule, pour que l'UI passe au vert
    immediatement.
- `/test-ringover` applique la cle active avant le test.

### 3. Services rendus dynamiques
- `RingoverService.set_api_key(key)` : met a jour la cle a chaud.
- `AIAgentService.set_api_key(key)` : met a jour la cle et **invalide le cache**
  des clients (recrees avec la nouvelle cle). `_get_client()` utilise la cle
  effective (`override` BDD, sinon `.env`).

### 4. Demarrage (`main.py`)
- Au boot, `config_service.apply_to_services(db)` charge la config BDD dans les
  services. Donc apres un redemarrage, les cles saisies via l'UI restent actives.

### 5. Interface (`configuration.html`)
- Apres sauvegarde, le statut renvoye par l'API est affiche immediatement
  (`renderStatus`). Message "Redemarrez le serveur" supprime (plus necessaire).

## Resultat

Coller la cle OpenAI / Ringover -> Sauvegarder -> le badge passe a **✓ Configuré**
(vert) instantanement, sans redemarrage. Ringover affiche "Connecté" si la cle est
valide, sinon "Non joignable" (cle presente mais API injoignable).

## Comportement de repli (point 3)
Si aucune valeur en BDD pour une cle, le systeme utilise `settings.OPENAI_API_KEY`
/ `settings.RINGOVER_API_KEY` (.env). Les deux sources fonctionnent.
