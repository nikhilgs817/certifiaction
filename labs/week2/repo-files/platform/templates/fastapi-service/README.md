# platform/templates/fastapi-service — Copier template

Creates, in one go: `projects/<name>/` (FastAPI app, tests, Makefile, Dockerfile), `platform/kubernetes/apps/<name>/`
(Helm values for `platform/helm-charts/service`), the Argo CD Application in `argocd/clusters/halo/`, and the
caller workflow `.github/workflows/svc-<name>.yml`. Use `platform/scripts/new-service.sh <name>`.
