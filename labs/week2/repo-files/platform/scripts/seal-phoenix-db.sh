#!/usr/bin/env bash
# platform/scripts/seal-phoenix-db.sh — one Phoenix DB password, sealed into the two Secrets that must agree:
#   timescale-auth (postgres-password, phoenix-password)  and  phoenix-db-app (uri, the CNPG-style contract)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
D=platform/kubernetes/apps/phoenix-data/overlays/halo/sealed
mkdir -p "$D"
SUPER=$(openssl rand -hex 24); APP=$(openssl rand -hex 24)
echo "  postgres superuser password: $SUPER   <- password manager" >&2
echo "  phoenix app password:        $APP   <- password manager" >&2
kubectl -n phoenix create secret generic timescale-auth \
  --from-literal=postgres-password="$SUPER" --from-literal=phoenix-password="$APP" --dry-run=client -o yaml \
  | kubeseal --format yaml > "$D/timescale-auth.yaml"
kubectl -n phoenix create secret generic phoenix-db-app \
  --from-literal=uri="postgresql://phoenix:${APP}@timescale.phoenix.svc.cluster.local:5432/phoenix" \
  --dry-run=client -o yaml \
  | kubeseal --format yaml > "$D/phoenix-db-app.yaml"
unset SUPER APP
echo "wrote $D/timescale-auth.yaml and $D/phoenix-db-app.yaml"
