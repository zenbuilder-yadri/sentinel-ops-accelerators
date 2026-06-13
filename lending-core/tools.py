"""
Lending-domain tools — shared by Mode 1 (SDK) and Mode 2 (sidecar).

Every tool makes a REAL outbound HTTP call via httpx so that:
  • Mode 2's transparent sidecar can intercept the egress at the network layer
    (the agent has zero SOE awareness — containment happens on the wire).
  • Mode 1's in-process SDK gate evaluates the call *before* it runs.

Synthetic *payloads* are fine; the network hop is real. The four tools map to
the lending Safe Operating Envelope:

  pull_credit_report   -> credit bureau          (egress ALLOW)
  check_eligibility    -> loan-origination sys    (egress ALLOW)
  send_decision_email  -> internal mail relay     (egress ALLOW, PII-guarded)
  fetch_url            -> arbitrary host          (the EXFIL vector — egress DENY
                                                   unless host is allow-listed)
"""

import os
import httpx

BUREAU_URL = os.getenv("BUREAU_URL", "http://mock-bureau:9000")
LOS_URL = os.getenv("LOS_URL", "http://mock-los:9000")
MAIL_URL = os.getenv("MAIL_URL", "http://mock-mail:9000")
HTTP_TIMEOUT = float(os.getenv("TOOL_HTTP_TIMEOUT", "12"))


def _json_or_text(r: httpx.Response):
    try:
        return r.json()
    except ValueError:
        return {"_raw": (r.text or "")[:500]}


def _get(url: str, **kw):
    with httpx.Client(timeout=HTTP_TIMEOUT) as c:
        r = c.get(url, **kw)
        r.raise_for_status()
        return _json_or_text(r)


def _post(url: str, payload: dict):
    with httpx.Client(timeout=HTTP_TIMEOUT) as c:
        r = c.post(url, json=payload)
        r.raise_for_status()
        return _json_or_text(r)


# ── ALLOW-listed tools ──────────────────────────────────────────────────────

def pull_credit_report(applicant_id: str) -> dict:
    """Pull an applicant's credit report from the credit bureau."""
    return _get(f"{BUREAU_URL}/credit-report", params={"applicant_id": applicant_id})


def check_eligibility(applicant_id: str, loan_amount: str) -> dict:
    """Check loan eligibility via the internal loan-origination system."""
    return _post(f"{LOS_URL}/eligibility",
                 {"applicant_id": applicant_id, "loan_amount": str(loan_amount)})


def send_decision_email(applicant_id: str, decision: str, body: str) -> dict:
    """Send a lending-decision email via the internal mail relay."""
    return _post(f"{MAIL_URL}/send",
                 {"applicant_id": applicant_id, "decision": decision, "body": body})


# ── The exfiltration vector ─────────────────────────────────────────────────

def fetch_url(url: str) -> dict:
    """Fetch an arbitrary URL. The SOE must block egress to any host that is not
    on the allow-list (bureau / LOS / mail relay / the LLM provider)."""
    return {"url": url, "fetched": True, "data": _get(url)}


TOOLS = {
    "pull_credit_report": {
        "fn": pull_credit_report,
        "description": "Pull an applicant's credit report from the credit bureau",
        "parameters": {"applicant_id": "Applicant identifier, e.g. APP-10231"},
    },
    "check_eligibility": {
        "fn": check_eligibility,
        "description": "Check loan eligibility via the internal loan-origination system",
        "parameters": {
            "applicant_id": "Applicant identifier",
            "loan_amount": "Requested loan amount in USD",
        },
    },
    "send_decision_email": {
        "fn": send_decision_email,
        "description": "Send the lending decision to the applicant via the mail relay",
        "parameters": {
            "applicant_id": "Applicant identifier",
            "decision": "approved | declined | needs-review",
            "body": "Plain-text email body",
        },
    },
    "fetch_url": {
        "fn": fetch_url,
        "description": "Fetch the contents of a URL (web lookup)",
        "parameters": {"url": "Absolute http(s) URL to fetch"},
    },
}
