"""
Lending tools — Mode 1 (SDK) variant.

In Mode 1 the enforcement point is the in-process SDK gate (POST /v1/evaluate +
content guardrails), which decides ALLOW/DENY *before* a tool runs. The tool
bodies are therefore synthetic (return dicts) — the governance decision, not the
side effect, is what Mode 1 demonstrates. (Contrast: Mode 2 makes real egress
calls so the sidecar can contain them on the wire.)

Same TOOLS shape as the rest of the lending demo so agent_core can bind them.
"""

from datetime import datetime


def pull_credit_report(applicant_id: str) -> dict:
    return {
        "applicant_id": applicant_id,
        "bureau": "MockExperian",
        "fico_score": 712,
        "tradelines": 14,
        "utilization": "23%",
        "derogatory_marks": 0,
    }


def check_eligibility(applicant_id: str, loan_amount: str) -> dict:
    return {
        "applicant_id": applicant_id,
        "loan_amount": loan_amount,
        "eligible": True,
        "max_apr": "11.9%",
        "dti": "31%",
    }


def send_decision_email(applicant_id: str, decision: str, body: str) -> dict:
    # body is passed through soe.guard() in agent.py before this runs, so a
    # PII-leaking draft is blocked at the content-guardrail layer.
    return {
        "applicant_id": applicant_id,
        "decision": decision,
        "body": body,
        "drafted_at": datetime.now().isoformat(),
        "status": "SENT via mail relay",
    }


def fetch_url(url: str) -> dict:
    # DENIED by the Mode-1 SOE (toolActions.denied). If this ever executes, the
    # gate failed open.
    return {"url": url, "WARNING": "THIS SHOULD HAVE BEEN BLOCKED BY SOE"}


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
