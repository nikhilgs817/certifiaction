# ADR-0002: Paved road for services — Copier template, shared Helm chart, GitHub Actions, Sealed Secrets

- **Status:** Accepted · **Date:** 2026-11-12

## Context
Every lab adds services (Phoenix, LLM gateway, RAG, MCP tools). Each must build, ship and run the same way, from one
monorepo, with no plaintext secrets in a repository that becomes public in January 2027. CI is GitHub Actions only.

## Decision
1. **Generator: Copier**, template in `platform/templates/fastapi-service`, run via `platform/scripts/new-service.sh`.
   It records answers per service, so `copier update` can roll template changes out later.
2. **One shared Helm chart** `platform/helm-charts/service` (Deployment, Service, Ingress, ServiceAccount, ConfigMap,
   PDB, HPA, workers, migration hook, one-shot jobs, optional namespace guardrails). Argo CD renders it with layered
   value files: `_shared/<env>` -> `apps/<svc>/base` -> `apps/<svc>/overlays/<env>`.
3. **CI: one reusable workflow** `_service-ci.yml` (verify -> image -> promote) plus composite actions; each service has
   a thin caller with path filters. The contract with a service is `make ci` and a Dockerfile.
4. **Images: GHCR**, private, tag = full git SHA, never `latest`. Harbor replaces GHCR in Week 4.
5. **Promotion: CI commits the tag** into `overlays/<env>/values.yaml` (not Argo CD Image Updater).
6. **Secrets: Sealed Secrets** (controller 0.41.2). Ciphertext in Git; the sealing key in the password manager.

## Alternatives
| Option | Why not now |
|---|---|
| cookiecutter | No update path for existing services; Copier has `copier update` and answer files |
| Plain copy script | Fast to write, but drift between services starts on day 2 |
| Kustomize `helmCharts` | Needs `--enable-helm` in Argo CD and a local chart path outside the kustomization root |
| Argo CD Image Updater (v1.x, CRD-based) | Needs registry and Git write credentials in the cluster, polls, and hides promotion from the PR flow |
| SOPS + age | Great for Terraform later; with Argo CD it needs a repo-server plugin (KSOPS/helm-secrets) to decrypt |

## Consequences
- A new service runs through Argo CD in under 15 minutes; the chart and workflow are fixed in one place for all.
- A chart change affects every service at once: `platform-checks.yml` renders all consumers on every chart PR.
- Losing the sealing key means re-sealing every secret (runbook `bootstrap-secrets.md`).
- The bot commits to `main`; requiring PRs on `main` later means switching promotion to a GitHub App or PR-based flow.
