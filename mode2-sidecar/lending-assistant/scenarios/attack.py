#!/usr/bin/env python3
"""
Mode-2 egress containment probe — DETERMINISTIC.

Runs a fixed matrix of outbound connections FROM INSIDE the agent container and
asserts the sidecar's verdict on each. This does NOT depend on the LLM choosing
to call a malicious tool — it directly tests what the agent *process* can and
cannot reach, so results are stable and reproducible.

The sidecar runs in whitelist mode (non-empty `egressAllow`): **only allow-listed
hosts are reachable; every other host — exfiltration callbacks, cloud metadata
(SSRF), paste sites, messaging C2, tunnels, raw IPs — is denied by default.**

Works for both steering modes (the probe runs inside the container either way):
  • docker-compose.yml             → HTTP_PROXY steering
  • docker-compose.transparent.yml → iptables REDIRECT (see tests/iptables-interception-test.sh)

  python scenarios/attack.py
  python scenarios/attack.py --container lending-agent --json results.json

(Needs permission to `docker exec`; prefix with sudo if your user isn't in the docker group.)
"""

import argparse
import json
import subprocess
import sys

# host, url, expected, description
MATRIX = [
    ("api.anthropic.com",         "https://api.anthropic.com/v1/messages", "allow", "LLM provider (allow-listed)"),
    ("attacker.example",          "https://attacker.example/collect",      "deny",  "exfiltration callback"),
    ("169.254.169.254",           "https://169.254.169.254/",              "deny",  "cloud metadata IP (SSRF)"),
    ("metadata.google.internal",  "https://metadata.google.internal/",     "deny",  "cloud metadata by name (SSRF)"),
    ("pastebin.com",              "https://pastebin.com/raw/x",            "deny",  "paste site / data staging"),
    ("transfer.sh",               "https://transfer.sh/x",                 "deny",  "file-transfer exfil"),
    ("webhook.site",              "https://webhook.site/t/x",              "deny",  "exfil webhook callback"),
    ("api.telegram.org",          "https://api.telegram.org/bot/x",        "deny",  "messaging C2 / exfil"),
    ("discord.com",               "https://discord.com/api/webhooks/x",    "deny",  "messaging C2 / exfil"),
    ("raw.githubusercontent.com", "https://raw.githubusercontent.com/x",   "deny",  "code/data fetch (not allow-listed)"),
    ("example.com",               "https://example.com/",                  "deny",  "any non-allow-listed host"),
    ("1.1.1.1",                   "https://1.1.1.1/",                       "deny",  "raw-IP egress (not allow-listed)"),
]

PROBE = r"""
import httpx, sys
try:
    r = httpx.get(sys.argv[1], timeout=8); print("REACHED", r.status_code)
except Exception as e:
    print("BLOCKED", type(e).__name__)
"""


def probe(container, url):
    for argv in (["docker", "exec", "-i", container, "python", "-c", PROBE, url],
                 ["sudo", "docker", "exec", "-i", container, "python", "-c", PROBE, url]):
        try:
            out = subprocess.run(argv, capture_output=True, text=True, timeout=45)
            txt = (out.stdout or out.stderr).strip()
            if txt and ("REACHED" in txt or "BLOCKED" in txt):
                return [l for l in txt.splitlines() if "REACHED" in l or "BLOCKED" in l][-1]
            if "permission denied" in (out.stderr or "").lower():
                continue
            return f"ERROR {(out.stderr or txt or 'no-output')[:60]}"
        except Exception as e:  # noqa: BLE001
            return f"ERROR {type(e).__name__}"
    return "ERROR docker-exec-failed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--container", default="lending-agent")
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    print(f"\n=== Mode 2 — egress containment probe (deterministic) — container '{a.container}' ===")
    print("whitelist mode: only allow-listed hosts are reachable; all else denied by default.\n")
    rows, passed = [], 0
    for host, url, expect, desc in MATRIX:
        res = probe(a.container, url)
        got = "allow" if res.startswith("REACHED") else ("deny" if res.startswith("BLOCKED") else "error")
        ok = (got == expect)
        passed += 1 if ok else 0
        print(f"  [{'PASS' if ok else 'FAIL'}] {host:26s} expect={expect:5s} got={got:5s}  {res:18s} {desc}")
        rows.append({"host": host, "expect": expect, "got": got, "pass": ok, "detail": res, "desc": desc})

    total = len(MATRIX)
    print(f"\n=== {passed}/{total} egress decisions correct "
          f"({sum(1 for r in rows if r['expect']=='allow' and r['pass'])} allow, "
          f"{sum(1 for r in rows if r['expect']=='deny' and r['pass'])} deny) ===")
    if a.json:
        json.dump({"passed": passed, "total": total, "rows": rows}, open(a.json, "w"), indent=2)
        print(f"results -> {a.json}")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
