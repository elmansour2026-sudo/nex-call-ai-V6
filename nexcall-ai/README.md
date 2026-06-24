# 📞 NexCall AI v3

**Plateforme SaaS de centre d'appels IA — specialisee mutuelle / resiliation.**
Ringover + OpenAI GPT-4o.

> Relance de clients resilies · 6 agents IA · Contacts & 10 statuts metier · Script Builder
> · Import CSV enrichi · Blacklist Do-Not-Call · Transfert humain · Analytics · CRM Pipeline

---

## ⚡ Demarrage rapide

```bash
cd nexcall-ai
pip install -r requirements.txt
cp .env.example .env      # configurez OPENAI_API_KEY et RINGOVER_API_KEY
rm -f nexcall.db          # IMPORTANT si vous venez de la v2 (schema modifie)
python -m uvicorn main:app --reload
```

Dashboard : **http://127.0.0.1:8000**
API docs  : **http://127.0.0.1:8000/docs**

Un fichier `exemple_contacts.csv` est fourni pour tester l'import.

---

## 🗂 Nouveautes v3 (specialisation mutuelle)

- **Page Contacts** — table centrale des clients resilies : nom, telephone, date de
  resiliation, ancienne offre, notes, dernier appel, tentatives, statut. Recherche,
  filtres (statut / campagne / agent), pagination, export CSV.
- **10 statuts metier** — Nouveau, En attente, Appele, Interesse, Pas interesse,
  Ne repond pas, A rappeler, Transfere conseiller, Refus definitif, Do not call.
- **Import CSV enrichi** — verifie doublons, numeros invalides, et bloque les numeros
  en liste noire. Affiche : importes / doublons / invalides / blacklists.
- **Script Builder** — editeur structure (introduction, qualification, objections,
  proposition d'offre, fermeture) avec variables {{'{{'}}nom{{'}}'}}, {{'{{'}}age{{'}}'}},
  {{'{{'}}ancienne_offre{{'}}'}}, {{'{{'}}date_resiliation{{'}}'}}.
- **Blacklist / Do Not Call** — page dediee ; auto-ajout quand le client dit
  "ne m'appelez plus" ; respectee a chaque import et avant chaque appel.
- **Transfert humain** — sur "je veux parler a un conseiller / une personne".
- **Retry system** — appel sans reponse -> statut "ne repond pas", rappel jusqu'a
  max_attempts ; horaires d'appel autorises par campagne.
- **Analytics** — total appels, repondus, sans reponse, interesses, refus, transferts,
  blacklist, duree moyenne, taux de reponse et de transfert, performance par agent.

Voir `MIGRATION_V3.md` pour le detail technique complet.

---

## 🔄 Heritage v2 (conserve)

| Agent | Service | Voix |
|-------|---------|------|
| Sophie | 💊 Mutuelle Sante | Nova |
| Thomas | 🚗 Assurance Auto | Echo |
| Chloe | 🏠 Assurance Habitation | Shimmer |
| Antoine | 🛡️ Assurance Prevoyance | Onyx |
| Marc | 🏗️ Assurance Decennale | Fable |
| Lea | 🏍️ Assurance Moto | Alloy |

---

## 🗂 Nouveautes v2

- **Agents IA multiples** — chaque service a son commercial virtuel (prompt, voix, ton, numero dedie)
- **Campagnes outbound** — import CSV de prospects, lancement automatique des appels
- **Qualification structuree** — intent (interested/not_interested/callback/wrong_number) + score 0-100
- **CRM Pipeline** — vue Kanban des leads (Nouveau → Appele → Interesse → RDV → Converti)
- **L'IA se presente toujours comme une IA** — jamais d'usurpation d'identite humaine

Voir `MIGRATION_V2.md` pour le detail complet des changements techniques.

---

## 🗂 Architecture

```
nexcall-ai/
├── main.py
├── requirements.txt
├── MIGRATION_V2.md          ← Guide de migration v1→v2
│
├── app/
│   ├── config.py
│   ├── database.py
│   │
│   ├── models/
│   │   ├── agent.py          ★ NOUVEAU — Agent IA
│   │   ├── prospect.py       ★ NOUVEAU — Prospect campagne
│   │   ├── qualification.py  ★ NOUVEAU — Analyse IA post-appel
│   │   ├── call.py           (mis a jour: +agent_id, +prospect_id)
│   │   ├── campaign.py       (mis a jour: +agent_id, +scheduled_at)
│   │   └── lead.py
│   │
│   ├── services/
│   │   ├── agent_service.py     ★ NOUVEAU — 6 prompts par defaut
│   │   ├── outbound_service.py  ★ NOUVEAU — Import CSV, lancement
│   │   ├── ai_agent.py          (mis a jour: multi-agents)
│   │   ├── ringover_service.py  (mis a jour: appels sortants)
│   │   ├── ivr_service.py
│   │   └── lead_service.py
│   │
│   ├── routers/
│   │   ├── agents.py         ★ NOUVEAU
│   │   ├── prospects.py      ★ NOUVEAU
│   │   ├── pages.py          (mis a jour: nouvelles routes)
│   │   ├── webhooks.py       (mis a jour: outbound + qualification)
│   │   ├── calls.py          (mis a jour: simulate avec agent_id)
│   │   ├── campaigns.py      (mis a jour)
│   │   ├── leads.py
│   │   └── configuration.py
│   │
│   └── templates/
│       ├── agents.html        ★ NOUVEAU
│       ├── agent_detail.html  ★ NOUVEAU
│       ├── campaigns_v2.html  ★ NOUVEAU (remplace campaigns.html)
│       ├── prospects.html     ★ NOUVEAU
│       ├── crm.html           ★ NOUVEAU
│       ├── base.html          (design SaaS pro repense)
│       ├── dashboard.html     (vue multi-agents)
│       ├── calls.html
│       ├── leads.html
│       └── configuration.html
```

---

## 🤖 Fonctionnement multi-agents

```
1. Admin cree une campagne "Prospects Mutuelle Mars"
   → choisit l'agent Sophie (Mutuelle Sante)
   → importe 500 prospects via CSV
       |
2. Clique "Lancer" → le systeme appelle les 3 premiers (max_concurrent)
       |
3. Prospect repond → webhook /outbound-answered
   → Sophie se presente : "Bonjour M. Dupont, je suis Sophie,
      l'assistante IA de AssurancePro..."
       |
4. Conversation naturelle → webhook /speech a chaque tour
   → GPT-4o suit le script Mutuelle Sante, pose les questions
   → extrait <QUALIFICATION> : intent, score, besoin, budget
       |
5. Score >= seuil (70) → transfert automatique vers conseiller humain
   Sinon → fin d'appel propre
       |
6. Qualification sauvegardee en base + lead cree/mis a jour
   Visible immediatement dans /crm (pipeline) et /leads
```

---

## 📋 Import CSV — Format attendu

```csv
nom,prenom,telephone,date_naissance,ville,informations
Dupont,Jean,0612345678,15/03/1985,Paris,Client fidele depuis 2020
Martin,Sophie,0698765432,22/07/1990,Lyon,
```

Colonnes acceptees (insensibles a la casse) : `nom`, `prenom`, `telephone`/`tel`,
`email`, `date_naissance`/`naissance`, `ville`, `informations`/`info`/`notes`.

---

## 📦 Stack technique

Backend FastAPI async · SQLAlchemy 2.x · SQLite/PostgreSQL · OpenAI GPT-4o + TTS + Whisper
· Ringover API v2 (inbound + outbound) · Jinja2 · Render (deploiement)

---

*NexCall AI v2.0.0*
