"""
Lending-domain tools. Every tool makes a REAL outbound HTTP call via httpx.

  pull_credit_report   -> credit bureau
  check_eligibility    -> loan-origination system
  send_decision_email  -> internal mail relay
  fetch_url            -> arbitrary host (generic web lookup)

This module is a vanilla agent dependency — no governance imports, no policy
logic. Outbound traffic is steered by the HTTP_PROXY env-var at runtime.
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


def fetch_url(url: str) -> dict:
    """Fetch the contents of a URL (generic web lookup)."""
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
