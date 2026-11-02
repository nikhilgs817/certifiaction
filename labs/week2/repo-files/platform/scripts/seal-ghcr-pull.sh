#!/usr/bin/env bash
# platform/scripts/seal-ghcr-pull.sh — seal the GHCR pull credential once, for every namespace (cluster-wide scope).
# Needs: kubeseal + access to the cluster (it fetches the controller's public cert). Writes ciphertext only.
set -euo pipefail
OWNER="${1:-nikhilgs817}"
cd "$(git rev-parse --show-toplevel)"
OUT=platform/kubernetes/apps/_shared/halo/values.yaml
[ -f "$OUT" ] || { echo "create $OUT first (Step A4)"; exit 1; }

read -rsp "GHCR token (classic PAT, scope read:packages only): " PAT; echo
ENC=$(kubectl create secret docker-registry ghcr-pull \
        --docker-server=ghcr.io --docker-username="$OWNER" --docker-password="$PAT" \
        --dry-run=client -o yaml \
      | kubeseal --scope cluster-wide --format yaml \
      | yq '.spec.encryptedData.".dockerconfigjson"')
unset PAT
ENC="$ENC" yq -i '.imagePullSecret.encryptedDockerConfigJson = strenv(ENC)' "$OUT"
echo "Sealed into $OUT (ciphertext only; safe to commit)."
