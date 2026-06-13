#!/usr/bin/env bash
# Zero-cloud quickstart: a local kind cluster running the LendingAssistant agent
# with the Sentinel-Ops sidecar injected in-pod. Demonstrates the in-pod topology
# without any cloud account.
#
# Prereqs: docker, kind, kubectl, helm.  Env: ANTHROPIC_API_KEY, SOE_API_KEY (sok_).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLUSTER="${KIND_CLUSTER:-soe-accel}"
M2="$ROOT/mode2-sidecar/lending-assistant"
: "${ANTHROPIC_API_KEY:?set ANTHROPIC_API_KEY}"
: "${SOE_API_KEY:?set SOE_API_KEY (sok_...)}"
: "${SOE_TENANT_ID:=yadriworks-demo}"
: "${SOE_API_URL:=https://api.yadriworks.ai}"

for t in docker kind kubectl helm; do command -v "$t" >/dev/null || { echo "missing: $t"; exit 1; }; done

echo "==> create kind cluster '$CLUSTER'"
kind get clusters 2>/dev/null | grep -qx "$CLUSTER" || kind create cluster --name "$CLUSTER"

echo "==> build + load images"
docker build -t lending-assistant:local "$M2/app"
docker build -t lending-mock:local "$M2/mock-services"
kind load docker-image lending-assistant:local lending-mock:local --name "$CLUSTER"

echo "==> deploy mock internal systems (bureau / los / mail)"
for svc in mock-bureau mock-los mock-mail; do
  kubectl create deployment "$svc" --image=lending-mock:local 2>/dev/null || true
  kubectl set image deployment/"$svc" "$svc"=lending-mock:local 2>/dev/null || true
  kubectl expose deployment "$svc" --port=9000 2>/dev/null || true
done

echo "==> secret with LLM + control-plane keys"
kubectl create secret generic lending-secrets \
  --from-literal=ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic soe-api-key \
  --from-literal=api-key="$SOE_API_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> helm install sidecar chart (app + soe-sidecar in one pod)"
helm upgrade --install lending "$ROOT/deploy/helm/sentinel-ops-sidecar" \
  --set app.image=lending-assistant:local \
  --set app.existingSecret=lending-secrets \
  --set controlPlane.apiUrl="$SOE_API_URL" \
  --set controlPlane.tenantId="$SOE_TENANT_ID" \
  --set controlPlane.apiKeySecret=soe-api-key \
  --set-file soe="$M2/soe-definitions/lending-assistant.soe.json"

echo "==> waiting for rollout"
kubectl rollout status deploy/lending-assistant --timeout=180s

cat <<EOF

Ready. In another terminal:
  kubectl port-forward svc/lending-assistant 8090:8090
Then:
  python $M2/scenarios/attack.py --url http://localhost:8090

Teardown:  kind delete cluster --name $CLUSTER
EOF
