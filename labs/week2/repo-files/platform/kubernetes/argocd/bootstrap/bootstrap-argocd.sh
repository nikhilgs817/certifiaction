#!/usr/bin/env bash
# platform/kubernetes/argocd/bootstrap/bootstrap-argocd.sh — install Argo CD and hand the cluster to GitOps.
# Usage: platform/kubernetes/argocd/bootstrap/bootstrap-argocd.sh halo
#        (deploy key expected at ~/.ssh/argocd-<env>-deploy; override with DEPLOY_KEY=...)
set -euo pipefail
ENV="${1:-halo}"
CHART_VERSION="10.11.6"                     # <- the ONE place the Argo CD chart version is pinned for bootstrap
REPO_URL="git@github.com:nikhilgs817/ai-platform-portfolio.git"
DEPLOY_KEY="${DEPLOY_KEY:-$HOME/.ssh/argocd-${ENV}-deploy}"
SEALING_KEY="${SEALING_KEY:-$HOME/.secrets/sealed-secrets-key-${ENV}.yaml}"   # Week 2: from the password manager
A="$(git rev-parse --show-toplevel)/platform/kubernetes/argocd"

[ "$(kubectl config current-context)" = "$ENV" ] || { echo "kube context must be '$ENV'"; exit 1; }
[ -f "$DEPLOY_KEY" ] || { echo "Missing $DEPLOY_KEY: restore it from the password manager"; exit 1; }

echo ">> Argo CD chart ${CHART_VERSION}"
helm repo add argo https://argoproj.github.io/argo-helm --force-update >/dev/null
helm repo update argo >/dev/null
helm upgrade --install argocd argo/argo-cd --version "$CHART_VERSION" \
  --namespace argocd --create-namespace \
  -f "$A/install/values.yaml" -f "$A/install/values-${ENV}.yaml" \
  --wait --timeout 10m

echo ">> repository credential (in-cluster Secret only; never in Git)"
kubectl -n argocd create secret generic repo-ai-platform-portfolio \
  --from-literal=type=git --from-literal=name=ai-platform-portfolio \
  --from-literal=url="$REPO_URL" --from-file=sshPrivateKey="$DEPLOY_KEY" \
  --dry-run=client -o yaml \
| kubectl label --local -f - argocd.argoproj.io/secret-type=repository -o yaml \
| kubectl apply -f -

echo ">> Sealed Secrets key (must exist BEFORE the controller starts, or old SealedSecrets cannot be decrypted)"
if [ -f "$SEALING_KEY" ]; then
  kubectl apply -f "$SEALING_KEY"
else
  echo "   WARNING: $SEALING_KEY not found: the controller will generate a NEW key; re-seal every secret (runbook)"
fi

echo ">> AppProjects + root application"
kubectl apply -k "$A/projects"
kubectl apply -f "$A/bootstrap/root-${ENV}.yaml"

cat <<MSG
>> Bootstrap complete. Now:
   1) argocd login --username admin --password "\$(argocd admin initial-password -n argocd | head -1)"
   2) argocd account update-password   (use the password-manager value)
   3) kubectl -n argocd delete secret argocd-initial-admin-secret
MSG
