"""
Mock internal systems for the lending demo — one image, three compose services
(mock-bureau / mock-los / mock-mail), all on port 9000. Synthetic data only.
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="lending mock services")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/credit-report")
def credit_report(applicant_id: str):
    return {
        "applicant_id": applicant_id,
        "bureau": "MockExperian",
        "fico_score": 712,
        "tradelines": 14,
        "utilization": "23%",
        "derogatory_marks": 0,
        "inquiries_6mo": 1,
    }


class Elig(BaseModel):
    applicant_id: str
    loan_amount: str


@app.post("/eligibility")
def eligibility(b: Elig):
    return {
        "applicant_id": b.applicant_id,
        "loan_amount": b.loan_amount,
        "eligible": True,
        "max_apr": "11.9%",
        "dti": "31%",
        "decision_hint": "approve-with-standard-terms",
    }


class Mail(BaseModel):
    applicant_id: str
    decision: str
    body: str


@app.post("/send")
def send(m: Mail):
    return {
        "sent": True,
        "applicant_id": m.applicant_id,
        "decision": m.decision,
        "message_id": "msg-mock-0001",
        "chars": len(m.body),
    }
