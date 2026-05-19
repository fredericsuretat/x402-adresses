# x402 Adresses FR — Documentation complète

Service de validation d'adresses françaises monétisé via le protocole x402.
Les agents IA paient automatiquement en USDC (Base network) à chaque appel.

---

## Architecture

```
Agent IA
  → POST /validate  (sans paiement)
  ← HTTP 402 + instructions x402
  → POST /validate  (avec X-PAYMENT header)
  → Coinbase CDP Facilitator (vérification + règlement)
  ← HTTP 200 + résultat validation
  → USDC arrive sur 0x6458941857a70C6cA18c440a316035A21901A12b
```

**Stack :**
- Python 3.12 + FastAPI
- Base Adresse Nationale (BAN) — open data, gratuit
- Protocole x402 (Coinbase) — paiement HTTP automatique
- Hébergé sur Hugging Face Spaces (gratuit, toujours allumé)

**URLs :**
- Service public : `https://fredsuretat-x402-adresses.hf.space`
- Docs interactives : `https://fredsuretat-x402-adresses.hf.space/docs`
- Health : `https://fredsuretat-x402-adresses.hf.space/health`
- HF Space : `https://huggingface.co/spaces/fredsuretat/x402-adresses`

**Wallet :** `0x6458941857a70C6cA18c440a316035A21901A12b` (Base mainnet, USDC)  
→ Résolu depuis `fredericsuretat.cb.id` via ENS

**Prix :** `0.001 USDC` par validation (~$0.001)

---

## Développement local

```bash
cd /home/frederic/Documents/Dev/x402-adresses

# Première fois
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Démarrage
source .venv/bin/activate
uvicorn main:app --reload --port 8001
```

### Tester sans paiement (retourne 402 — normal)
```bash
curl -s -X POST http://localhost:8001/validate \
  -H "Content-Type: application/json" \
  -d '{"adresse": "15 rue de la paix paris"}' | python3 -m json.tool
```

---

## Déploiement Hugging Face Spaces

### Premier déploiement
```bash
cd /home/frederic/Documents/Dev/x402-adresses
git init
git add .
git commit -m "initial"
git remote add hf https://huggingface.co/spaces/fredsuretat/x402-adresses
git push hf main
```

### Mise à jour
```bash
cd /home/frederic/Documents/Dev/x402-adresses
git add .
git commit -m "description du changement"
git push https://fredsuretat:hf_TOKEN@huggingface.co/spaces/fredsuretat/x402-adresses main
```

> Le token HF se génère sur huggingface.co → Settings → Access Tokens → New token (Write)

### Variables d'environnement (HF Space Settings)
| Variable | Valeur | Note |
|---|---|---|
| `WALLET_ADDRESS` | `0x6458941857a70C6cA18c440a316035A21901A12b` | Hardcodé en fallback, secret optionnel |
| `PRICE_USDC` | `0.001` | Optionnel, défaut = 0.001 |

---

## Comment les agents paient

Le protocole x402 est standard HTTP :

1. L'agent appelle `POST /validate` sans header de paiement
2. Le serveur répond `HTTP 402` avec les instructions :
   ```json
   {
     "x402Version": 1,
     "accepts": [{
       "scheme": "exact",
       "network": "base",
       "maxAmountRequired": "0.001",
       "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
       "payTo": "0x6458941857a70C6cA18c440a316035A21901A12b"
     }]
   }
   ```
3. L'agent signe un transfert USDC EIP-3009 et renvoie la requête avec `X-PAYMENT` header
4. Le serveur vérifie + règle via `https://x402.org/facilitator`
5. L'agent reçoit la validation, l'USDC arrive sur le wallet

**Listing automatique :** Après le premier paiement réussi, le service apparaît automatiquement sur le Bazaar Coinbase (découverte par les agents).

---

## Monitoring

Le service est surveillé par le **URL Sentinel** du Control Center (CC Frédéric).  
Check toutes les 5 minutes — alerte ntfy si down.

URL surveillée : `https://fredsuretat-x402-adresses.hf.space/health`

---

## Structure du projet

```
x402-adresses/
├── main.py            # App FastAPI + middleware x402 + endpoint /validate
├── requirements.txt   # fastapi, uvicorn, httpx, pydantic, python-dotenv
├── Dockerfile         # Port 7860 (HF Spaces standard)
├── docker-compose.yml # Pour déploiement VPS alternatif
├── README.md          # Header HF Spaces (requis)
├── SETUP.md           # Ce fichier
├── .env               # Variables locales (non commité)
└── .env.example       # Template
```

---

## Évolutions possibles

- Augmenter le prix (`PRICE_USDC=0.01`) si la demande monte
- Ajouter d'autres endpoints payants (validation SIRET, extraction d'entités NLP)
- Passer sur le VPS Ateris pour plus de contrôle (derrière Traefik)
- Ajouter un dashboard de transactions reçues
