#!/usr/bin/env bash
# platform/scripts/new-service.sh — create a paved-road service: code, chart values, Argo CD app, CI caller.
# Usage (WSL, anywhere in the repo):  platform/scripts/new-service.sh <name> [namespace]
set -euo pipefail
NAME="${1:?usage: new-service.sh <name> [namespace]}"
NS="${2:-$NAME}"
COPIER_VERSION="9.19.1"
cd "$(git rev-parse --show-toplevel)"

[[ "$NAME" =~ ^[a-z][a-z0-9-]{1,28}[a-z0-9]$ ]] || { echo "name must match ^[a-z][a-z0-9-]{1,28}[a-z0-9]$"; exit 1; }
[ ! -e "projects/$NAME" ] || { echo "projects/$NAME already exists"; exit 1; }
[ -f platform/kubernetes/apps/_shared/halo/values.yaml ] || { echo "missing apps/_shared/halo/values.yaml (Step A4)"; exit 1; }

uvx "copier@${COPIER_VERSION}" copy --quiet --defaults \
  --data "service_name=$NAME" --data "namespace=$NS" \
  --answers-file ".copier-answers/$NAME.yml" \
  platform/templates/fastapi-service .

(cd "projects/$NAME" && uv lock --quiet)

K=platform/kubernetes/argocd/clusters/halo/kustomization.yaml
yq -i ".resources += [\"$NAME.yaml\"] | .resources |= unique" "$K"
L=platform/kubernetes/argocd/projects/lab.yaml
yq -i ".spec.destinations += [{\"server\": \"https://kubernetes.default.svc\", \"namespace\": \"$NS\"}]
       | .spec.destinations |= unique_by(.namespace)" "$L"

cat <<MSG
Created service "$NAME" (namespace "$NS"):
  projects/$NAME/   platform/kubernetes/apps/$NAME/   argocd/clusters/halo/$NAME.yaml   .github/workflows/svc-$NAME.yml
Next:
  (cd projects/$NAME && make ci)
  git add -A && git commit -m "feat($NAME): new service from the paved-road template" && git push
MSG
