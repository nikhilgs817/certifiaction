#!/usr/bin/env bash
# platform/scripts/seal-secret.sh — create a namespace-scoped SealedSecret without plaintext ever touching disk.
# Usage: seal-secret.sh <namespace> <secret-name> <out.yaml> KEY[=gen|=fernet] ...
#   KEY=gen     random 48-hex-char value, printed ONCE: store it in your password manager
#   KEY=fernet  random Fernet key (urlsafe base64, 32 bytes), printed ONCE
#   KEY         prompts for the value (no echo)
set -euo pipefail
NS="${1:?}"; NAME="${2:?}"; OUT="${3:?}"; shift 3
args=()
for spec in "$@"; do
  key="${spec%%=*}"
  case "$spec" in
    *=gen)    val=$(openssl rand -hex 24);                    echo "  $NAME/$key = $val   <- password manager" >&2 ;;
    *=fernet) val=$(openssl rand -base64 32 | tr '+/' '-_');  echo "  $NAME/$key = $val   <- password manager" >&2 ;;
    *)        read -rsp "  value for $NAME/$key: " val; echo >&2 ;;
  esac
  args+=("--from-literal=$key=$val")
done
mkdir -p "$(dirname "$OUT")"
kubectl -n "$NS" create secret generic "$NAME" "${args[@]}" --dry-run=client -o yaml \
  | kubeseal --format yaml > "$OUT"
echo "wrote $OUT (namespace-scoped ciphertext; safe to commit)"
