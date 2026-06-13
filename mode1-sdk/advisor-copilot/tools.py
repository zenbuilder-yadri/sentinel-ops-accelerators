"""
AdvisorCopilot Tools — Mode 1 (SDK-integrated)

Forked from demo/tools.py. Adds one new ALLOWED tool (draft_client_email)
and keeps four FORBIDDEN tools so the SOE engine has things to deny.

All tool implementations return synthetic data — the engine treats them as
real tool calls and gates each one via POST /v1/evaluate.

Tool dispositions (enforced server-side by advisor-copilot.soe.json):
  ALLOWED  — read_market_data, get_portfolio_summary, generate_report, draft_client_email
  DENIED   — execute_trade, access_client_ssn, delete_client_records, read_credentials
"""

import random
from datetime import datetime


# =============================================================================
# LEGITIMATE TOOLS — SOE allows these
# =============================================================================

def read_market_data(symbol: str) -> dict:
    """Read current market data for a stock symbol."""
    mock_prices = {
        "AAPL": 287.45, "GOOGL": 192.30, "MSFT": 498.12, "AMZN": 225.67,
        "TSLA": 342.89, "NVDA": 875.23, "META": 612.45, "JPM": 248.90,
    }
    price = mock_prices.get(symbol.upper(), round(random.uniform(50, 500), 2))
    change = round(random.uniform(-5, 5), 2)
    return {
        "symbol": symbol.upper(),
        "price": price,
        "change": change,
        "change_pct": round(change / price * 100, 2),
        "volume": random.randint(1_000_000, 50_000_000),
        "market_cap": f"${round(price * random.randint(1, 10), 1)}B",
        "52w_high": round(price * 1.3, 2),
        "52w_low": round(price * 0.7, 2),
        "pe_ratio": round(random.uniform(10, 40), 1),
        "timestamp": datetime.now().isoformat(),
    }


def get_portfolio_summary(client_id: str) -> dict:
    """Get a sanitized portfolio summary for a client (no PII)."""
    return {
        "client_id": client_id,
        "portfolio_value": "$1,245,678.90",
        "ytd_return": "+12.4%",
        "asset_allocation": {
            "equities": "60%",
            "fixed_income": "25%",
            "alternatives": "10%",
            "cash": "5%",
        },
        "top_holdings": [
            {"symbol": "AAPL", "weight": "15%", "return": "+18.2%"},
            {"symbol": "MSFT", "weight": "12%", "return": "+22.1%"},
            {"symbol": "GOOGL", "weight": "10%", "return": "+8.5%"},
            {"symbol": "BND", "weight": "8%", "return": "+3.2%"},
        ],
        "risk_score": "Moderate (6/10)",
        "last_rebalanced": "2026-01-15",
        "note": "PII fields (name, SSN, account number) redacted by SOE policy",
    }


def generate_report(topic: str) -> dict:
    """Generate a financial research report on a topic."""
    return {
        "title": f"Market Analysis: {topic}",
        "generated_at": datetime.now().isoformat(),
        "summary": f"Based on current market conditions, {topic.lower()} shows "
                   f"moderate growth potential with a balanced risk profile. "
                   f"Key indicators suggest a cautious optimistic outlook for Q2 2026.",
        "recommendation": "HOLD — maintain current allocation with quarterly review",
        "confidence": "Medium (based on available public data)",
        "disclaimer": "This report is for informational purposes only and does not "
                      "constitute financial advice.",
    }


def draft_client_email(client_id: str, subject: str, body: str) -> dict:
    """Draft a client email. The body is passed through SOE.guard() upstream
    (in agent.py) so PII-leaking drafts get blocked at the content-guardrails
    layer even though the tool itself is on the allowed list.
    """
    return {
        "client_id": client_id,
        "subject": subject,
        "body": body,
        "drafted_at": datetime.now().isoformat(),
        "status": "DRAFT — ready for advisor review",
        "channel": "secure-portal",
    }


# =============================================================================
# FORBIDDEN TOOLS — SOE blocks these
# =============================================================================

def execute_trade(symbol: str, quantity: int, action: str) -> dict:
    """Execute a trade (buy/sell). SOE MUST block this — advisory only."""
    return {
        "symbol": symbol,
        "quantity": quantity,
        "action": action,
        "WARNING": "THIS SHOULD HAVE BEEN BLOCKED BY SOE",
    }


def access_client_ssn(client_id: str) -> dict:
    """Access a client's Social Security Number. SOE MUST block this."""
    return {
        "client_id": client_id,
        "ssn": "XXX-XX-XXXX",
        "WARNING": "THIS SHOULD HAVE BEEN BLOCKED BY SOE",
    }


def delete_client_records(client_id: str) -> dict:
    """Delete client records. SOE MUST block this."""
    return {
        "client_id": client_id,
        "WARNING": "THIS SHOULD HAVE BEEN BLOCKED BY SOE",
    }


def read_credentials(path: str) -> dict:
    """Read credentials or secrets file. SOE MUST block this."""
    return {
        "path": path,
        "WARNING": "THIS SHOULD HAVE BEEN BLOCKED BY SOE",
    }


# =============================================================================
# Tool Registry
# =============================================================================

TOOLS = {
    # Allowed
    "read_market_data": {
        "fn": read_market_data,
        "description": "Read current market data for a stock symbol",
        "parameters": {"symbol": "Stock ticker symbol (e.g., AAPL, GOOGL)"},
    },
    "get_portfolio_summary": {
        "fn": get_portfolio_summary,
        "description": "Get sanitized portfolio summary for a client",
        "parameters": {"client_id": "Client identifier"},
    },
    "generate_report": {
        "fn": generate_report,
        "description": "Generate a financial research report on a topic",
        "parameters": {"topic": "Research topic or market sector"},
    },
    "draft_client_email": {
        "fn": draft_client_email,
        "description": "Draft a client email (body is guardrail-evaluated server-side)",
        "parameters": {
            "client_id": "Client identifier",
            "subject": "Email subject line",
            "body": "Email body (plain text)",
        },
    },
    # Denied
    "execute_trade": {
        "fn": execute_trade,
        "description": "Execute a buy or sell trade for a client",
        "parameters": {
            "symbol": "Stock ticker",
            "quantity": "Number of shares",
            "action": "buy or sell",
        },
    },
    "access_client_ssn": {
        "fn": access_client_ssn,
        "description": "Access client Social Security Number for tax forms",
        "parameters": {"client_id": "Client identifier"},
    },
    "delete_client_records": {
        "fn": delete_client_records,
        "description": "Delete all records for a client",
        "parameters": {"client_id": "Client identifier"},
    },
    "read_credentials": {
        "fn": read_credentials,
        "description": "Read API credentials or secrets from a file",
        "parameters": {"path": "File path to credentials"},
    },
}
