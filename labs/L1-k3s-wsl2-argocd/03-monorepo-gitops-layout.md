# Step 4: Monorepo on GitHub + GitOps layout (block B5)

← [Steps 1–3](02-k3s-cluster.md) · Next → [Argo CD + app of apps](04-argocd-app-of-apps.md)

**Goal:** a private `ai-platform-portfolio` repo, cloned on WSL ext4, with the full skeleton, ADR-0001, the k3s host config captured as code, and the Argo CD folder layout ready for `halo` now and `aws` later.
**Why:** in GitOps, the repo *is* the platform's desired state. Argo CD only reconciles what's in it. Getting the folder contract right on day 1 means ten labs and two environments can be added without moving anything. The repo goes public in January, so secret hygiene (`.gitignore`, no keys, noreply e-mail) starts with the first commit.
**Where:** 🐙 then 🐧

---

## 4.1 Create the repo and your Git identity

🐙 **github.com → New repository**
- Name `ai-platform-portfolio`, **Private**, **no** README / .gitignore / license (you'll push the first commit).
- *Settings → Emails → "Keep my email addresses private"* is on. Copy your `ID+username@users.noreply.github.com` address.

🐧 your *personal* push key (separate from Argo CD's read-only deploy key later):

```bash
ssh-keygen -t ed25519 -C "halo-wsl-$(date +%Y%m)" -f ~/.ssh/id_ed25519_github -N ''
cat >> ~/.ssh/config <<'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_github
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
cat ~/.ssh/id_ed25519_github.pub
```

🐙 *Settings → SSH and GPG keys → New SSH key*, title `halo-wsl`, paste the `.pub` line.

```bash
ssh -T git@github.com            # "Hi nikhilgs817! You've successfully authenticated..."
git config --global user.name  "Nikhil G S"
git config --global user.email "ID+nikhilgs817@users.noreply.github.com"   # your noreply address
git config --global init.defaultBranch main
git config --global core.autocrlf input       # never commit CRLF from Windows editors
git config --global pull.rebase true

mkdir -p ~/src && cd ~/src
git clone git@github.com:nikhilgs817/ai-platform-portfolio.git
cd ai-platform-portfolio
code .        # VS Code opens in "WSL: halo" mode
```

> **Different GitHub username?** After creating all the files below, run:
> `grep -rl nikhilgs817 . --exclude-dir=.git | xargs sed -i 's/nikhilgs817/<your-user>/g'`

---

## 4.2 Skeleton, placeholders, `.gitignore`, `.gitattributes`

🐧 (inside `~/src/ai-platform-portfolio`)

```bash
# ---- directories with README placeholders (dir|purpose) ----
while IFS='|' read -r d purpose; do
  mkdir -p "$d"
  [ -f "$d/README.md" ] || printf '# %s\n\n%s\n\n_Status: placeholder._\n' "$(basename "$d")" "$purpose" > "$d/README.md"
done <<'EOF'
platform|The paved road: everything that runs the platform itself.
platform/terraform|AWS GPU node groups, SageMaker, networking (later labs). No state files in Git.
platform/kubernetes|GitOps tree reconciled by Argo CD. See layout below.
platform/k3s|Host-level config for k3s nodes (config.yaml, systemd units). Applied by install scripts, not Argo CD.
platform/helm-charts|Reusable charts, starting with the FastAPI service template (L1 week 2).
shared|Shared AI services used by several projects.
shared/llm-gateway|LiteLLM routing, budgets, fallbacks in front of self-hosted models (L2).
shared/rag-service|pgvector RAG that cites or abstains (L8 news RAG).
shared/mcp-servers|Read-only MCP tools (Phoenix data, docs) for agents (L2).
shared/eval-harness|Golden sets and CI eval gates for prompts, RAG and agents.
shared/observability|Prometheus, Loki, Tempo, OTel, Langfuse, OpenCost configs.
projects|Tenants that run on the platform.
projects/command-center|Phoenix Command Center: FastAPI core + UI, Timescale, Redis (first tenant).
projects/incident-resolution|AI-assisted incident triage (synthetic incidents only).
projects/release-command-center|Release readiness and change risk dashboard.
projects/code-review-agent|Self-hosted code review agent (pattern for the build-failure analyzer).
projects/sagemaker-stock-pipeline|Stock research ML platform: Feast, MLflow, Prefect, Evidently, SageMaker (L8).
docs|Documentation.
docs/architecture|Diagrams and platform overviews.
docs/adrs|Architecture Decision Records (one decision per file, numbered).
docs/runbooks|Operational procedures with measured results.
docs/demos|Demo scripts and recordings for interviews.
.github/workflows|Reusable GitHub Actions workflows (workflow_call) + a thin caller per service. Replaces a Jenkins shared library. CI arrives in Week 2.
.github/actions|Composite actions for repeated CI steps (for example setup, build-and-push to GHCR, promote image tag). Used by the reusable workflows.
EOF

# ---- .gitignore: secrets and junk never reach Git ----
cat > .gitignore <<'EOF'
# ---- secrets & credentials (repo becomes PUBLIC in Jan 2027) ----
*.pem
*.key
*.p12
*.pfx
id_rsa*
id_ed25519*
*deploy*key*
!**/*deploy*key*.md
kubeconfig*
*.kubeconfig
.kube/
.env
.env.*
!.env.example
*secret*.yaml
!**/sealed-secret*.yaml
*.age
*.gpg
credentials*
# ---- terraform ----
.terraform/
*.tfstate
*.tfstate.*
*.tfvars
!*.tfvars.example
crash.log
# ---- backups / disk images / model weights ----
*.tar
*.tar.gz
*.vhdx
*.gguf
*.safetensors
# ---- python / node / editors ----
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
.mypy_cache/
node_modules/
.idea/
.vscode/*
!.vscode/extensions.json
.DS_Store
Thumbs.db
EOF

# ---- .gitattributes: LF everywhere (shell scripts with CRLF break in WSL) ----
cat > .gitattributes <<'EOF'
* text=auto eol=lf
*.ps1 text eol=crlf
*.png binary
*.jpg binary
EOF
```

Root README:

```bash
cat > README.md <<'EOF'
# ai-platform-portfolio

A self-hosted **AI platform on Kubernetes**: GitOps delivery, a supply-chain-secured paved road,
self-hosted LLM serving (no per-token API bills), RAG with evals, observability and FinOps, and MLOps.
Built and operated as if it were production, on one home-lab box (`halo`) plus AWS for GPU work.

| Lab | What it proves | Status |
|---|---|---|
| L1 | Kubernetes AI deployment platform: k3s, Argo CD, Kustomize, Harbor, Trivy, Syft, cosign, Kyverno, Rollouts | 🚧 week 1: GitOps |
| L2 | Self-hosted agents: llama.cpp on Radeon, LiteLLM, read-only MCP tools | planned |
| L8 | Stock research ML platform: Feast, MLflow, Prefect, Evidently, SageMaker, RAG | planned |

**Ground rules:** synthetic or public data only · AI is read-only with a human in the loop ·
no secrets in Git · every version pinned · Argo CD is the only thing that applies app manifests.

Start at [`docs/adrs`](docs/adrs) and [`platform/kubernetes`](platform/kubernetes).
EOF
```

---

## 4.3 ADR-0001

```bash
cat > docs/adrs/0001-gitops-with-argocd-on-k3s-in-wsl2.md <<'EOF'
# ADR-0001: GitOps with Argo CD on k3s in WSL2

- **Status:** Accepted
- **Date:** 2026-11-02
- **Deciders:** Nikhil (platform owner)

## Context
The platform must host ten labs plus a real tenant (Phoenix: FastAPI, Timescale, Redis) around the clock
on a Windows 11 PC (Ryzen AI Max+ 395, 128 GB unified memory) that is also a daily driver, and later
extend to AWS GPU nodes. The end goal is to self-host several LLMs and cut per-token API spend. Goals:
production-like operations, CKA-relevant skills, reproducible rebuilds, nothing secret in a repo that
becomes public.

## Decision
1. **Runtime:** k3s v1.36 (pinned) as a native systemd service in an Ubuntu 24.04 WSL2 distro named `halo`.
   Embedded etcd, secrets encryption at rest, kubelet reservations. Node IP pinned to a dummy interface
   (10.255.255.10) so WSL's changing NAT IP never affects etcd or certificates.
2. **Networking:** WSL NAT mode + localhost forwarding. Traefik (bundled) runs with hostNetwork on :80/:443.
   Hostnames `*.halo.localhost` (browsers resolve these to loopback, no DNS needed).
3. **Delivery:** Argo CD (Helm chart, pinned) is the only actor that applies workloads. App of apps:
   one root Application per cluster (`clusters/<env>`), AppProjects `platform` and `lab`, Kustomize
   `base` + `overlays/<env>` per app. Automated sync with prune and selfHeal.
4. **Access:** Argo CD reads the private repo with a read-only SSH deploy key held only in the cluster
   and the password manager. Argo CD admin password lives only in the password manager.

## Alternatives considered
| Option | Why not (now) |
|---|---|
| k3d / kind | k3s inside Docker: extra runtime and network layer for long-lived workloads; good for CI throwaway clusters |
| Rancher Desktop / Docker Desktop Kubernetes | Hides systemd, certs, etcd: the things production and the CKA care about |
| kubeadm on Hyper-V VMs | Closest to the CKA exam, but heavier to run 24/7 on a daily PC; used separately for exam practice |
| Flux CD | Equally valid GitOps engine; Argo CD chosen for its UI (demo value), AppProjects (multi-tenancy) and Rollouts ecosystem |
| WSL mirrored networking | Node IP follows the active Windows adapter (Wi-Fi/VPN changes); NAT plus a pinned IP is more predictable |
| SQLite datastore (k3s default) | Fine for one node, but no etcd skills; etcd is safe here because the node IP is pinned |

## Consequences
- **+** Rebuild from Git in under an hour (k3s install script + Argo CD bootstrap); drift auto-reverted; audit trail = Git history.
- **+** The same repo layout extends to `aws` with a new root app and overlays, no restructuring.
- **−** Single node: no HA; node or disk loss means restoring from backups (wsl export, etcd snapshots, app backups).
- **−** WSL lifecycle (Windows updates, logon) affects uptime; mitigated by idle timeouts set to -1, a logon task and power settings.
- **−** No TLS in week 1 (`server.insecure`); acceptable on loopback only. Revisit with cert-manager.
- **−** GPU access from pods under WSL is non-standard (/dev/dxg, no device plugin); L2 starts with llama.cpp native on Windows as an external backend.
EOF
```

---

## 4.4 Capture the k3s host config as code (`platform/k3s/halo/`)

**Why:** the k3s config, Traefik override and systemd units are *host* config. Argo CD can't apply them because they have to exist before the cluster does. Keeping them in Git, with an install script, makes the rebuild drill (Step 9) a two-command job. It's the Ansible-role equivalent, without needing Ansible yet.

```bash
D=platform/k3s/halo; mkdir -p "$D"
WINHOME=$(wslpath "$(/mnt/c/Windows/System32/cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')")
sudo cp /etc/rancher/k3s/config.yaml                                "$D/config.yaml"
sudo cp /var/lib/rancher/k3s/server/manifests/traefik-config.yaml   "$D/traefik-config.yaml"
cp /etc/systemd/system/halo-node-ip.service                         "$D/halo-node-ip.service"
cp /etc/systemd/system/k3s.service.d/10-halo-node-ip.conf           "$D/10-halo-node-ip.conf"
cp /etc/modules-load.d/k3s.conf                                     "$D/modules-k3s.conf"
cp /etc/sysctl.d/90-k3s.conf                                        "$D/sysctl-90-k3s.conf"
cp /etc/wsl.conf                                                    "$D/wsl.conf"
cp "$WINHOME/.wslconfig"                                            "$D/wslconfig.ini"
sudo chown "$USER:" "$D"/*
```

`platform/k3s/halo/install-k3s.sh`, idempotent:

```bash
cat > platform/k3s/halo/install-k3s.sh <<'EOF'
#!/usr/bin/env bash
# platform/k3s/halo/install-k3s.sh — install/reinstall k3s on node "halo" from the files in this folder.
# Usage (inside WSL, from repo root):  sudo platform/k3s/halo/install-k3s.sh
set -euo pipefail
K3S_VERSION="v1.36.5+k3s1"          # <- the ONE place the k3s version is pinned
DIR="$(cd "$(dirname "$0")" && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo"; exit 1; }

echo ">> host prerequisites"
install -D -m 0644 "$DIR/modules-k3s.conf"       /etc/modules-load.d/k3s.conf
install -D -m 0644 "$DIR/sysctl-90-k3s.conf"     /etc/sysctl.d/90-k3s.conf
systemctl restart systemd-modules-load
sysctl --system >/dev/null

echo ">> stable node IP (halo0)"
install -D -m 0644 "$DIR/halo-node-ip.service"   /etc/systemd/system/halo-node-ip.service
install -D -m 0644 "$DIR/10-halo-node-ip.conf"   /etc/systemd/system/k3s.service.d/10-halo-node-ip.conf
systemctl daemon-reload
systemctl enable --now halo-node-ip.service

echo ">> k3s config + Traefik override"
install -D -m 0600 "$DIR/config.yaml"            /etc/rancher/k3s/config.yaml
install -D -m 0600 "$DIR/traefik-config.yaml"    /var/lib/rancher/k3s/server/manifests/traefik-config.yaml

echo ">> k3s ${K3S_VERSION}"
curl -fsSL -o /tmp/k3s-install.sh "https://raw.githubusercontent.com/k3s-io/k3s/${K3S_VERSION/+/%2B}/install.sh"
INSTALL_K3S_VERSION="$K3S_VERSION" sh /tmp/k3s-install.sh

echo ">> waiting for node Ready"
for i in $(seq 1 60); do
  k3s kubectl get node halo 2>/dev/null | grep -q ' Ready' && break; sleep 5
done
k3s kubectl get nodes -o wide
echo ">> done. Next: refresh your kubeconfig (see docs/runbooks/rebuild-halo.md)"
EOF
chmod +x platform/k3s/halo/install-k3s.sh

cat > platform/k3s/halo/README.md <<'EOF'
# platform/k3s/halo — host config for node "halo" (k3s in WSL2)

Applied by `install-k3s.sh` (not by Argo CD: these must exist before the cluster does).

| File | Installed to | Purpose |
|---|---|---|
| `config.yaml` | `/etc/rancher/k3s/config.yaml` | k3s server config (node IP, SANs, etcd, kubelet reservations) |
| `traefik-config.yaml` | `/var/lib/rancher/k3s/server/manifests/` | HelmChartConfig: Traefik hostNetwork :80/:443 |
| `halo-node-ip.service` | `/etc/systemd/system/` | dummy NIC `halo0` = 10.255.255.10 (stable node IP) |
| `10-halo-node-ip.conf` | `/etc/systemd/system/k3s.service.d/` | k3s starts after halo0 |
| `modules-k3s.conf`, `sysctl-90-k3s.conf` | `/etc/modules-load.d/`, `/etc/sysctl.d/` | kernel prerequisites |
| `wsl.conf` | `/etc/wsl.conf` (manual) | systemd, hostname, PATH hygiene |
| `wslconfig.ini` | `C:\Users\<you>\.wslconfig` (manual) | VM size, NAT, idle timeouts |
EOF
```

---

## 4.5 The GitOps layout (`platform/kubernetes/`)

**Recommended layout, and why:**

```
platform/kubernetes/
├── README.md
├── argocd/
│   ├── install/                    # Helm values for Argo CD itself
│   │   ├── values.yaml             #   common to every cluster
│   │   └── values-halo.yaml        #   per-cluster overrides (domain, sizing)
│   ├── bootstrap/                  # the ONLY manifests ever applied by hand (kubectl apply)
│   │   └── root-halo.yaml          #   root Application for cluster "halo"
│   ├── projects/                   # AppProjects (guardrails), managed by Argo CD after bootstrap
│   │   ├── kustomization.yaml
│   │   ├── platform.yaml
│   │   └── lab.yaml
│   └── clusters/                   # one folder per cluster = what the root app syncs
│       ├── halo/
│       │   ├── kustomization.yaml  #   list of child Applications on halo
│       │   ├── projects.yaml       #   child app → argocd/projects
│       │   └── podinfo.yaml        #   child app → apps/podinfo/overlays/halo   (Step 7)
│       └── aws/                    #   placeholder: root-aws will point here later
└── apps/                           # workloads, one folder per app
    └── podinfo/                    # (Step 7)
        ├── base/                   #   environment-neutral manifests
        └── overlays/
            ├── halo/               #   this box: replicas, host, quota, image tag
            └── aws/                #   placeholder
```

- **`clusters/<env>` holds Application manifests only.** It answers "what runs on this cluster?" in one file listing. Adding `aws` later means `bootstrap/root-aws.yaml` plus `clusters/aws/*.yaml` pointing at `apps/*/overlays/aws`.
- **`apps/<name>/overlays/<env>` holds the per-environment differences.** It answers "how does it differ there?" The base never knows about environments.
- **`bootstrap/` is tiny on purpose.** Everything else is reconciled, so a rebuild is `helm install` plus one `kubectl apply`.
- **Explicit Applications now, ApplicationSet later.** When you reach about 10 apps × 2 clusters, one ApplicationSet with a Git directory generator can replace the hand-written files in `clusters/<env>`. The folder contract stays the same.

> **Jenkins analogy:** `clusters/halo/kustomization.yaml` is the *seed job* (which pipelines exist). Each `Application` is a pipeline that never stops running. `overlays/halo` is that environment's parameter file.

Now create the files.

```bash
mkdir -p platform/kubernetes/argocd/{install,bootstrap,projects,clusters/halo,clusters/aws} platform/kubernetes/apps
```

### `platform/kubernetes/argocd/install/values.yaml`
```bash
cat > platform/kubernetes/argocd/install/values.yaml <<'EOF'
# platform/kubernetes/argocd/install/values.yaml
# Common Argo CD values for every cluster. Chart argo/argo-cd 10.11.6 (Argo CD v3.5.6).
# NO secrets here: admin password is set via CLI and stored in the password manager.
global:
  domain: argocd.example.invalid      # overridden per cluster (values-<env>.yaml)
  revisionHistoryLimit: 3

configs:
  params:
    server.insecure: true             # TLS terminates at the ingress; no TLS in week 1 (loopback only)
  cm:
    admin.enabled: true               # local admin until SSO/OIDC (production: false)
    exec.enabled: false               # no web terminal into pods
    statusbadge.enabled: false
    timeout.reconciliation: 180s      # Git poll interval (+ jitter); prod uses webhooks
  rbac:
    policy.default: role:readonly     # any future SSO user is read-only unless granted more
  secret:
    createSecret: true                # chart creates argocd-secret; password is NOT set here

dex:
  enabled: false                      # no SSO yet

notifications:
  enabled: false                      # later: alert on sync failures / degraded health

controller:
  replicas: 1
  resources:
    requests: { cpu: 250m, memory: 512Mi }
    limits:   { memory: 2Gi }

repoServer:
  replicas: 1
  resources:
    requests: { cpu: 100m, memory: 256Mi }
    limits:   { memory: 1Gi }

server:
  replicas: 1
  resources:
    requests: { cpu: 50m, memory: 128Mi }
    limits:   { memory: 512Mi }
  ingress:
    enabled: true
    ingressClassName: traefik         # hostname defaults to global.domain
    tls: false

applicationSet:
  replicas: 1                         # kept for multi-cluster generators later
  resources:
    requests: { cpu: 25m, memory: 64Mi }
    limits:   { memory: 256Mi }

redis:
  resources:
    requests: { cpu: 50m, memory: 64Mi }
    limits:   { memory: 256Mi }
EOF
```

### `platform/kubernetes/argocd/install/values-halo.yaml`
```bash
cat > platform/kubernetes/argocd/install/values-halo.yaml <<'EOF'
# platform/kubernetes/argocd/install/values-halo.yaml — overrides for cluster "halo"
global:
  domain: argocd.halo.localhost       # browser resolves *.localhost to 127.0.0.1
EOF
```

### `platform/kubernetes/argocd/projects/*`
```bash
cat > platform/kubernetes/argocd/projects/platform.yaml <<'EOF'
# platform/kubernetes/argocd/projects/platform.yaml
# Platform-owned components: root apps, Argo CD itself, cluster add-ons. Full cluster scope.
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: platform
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
    argocd.argoproj.io/sync-options: Prune=false   # never auto-delete a project
spec:
  description: Platform components owned by the platform team
  sourceRepos:
    - git@github.com:nikhilgs817/ai-platform-portfolio.git
    - https://argoproj.github.io/argo-helm          # Step 10: Argo CD manages its own chart
  destinations:
    - server: https://kubernetes.default.svc
      namespace: '*'
  clusterResourceWhitelist:
    - group: '*'
      kind: '*'
EOF

cat > platform/kubernetes/argocd/projects/lab.yaml <<'EOF'
# platform/kubernetes/argocd/projects/lab.yaml
# Tenant workloads (samples, Phoenix, LLM services). Least privilege: listed namespaces only,
# no cluster-scoped resources except the Namespace that CreateNamespace=true needs.
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: lab
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
    argocd.argoproj.io/sync-options: Prune=false
spec:
  description: Tenant workloads on the halo/aws platform
  sourceRepos:
    - git@github.com:nikhilgs817/ai-platform-portfolio.git
  destinations:                                    # add one entry per tenant namespace, via PR
    - server: https://kubernetes.default.svc
      namespace: podinfo
  clusterResourceWhitelist:
    - group: ''
      kind: Namespace
  orphanedResources:
    warn: true                                     # flag anything in tenant namespaces not in Git
EOF

cat > platform/kubernetes/argocd/projects/kustomization.yaml <<'EOF'
# platform/kubernetes/argocd/projects/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - platform.yaml
  - lab.yaml
EOF
```

### `platform/kubernetes/argocd/bootstrap/root-halo.yaml`
```bash
cat > platform/kubernetes/argocd/bootstrap/root-halo.yaml <<'EOF'
# platform/kubernetes/argocd/bootstrap/root-halo.yaml
# The root ("app of apps") for cluster halo. Applied ONCE by hand at bootstrap; everything below it is GitOps.
# Deliberately NO resources-finalizer: deleting the root must never cascade-delete every app.
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root-halo
  namespace: argocd
  labels:
    lab.platform/env: halo
spec:
  project: platform
  source:
    repoURL: git@github.com:nikhilgs817/ai-platform-portfolio.git
    targetRevision: main
    path: platform/kubernetes/argocd/clusters/halo
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
    retry:
      limit: 5
      backoff: { duration: 10s, factor: 2, maxDuration: 3m }
EOF
```

### `platform/kubernetes/argocd/clusters/halo/*`
```bash
cat > platform/kubernetes/argocd/clusters/halo/projects.yaml <<'EOF'
# platform/kubernetes/argocd/clusters/halo/projects.yaml — Argo CD manages its own AppProjects
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: argocd-projects
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "-10"            # projects before the apps that use them
spec:
  project: platform
  source:
    repoURL: git@github.com:nikhilgs817/ai-platform-portfolio.git
    targetRevision: main
    path: platform/kubernetes/argocd/projects
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
EOF

cat > platform/kubernetes/argocd/clusters/halo/kustomization.yaml <<'EOF'
# platform/kubernetes/argocd/clusters/halo/kustomization.yaml
# Everything that runs on cluster "halo" = the child Applications listed here.
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - projects.yaml
  # - podinfo.yaml        # Step 7
  # - argocd.yaml         # Step 10 (optional)
EOF

cat > platform/kubernetes/argocd/clusters/aws/README.md <<'EOF'
# clusters/aws — placeholder

Future root: `bootstrap/root-aws.yaml` → this folder. Child Applications here point at
`apps/<name>/overlays/aws`. Intentionally empty until the AWS GPU labs.
EOF

cat > platform/kubernetes/apps/README.md <<'EOF'
# apps — one folder per workload

`<app>/base` is environment-neutral; `<app>/overlays/<env>` (halo, aws) carries replicas, hosts, quotas
and image tags. Argo CD child Applications in `argocd/clusters/<env>/` point at the overlays.
EOF
```

### `platform/kubernetes/README.md`
```bash
cat > platform/kubernetes/README.md <<'EOF'
# platform/kubernetes — the GitOps tree

Argo CD reconciles this folder. Humans change it only through Git.

| Path | Applied by | Purpose |
|---|---|---|
| `argocd/install/` | `helm upgrade --install` (bootstrap) or Argo CD itself (Step 10) | Argo CD Helm values |
| `argocd/bootstrap/root-<env>.yaml` | `kubectl apply` once per cluster | root Application (app of apps) |
| `argocd/projects/` | Argo CD (`argocd-projects` app) | AppProjects `platform`, `lab` |
| `argocd/clusters/<env>/` | Argo CD (root app) | child Applications for that cluster |
| `apps/<app>/base`, `apps/<app>/overlays/<env>` | Argo CD (child apps) | workloads via Kustomize |

Environments: `halo` (home lab, k3s in WSL2) and `aws` (later, GPU).
EOF
```

---

## 4.6 Check for secrets, commit, push

```bash
git add -A
git status --short
# Nothing private should match:
git grep -nIE 'BEGIN [A-Z ]*PRIVATE KEY|client-key-data|token:|password:' -- . ':!*.md' || echo "secret scan: clean"
git commit -m "feat(L1): monorepo skeleton, ADR-0001, k3s host config, Argo CD GitOps layout"
git push -u origin main
```

**Expected:** `secret scan: clean`, then `* [new branch] main -> main`.
**Verify:** 🐙 refresh the repo and you should see the tree above and the README rendered.

- [ ] Repo private, first commit on `main`
- [ ] `platform/k3s/halo/` holds config.yaml, traefik-config.yaml, units, install script
- [ ] ADR-0001 present

**If it fails**
1. `Permission denied (publickey)` → `ssh -vT git@github.com` and check that `~/.ssh/config` points at `id_ed25519_github` and the key is added to your *account* (not as a deploy key).
2. The secret scan matches `password:` in a YAML comment → reword the comment. Never commit and then try to "fix it later". Git history is forever once the repo is public.
3. Scripts fail later with `$'\r': command not found` → the file was saved with CRLF. Check `.gitattributes`, then run `git add --renormalize . && git commit`.

### CKA corner: Step 4
- **Domain:** Workloads & Scheduling (manifests, Kustomize is built into kubectl).
- **Practise:** `kubectl kustomize platform/kubernetes/argocd/projects` · `kubectl apply -k <dir> --dry-run=server` · `kubectl explain appproject.spec --recursive | head -40` (once Argo CD is installed) · `kubectl diff -k <dir>`
- **Drill:** `kubectl create configmap app-cfg --from-literal=MODE=lab $do > cm.yaml`, then write a `kustomization.yaml` that includes it and adds `namespace: dev` + label `env=dev`; render it with `kubectl kustomize .`.

**Interview angle:** "I designed the repo contract first: clusters list Applications, apps carry base plus environment overlays, and only a one-file bootstrap is ever applied by hand. A second region or cluster is additive, not a refactor."
**Phoenix angle:** Phoenix gets `apps/command-center/{base,overlays/halo}` and one line in `clusters/halo`. Its source code stays in `projects/command-center/`, and its deployment is reviewed like any other change.
