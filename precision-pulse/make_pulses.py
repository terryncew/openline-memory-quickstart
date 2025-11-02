#!/usr/bin/env python3
import json, time, uuid, hashlib
from datetime import datetime, timezone

# --- cheap deterministic “workload” so outputs differ under emulated precision
def toy_logits(seed=7, n=32):
    # portable, no numpy
    x = []
    v = seed * 1103515245 + 12345
    for _ in range(n):
        v = (v * 1103515245 + 12345) & 0x7fffffff
        x.append((v % 100000) / 100000.0)  # [0,1)
    return x

def emulate_bf16(vals):
    # emulate extra rounding loss; not numerically exact, but monotone
    out = []
    for v in vals:
        # keep 7 bits frac; crude but deterministic
        quant = round(v * 128) / 128.0
        out.append(min(1.0, max(0.0, quant)))
    return out

def stress_metric(vals):
    # higher variance => higher stress (toy)
    mean = sum(vals)/len(vals)
    var = sum((v-mean)**2 for v in vals)/len(vals)
    return max(0.0, min(1.0, var*3))  # scale into [0,1]

def drift_metric(a, b):
    # L1 distance normalized
    s = sum(abs(x-y) for x,y in zip(a,b)) / len(a)
    return max(0.0, min(1.0, s*2))

def coherence_metric(vals):
    # prefer “organized” distribution near center; punish extremes (toy)
    center_mass = sum(1.0 - abs(v-0.5)*2 for v in vals)/len(vals)
    return max(0.0, min(1.0, center_mass))

def digest(model_fp, config_fp, train_dtype, infer_dtype):
    h = hashlib.blake2s()
    h.update((model_fp + "|" + config_fp + "|" + train_dtype + "/" + infer_dtype).encode())
    return h.hexdigest()

def make_receipt(train_dtype, infer_dtype, base_logits, perturbed_logits, model_family="demo-llm", listed_sensitive=True):
    dials = {
        "stress": stress_metric(perturbed_logits),
        "drift": drift_metric(base_logits, perturbed_logits),
        "coherence": coherence_metric(perturbed_logits),
        "precision_consistency": 1.0 if train_dtype==infer_dtype else 0.0,
        "precision_risk": (0.5 if train_dtype!=infer_dtype else 0.0) + (0.5 if (train_dtype!=infer_dtype and listed_sensitive) else 0.0)
    }
    badge = "RED" if (dials["stress"]>0.85 or dials["drift"]>0.85) else ("AMBER" if train_dtype!=infer_dtype else "GREEN")

    now = datetime.now(timezone.utc).isoformat()
    rid = str(uuid.uuid4())
    model_fp = "demo-fingerprint"
    cfg_fp = "demo-config"

    rec = {
        "version": "OLR/1.5-P",
        "issued_at": now,
        "model": {"family": model_family, "fingerprint": model_fp},
        "precision": {
            "train_dtype": train_dtype, "infer_dtype": infer_dtype,
            "mismatch": train_dtype!=infer_dtype,
            "note": "Declared only; no activations logged."
        },
        "run": {"id": rid, "ts": now},
        "dials": dials,
        "badge": badge,
        "signature": {
            "alg": "none",
            "pub": "",
            "sig": "",
            "digest": digest(model_fp, cfg_fp, train_dtype, infer_dtype)
        }
    }
    return rec

def main():
    base = toy_logits()
    fp16 = base[:]                  # as-is
    bf16e = emulate_bf16(base)      # emulated precision loss

    r1 = make_receipt("fp16","fp16", base, fp16)
    r2 = make_receipt("fp16","bf16", base, bf16e)

    with open("receipt.fp16.json","w") as f: json.dump(r1, f, indent=2)
    with open("receipt.bf16e.json","w") as f: json.dump(r2, f, indent=2)

    print("Wrote receipt.fp16.json  &  receipt.bf16e.json")
    print("Dial summary:")
    for name in ["stress","drift","coherence","precision_consistency","precision_risk"]:
        print(f"  {name:22s} fp16={r1['dials'][name]:.3f}   bf16-emul={r2['dials'][name]:.3f}")

if __name__ == "__main__":
    main()
