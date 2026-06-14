"""
Shared HTTP + SSE client for the Sentinel-Ops two-mode demo (APP 3 + APP 1 shared).

Real HTTP only. No mocks, no canned data. Every method round-trips to
https://api.yadriworks.ai (or the URL passed in `api_url`).

Auth modes
----------
- JWT Bearer:        Authorization: Bearer <jwt>                              (UI, Mode 1)
- Long-lived API key X-SOE-Tenant-Id: <tid>, X-SOE-Api-Key: sok_...           (Mode 2 sidecar)

Endpoints used
--------------
GET    /v1/health
POST   /v1/evaluate
POST   /v1/guardrails/evaluate
POST   /v1/audit
GET    /v1/agents/<id>/risk
POST   /v1/deploy
GET    /v1/events/stream                  (text/event-stream)

Retries 5xx up to 3x with exponential backoff. SSE auto-reconnects on
disconnect (server heartbeats every 20s; ALB idle timeout is 60s).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Iterator, Optional

import requests
import sseclient  # sseclient-py

log = logging.getLogger("soe_client")

_RETRYABLE = (500, 502, 503, 504)
_MAX_RETRIES = 3
_BASE_BACKOFF = 0.4  # seconds


class SoeClient:
    """Real HTTP + SSE client against the live Sentinel-Ops control plane."""

    def __init__(
        self,
        api_url: str,
        jwt: Optional[str] = None,
        api_key: Optional[str] = None,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        timeout: float = 15.0,
    ):
        if not api_url:
            raise ValueError("api_url is required")
        if not jwt and not api_key:
            # Warn but allow construction — demo scripts often init the client
            # before the operator pastes/refreshes the JWT. Calls will 401 at
            # runtime, which is the correct fail-CLOSED behavior.
            log.warning(
                "SoeClient initialized without jwt or api_key — "
                "every authenticated request will 401 until creds are set."
            )
        if api_key and not tenant_id:
            raise ValueError("api_key auth requires tenant_id")

        self.api_url = api_url.rstrip("/")
        self.jwt = jwt
        self.api_key = api_key
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.timeout = timeout
        self._session = requests.Session()

    # ── auth ──────────────────────────────────────────────────────────────

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        h: Dict[str, str] = {"Content-Type": "application/json"}
        if self.jwt:
            h["Authorization"] = f"Bearer {self.jwt}"
        else:
            h["X-SOE-Api-Key"] = self.api_key or ""
            h["X-SOE-Tenant-Id"] = self.tenant_id or ""
        if extra:
            h.update(extra)
        return h

    # ── core HTTP with retry ──────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        accept: Optional[str] = None,
    ) -> requests.Response:
        url = f"{self.api_url}{path}"
        extra = {"Accept": accept} if accept else None
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                r = self._session.request(
                    method,
                    url,
                    headers=self._headers(extra),
                    json=json_body,
                    params=params,
                    stream=stream,
                    timeout=self.timeout,
                )
            except requests.RequestException as e:
                last_exc = e
                backoff = _BASE_BACKOFF * (2 ** attempt)
                log.warning("HTTP %s %s failed (%s); retry in %.1fs", method, path, e, backoff)
                time.sleep(backoff)
                continue

            if r.status_code in _RETRYABLE and attempt < _MAX_RETRIES - 1:
                backoff = _BASE_BACKOFF * (2 ** attempt)
                log.warning("HTTP %s %s -> %d; retry in %.1fs", method, path, r.status_code, backoff)
                try:
                    r.close()
                except Exception:
                    pass
                time.sleep(backoff)
                continue

            return r

        raise RuntimeError(f"HTTP {method} {path} failed after {_MAX_RETRIES} attempts: {last_exc}")

    @staticmethod
    def _decode(r: requests.Response) -> Dict[str, Any]:
        if r.status_code >= 400:
            return {
                "error": f"HTTP {r.status_code}",
                "detail": (r.text or "")[:512],
                "status": r.status_code,
            }
        try:
            return r.json()
        except ValueError:
            return {"error": "non-JSON response", "detail": (r.text or "")[:512]}

    # ── public API ────────────────────────────────────────────────────────

    def health(self) -> bool:
        try:
            r = self._request("GET", "/v1/health")
            if r.status_code != 200:
                return False
            body = self._decode(r)
            status = (body.get("status") or "").upper()
            return status in {"HEALTHY", "OK", "UP"}
        except Exception as e:
            log.warning("health() failed: %s", e)
            return False

    def evaluate(self, tool_name: str, tool_input: Dict[str, Any],
                 agent_id: Optional[str] = None) -> Dict[str, Any]:
        aid = agent_id or self.agent_id
        if not aid:
            raise ValueError("evaluate() requires agent_id (constructor or argument)")
        body = {"agentId": aid, "toolName": tool_name, "toolInput": tool_input}
        t0 = time.monotonic()
        r = self._request("POST", "/v1/evaluate", json_body=body)
        latency_ms = round((time.monotonic() - t0) * 1000)
        data = self._decode(r)
        data["_latency_ms"] = latency_ms
        return data

    def guard(self, text: str, direction: str = "input",
              agent_id: Optional[str] = None) -> Dict[str, Any]:
        if direction not in {"input", "output"}:
            raise ValueError("direction must be 'input' or 'output'")
        aid = agent_id or self.agent_id
        body = {"agentId": aid}
        body["input" if direction == "input" else "output"] = text
        r = self._request("POST", "/v1/guardrails/evaluate", json_body=body)
        return self._decode(r)

    def audit(self, event: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(event, dict):
            raise ValueError("event must be a dict")
        body = dict(event)
        if "agentId" not in body and self.agent_id:
            body["agentId"] = self.agent_id
        r = self._request("POST", "/v1/audit", json_body=body)
        return self._decode(r)

    def get_risk(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        aid = agent_id or self.agent_id
        if not aid:
            raise ValueError("get_risk() requires agent_id")
        r = self._request("GET", f"/v1/agents/{aid}/risk")
        return self._decode(r)

    def deploy_soe(self, soe_def: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(soe_def, dict):
            raise ValueError("soe_def must be a dict")
        r = self._request("POST", "/v1/deploy", json_body=soe_def)
        return self._decode(r)

    # ── SSE consumer with auto-reconnect ──────────────────────────────────

    def stream_events(self, agent_id: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        """
        Yield decoded SSE events (dict). Reconnects on disconnect with
        exponential backoff capped at 30s. Yields a synthetic
        {'kind': '_disconnect', 'detail': '...'} marker on each break so the
        Streamlit polling-fallback can count consecutive drops.
        """
        params: Dict[str, Any] = {}
        if agent_id or self.agent_id:
            params["agentId"] = agent_id or self.agent_id

        backoff = 1.0
        while True:
            try:
                r = self._request(
                    "GET",
                    "/v1/events/stream",
                    params=params or None,
                    stream=True,
                    accept="text/event-stream",
                )
                if r.status_code != 200:
                    yield {
                        "kind": "_disconnect",
                        "detail": f"HTTP {r.status_code}",
                        "ts": time.time(),
                    }
                    time.sleep(min(backoff, 30.0))
                    backoff = min(backoff * 2, 30.0)
                    continue

                backoff = 1.0  # successful connect resets backoff
                client = sseclient.SSEClient(r)
                for sse in client.events():
                    raw = (sse.data or "").strip()
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        payload = {"kind": "raw", "data": raw}
                    if sse.event and "kind" not in payload:
                        payload["kind"] = sse.event
                    yield payload
            except (requests.RequestException, GeneratorExit) as e:
                yield {"kind": "_disconnect", "detail": str(e), "ts": time.time()}
                time.sleep(min(backoff, 30.0))
                backoff = min(backoff * 2, 30.0)
                continue
            except Exception as e:  # noqa: BLE001
                yield {"kind": "_disconnect", "detail": f"unexpected: {e}", "ts": time.time()}
                time.sleep(min(backoff, 30.0))
                backoff = min(backoff * 2, 30.0)
                continue

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass
