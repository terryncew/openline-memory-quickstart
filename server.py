# server.py — skinny memory + five-field receipts + revoke + verify
import os, json, time, uuid, base64, datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from nacl.signing import SigningKey, VerifyKey
from nacl.encoding import RawEncoder
from dotenv import load_dotenv

try:
    import requests
except Exception:
    requests = None

load_dotenv()
app = FastAPI(title="Memory + Receipts (Quickstart)")

# ---- dev key (rotate in prod) ----
DEV_SEED = os.getenv("DEV_SEED", "dev-seed-change-me-32bytes________")
KEY_ID   = os.getenv("KEY_ID", "dev-1")
signing_key = SigningKey(DEV_SEED.encode("utf-8")[:32])
verify_key  = signing_key.verify_key
PUBKEY_B64  = base64.b64encode(bytes(verify_key)).decode()

ISSUER_DID = os.getenv("ISSUER_DID", "did:web:localhost")
SCHEMA     = "proof.v1"

# ---- storage (SQLite or in-memory) ----
from memory_store import MemoryStore
store = MemoryStore()

# ---- models ----
class WriteReq(BaseModel):
    text: str
    tags: List[str] = []
    scope: str = Field(default="private", pattern="^(private|team|public)$")
    ttl_days: Optional[int] = None
    consent: str = Field(default="explicit", pattern="^(explicit|inferred|none)$")

class SearchReq(BaseModel):
    q: str
    top_k: int = 5
    tags: Optional[List[str]] = None

class RevokeReq(BaseModel):
    mid: str

# ---- helpers ----
def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")

def sign_fields(fields: dict) -> str:
    msg = canonical(fields)
    sig = signing_key.sign(msg, encoder=RawEncoder).signature
    return "ed25519:" + base64.b64encode(sig).decode()

def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def add_days_iso(days: int) -> str:
    ts = datetime.datetime.utcnow() + datetime.timedelta(days=days)
    return ts.replace(microsecond=0).isoformat() + "Z"

def mk_receipt(rid: str, badge: str, flags: list, revoke_of: Optional[str] = None) -> dict:
    fields = {
        "rid": rid,
        "issuer": ISSUER_DID,
        "kid": KEY_ID,
        "when": now_iso(),
        "where": "geo:none",
        "badge": badge,            # green|amber|red
        "flags": flags,            # e.g., ["mem.write"], ["mem.revoke", mid]
        "schema": SCHEMA
    }
    if revoke_of:
        fields["revoke_of"] = revoke_of
    return {**fields, "sig": sign_fields(fields)}

def did_web_to_wellknown(did: str) -> Optional[str]:
    if not did.startswith("did:web:"):
        return None
    hostpath = did[len("did:web:"):].replace(":", "/")
    return f"https://{hostpath}/.well-known/receipts.json"

# ---- well-known (for verifiers) ----
@app.get("/.well-known/receipts.json")
def well_known():
    return {"issuer": ISSUER_DID,
            "keys": [{"kty":"OKP","crv":"Ed25519","alg":"EdDSA","kid":KEY_ID,"publicKeyBase64":PUBKEY_B64}],
            "schema": SCHEMA}

@app.get("/health")
def health(): return {"ok": True, "time": now_iso()}

# ---- memory endpoints ----
@app.post("/mem/write")
def mem_write(req: WriteReq):
    mid = str(uuid.uuid4()); rid = str(uuid.uuid4())
    item = {
        "mid": mid, "text": req.text, "tags": req.tags, "scope": req.scope,
        "consent": req.consent, "created_at": now_iso(),
        "expires_at": add_days_iso(req.ttl_days) if req.ttl_days else None,
        "rid": rid
    }
    store.write(item)
    receipt = mk_receipt(rid, badge="green", flags=["mem.write"])
    return {"mid": mid, "receipt": receipt}

@app.post("/mem/search")
def mem_search(req: SearchReq):
    results = store.search(req.q, req.tags, req.top_k)
    return {"results": results}

@app.post("/mem/revoke")
def mem_revoke(req: RevokeReq):
    revoke_of = store.revoke(req.mid)
    if not revoke_of:
        raise HTTPException(404, "mid not found or already revoked")
    rid = str(uuid.uuid4())
    receipt = mk_receipt(rid, badge="amber", flags=["mem.revoke", req.mid], revoke_of=revoke_of)
    return {"revoked": req.mid, "receipt": receipt}

# ---- verify a posted receipt ----
@app.post("/verify")
def verify_receipt(payload: dict = Body(...)):
    required = ["rid","issuer","kid","when","where","badge","flags","schema","sig"]
    for f in required:
        if f not in payload: raise HTTPException(400, f"missing field: {f}")
    fields = {k: payload[k] for k in ["rid","issuer","kid","when","where","badge","flags","schema"] if k in payload}
    sig_b64 = payload["sig"].split("ed25519:")[-1]

    # default: local dev key
    candidate = [{"kid": KEY_ID, "publicKeyBase64": PUBKEY_B64}]

    # try external issuer’s .well-known if different DID
    if payload["issuer"] != ISSUER_DID and requests:
        url = did_web_to_wellknown(payload["issuer"])
        if url:
            try:
                data = requests.get(url, timeout=3).json()
                if isinstance(data, dict) and "keys" in data: candidate = data["keys"]
            except Exception:
                pass

    # pick key by kid (or fallback to first)
    kid = payload.get("kid")
    pkey = None
    for k in candidate:
        if kid and k.get("kid") == kid: pkey = k.get("publicKeyBase64"); break
    if not pkey: pkey = candidate[0].get("publicKeyBase64")

    try:
        VerifyKey(base64.b64decode(pkey)).verify(canonical(fields), base64.b64decode(sig_b64))
        return {"valid": True, "issuer": fields["issuer"], "kid": fields["kid"]}
    except Exception as e:
        return {"valid": False, "error": str(e)}
