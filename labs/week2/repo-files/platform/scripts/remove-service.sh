#!/usr/bin/env bash
# platform/scripts/remove-service.sh — remove a template service in two safe commits.
# Usage:  remove-service.sh <name>            step 1: delete code, values, CI caller and the Argo CD app
#         remove-service.sh <name> --finalize step 2 (after Argo CD pruned it): drop the AppProject destination
set -euo pipefail
NAME="${1:?usage: remove-service.sh <name> [--finalize]}"
cd "$(git rev-parse --show-toplevel)"
NS=$(yq '.namespace // ""' ".copier-answers/$NAME.yml" 2>/dev/null || true)
NS="${NS:-$NAME}"

if [ "${2:-}" = "--finalize" ]; then
  if [ "$NS" = "$NAME" ]; then
    yq -i "del(.spec.destinations[] | select(.namespace == \"$NS\"))" platform/kubernetes/argocd/projects/lab.yaml
  fi
  rm -f ".copier-answers/$NAME.yml"
  echo "Step 2 done. Commit + push, then: kubectl delete namespace $NS   (and delete the GHCR package)"
  exit 0
fi

rm -rf "projects/$NAME" "platform/kubernetes/apps/$NAME" \
       ".github/workflows/svc-$NAME.yml" "platform/kubernetes/argocd/clusters/halo/$NAME.yaml"
yq -i "del(.resources[] | select(. == \"$NAME.yaml\"))" platform/kubernetes/argocd/clusters/halo/kustomization.yaml
echo "Step 1 done. Commit + push, wait until 'argocd app get $NAME' says not found, then run with --finalize."
