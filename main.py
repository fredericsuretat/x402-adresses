import os
import httpx
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()

PRICE_USDC = os.getenv("PRICE_USDC", "0.001")
FACILITATOR_URL = "https://x402.org/facilitator"
BAN_API = "https://api-adresse.data.gouv.fr/search/"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

wallet_address: str = ""
payments_total: int = 0
payments_log: list = []


async def resolve_wallet() -> str:
    raw = os.getenv("WALLET_ADDRESS", "0x6458941857a70C6cA18c440a316035A21901A12b")
    if raw.startswith("0x"):
        return raw
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"https://api.ensdata.net/{raw}")
            resolved = resp.json().get("address")
            if resolved:
                print(f"[x402] {raw} → {resolved}")
                return resolved
        except Exception:
            pass
    print(f"[x402] Impossible de résoudre {raw}, utilisation brute")
    return raw


@asynccontextmanager
async def lifespan(app: FastAPI):
    global wallet_address
    wallet_address = await resolve_wallet()
    if not wallet_address:
        print("[x402] AVERTISSEMENT : WALLET_ADDRESS non défini, les paiements ne seront pas encaissés")
    else:
        print(f"[x402] Wallet actif : {wallet_address}")
    yield


app = FastAPI(title="Validateur Adresses FR", version="1.0.0", lifespan=lifespan)


class AddressRequest(BaseModel):
    adresse: str


BAZAAR_EXTENSION = {
    "name": "USDC",
    "version": "2",
    "bazaar": {
        "bodyType": "json",
        "input": {"adresse": "15 rue de la paix paris"},
        "inputSchema": {
            "properties": {
                "adresse": {"type": "string", "description": "Adresse française à valider"}
            },
            "required": ["adresse"],
        },
        "output": {
            "example": {
                "valide": True,
                "adresse_normalisee": "15 Rue de la Paix, 75002 Paris",
                "score": 0.97,
                "lat": 48.8698,
                "lon": 2.3311,
                "ville": "Paris",
                "code_postal": "75002",
            }
        },
    },
}


def build_payment_requirements(resource_url: str) -> dict:
    if resource_url.startswith("http://"):
        resource_url = "https://" + resource_url[7:]
    return {
        "scheme": "exact",
        "network": "base",
        "maxAmountRequired": PRICE_USDC,
        "resource": resource_url,
        "description": "Validation d'adresse française — Base Adresse Nationale",
        "mimeType": "application/json",
        "payTo": wallet_address,
        "maxTimeoutSeconds": 300,
        "asset": USDC_BASE,
        "extra": BAZAAR_EXTENSION,
    }


async def call_facilitator(endpoint: str, payment_header: str, requirements: dict) -> bool:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{FACILITATOR_URL}/{endpoint}",
                json={
                    "x402Version": 1,
                    "paymentHeader": payment_header,
                    "paymentRequirements": [requirements],
                },
            )
            if endpoint == "verify":
                return resp.json().get("isValid", False)
            return resp.status_code == 200
        except Exception:
            return False


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if not request.url.path.startswith("/validate"):
        return await call_next(request)

    requirements = build_payment_requirements(str(request.url))
    payment_header = request.headers.get("X-PAYMENT")

    if not payment_header:
        return JSONResponse(
            status_code=402,
            content={
                "x402Version": 1,
                "accepts": [requirements],
                "error": "Payment required",
            },
        )

    is_valid = await call_facilitator("verify", payment_header, requirements)
    if not is_valid:
        return JSONResponse(
            status_code=402,
            content={"x402Version": 1, "error": "Paiement invalide ou expiré"},
        )

    settled = await call_facilitator("settle", payment_header, requirements)
    if settled:
        global payments_total, payments_log
        payments_total += 1
        from datetime import datetime, timezone
        payments_log.append({
            "n": payments_total,
            "at": datetime.now(timezone.utc).isoformat(),
            "resource": str(request.url),
        })
        if len(payments_log) > 100:
            payments_log = payments_log[-100:]
        print(f"[x402] PAIEMENT #{payments_total} reçu — {request.url}")
    return await call_next(request)


@app.get("/")
async def root():
    return {
        "service": "Validateur Adresses Françaises",
        "protocol": "x402",
        "network": "Base (Coinbase L2)",
        "price_per_call": f"{PRICE_USDC} USDC",
        "endpoint": "POST /validate",
        "body": {"adresse": "string"},
        "docs": "/docs",
    }


@app.post("/validate")
async def validate_address(payload: AddressRequest):
    adresse = payload.adresse.strip()
    if not adresse:
        return JSONResponse(status_code=400, content={"error": "Champ 'adresse' requis"})

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(BAN_API, params={"q": adresse, "limit": 1})
            data = resp.json()
        except Exception:
            return JSONResponse(status_code=503, content={"error": "Service BAN indisponible"})

    if not data.get("features"):
        return {"valide": False, "score": 0.0, "adresse_originale": adresse}

    feature = data["features"][0]
    props = feature["properties"]
    lon, lat = feature["geometry"]["coordinates"]

    return {
        "valide": True,
        "adresse_normalisee": props.get("label"),
        "numero": props.get("housenumber"),
        "rue": props.get("street") or props.get("name"),
        "code_postal": props.get("postcode"),
        "ville": props.get("city"),
        "departement": props.get("context", "").split(",")[0].strip() if props.get("context") else None,
        "score": round(props.get("score", 0), 4),
        "lat": lat,
        "lon": lon,
        "type": props.get("type"),
        "adresse_originale": adresse,
    }


@app.get("/stats")
async def stats():
    return {
        "payments_total": payments_total,
        "last_payments": payments_log[-5:] if payments_log else [],
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
