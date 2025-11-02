#!/usr/bin/env python3
import json, sys
a = json.load(open("receipt.fp16.json"))
b = json.load(open("receipt.bf16e.json"))

def g(rec,k): return rec["dials"][k]

print("Badges:", a["badge"], "->", b["badge"])
print("Stress:", g(a,"stress"), "->", g(b,"stress"))
print("Drift :", g(a,"drift"),  "->", g(b,"drift"))
print("Expect: stress↑ and drift↑ under bf16-emulated. If not, retire/adjust metrics.")
