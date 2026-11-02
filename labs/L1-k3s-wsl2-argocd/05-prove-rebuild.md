# Steps 8–10: Prove GitOps, rebuild drill, Argo CD manages itself (blocks B8–B10)

← [Steps 5–7](04-argocd-app-of-apps.md) · Next → [Appendix](06-appendix.md)

Keep two windows open for all of Step 8:
- **Window A (🐧):** `watch -n2 'kubectl -n podinfo get deploy,rs,pods -o wide; echo; argocd app list'`
- **Window B (🌐):** the Argo CD UI on the `podinfo` app (tree view), plus a tab on `http://podinfo.halo.localhost`

---

## Step 8: Prove GitOps works (B8)

### 8a: Change replicas in Git, push, watch it sync

**Why:** proves the main GitOps loop: *commit → Argo CD notices → cluster converges*. Nobody runs `kubectl apply`.
**Where:** 🐧 (repo root)

```bash
cd ~/src/ai-platform-portfolio
sed -i 's/^  replicas: 2 .*/  replicas: 3                            # Step 8a/' platform/kubernetes/apps/podinfo/overlays/halo/patch-deployment.yaml
git diff --stat && git commit -am "podinfo(halo): scale to 3 replicas" && git push
argocd app get podinfo --refresh | grep -E 'Sync Status|Health Status'
```

**Expected:** within seconds (thanks to `--refresh`; otherwise within about 3–4 min by polling), a third pod appears and the app returns to `Synced` / `Healthy` at the new commit SHA. The browser hostname now rotates across 3 pods.
**Verify:** `kubectl -n podinfo get deploy podinfo -o jsonpath='{.spec.replicas}{"\n"}'` → `3`
- [ ] 8a done

> Production uses a GitHub **webhook** to Argo CD so syncs start instantly. That needs a reachable endpoint; the 180 s poll is the lab equivalent.

### 8b: `kubectl delete` the Deployment, watch Argo CD bring it back

**Why:** proves *self-heal for deletions*. The cluster is a cache of Git, not the source of truth.

```bash
kubectl -n podinfo delete deployment podinfo
sleep 15; kubectl -n podinfo get deploy podinfo
argocd app get podinfo | grep -E 'Sync Status|Health Status'
```

**Expected:** the Deployment is recreated within about 5–15 s (`AGE` a few seconds). The app goes briefly `OutOfSync`/`Missing`, then back to `Synced`/`Healthy`. The UI's *Events* show the auto-sync.
- [ ] 8b done

### 8c: `kubectl scale` by hand, watch the drift get reverted

**Why:** proves *self-heal for drift*. In a large organisation, this is what stops a 2 a.m. hand change from quietly becoming permanent.

```bash
kubectl -n podinfo scale deployment podinfo --replicas=5
sleep 10; kubectl -n podinfo get deploy podinfo
```

**Expected:** replicas jump to 5, then within seconds Argo CD sets them back to **3**, and the extra pods terminate.
- [ ] 8c done

> Later, with an HPA, you'll tell Argo CD to ignore `spec.replicas` (`ignoreDifferences`). Otherwise Argo CD and the HPA fight.

### 8d: Push a bad change (wrong image tag), see Degraded, fix with `git revert`

**Why:** shows what failure looks like and why rollback is a **Git operation**. With `maxUnavailable: 0` the old pods keep serving, so users never notice. `kubectl rollout undo` would be undone by selfHeal, and `argocd app rollback` is blocked while auto-sync is on. The supported rollback is `git revert`.

```bash
sed -i 's/newTag: "6.17.0" .*/newTag: "6.99.0"                     # Step 8d: does not exist/' platform/kubernetes/apps/podinfo/overlays/halo/kustomization.yaml
git commit -am "podinfo(halo): bump to 6.99.0 (intentionally broken)" && git push
argocd app get podinfo --refresh >/dev/null
sleep 30; kubectl -n podinfo get pods
curl -s -H 'Host: podinfo.halo.localhost' http://127.0.0.1/version     # still 6.17.0: old pods serve
sleep 100; argocd app get podinfo | grep -E 'Sync Status|Health Status'
```

**Expected:** one new pod shows `ErrImagePull` → `ImagePullBackOff`, the 3 old pods stay `Running`, and the app is **Synced** but **Degraded** after `progressDeadlineSeconds` (120 s). `kubectl -n podinfo describe deploy podinfo | grep -A2 Progressing` shows `ProgressDeadlineExceeded`.

Fix it:
```bash
git revert --no-edit HEAD && git push
argocd app get podinfo --refresh >/dev/null
argocd app wait podinfo --health --timeout 180
```

**Expected:** the broken ReplicaSet scales to 0 and the app returns to `Healthy`. Git history now shows the bad commit *and* its revert, which is your audit trail.
- [ ] 8d done (Degraded seen, recovered by revert)

### 8e: Find the sync history in the UI and the CLI

```bash
argocd app history podinfo
kubectl -n argocd get application podinfo -o jsonpath='{range .status.history[*]}{.id}{"  "}{.revision}{"  "}{.deployedAt}{"\n"}{end}'
git log --oneline -6
```

🌐 UI: app `podinfo` → **History and Rollback**. Each entry is a deployed Git SHA with a timestamp, matching `git log`.

**Expected:** at least 4 entries (initial, scale to 3, broken 6.99.0, revert). The SHAs match `git log`.
- [ ] 8e done

### 8f: `wsl --shutdown`, start again, confirm self-recovery

**Where:** 🪟

```powershell
wsl --shutdown
Start-Sleep 10
Start-ScheduledTask -TaskName 'WSL-halo-keepalive'
Start-Sleep 90
kubectl get nodes
kubectl -n argocd get pods
argocd app list
curl.exe -s http://podinfo.halo.localhost/version
```

**Expected:** node `Ready`, all Argo CD pods `Running`, `root-halo`, `argocd-projects` and `podinfo` all `Synced`/`Healthy`, and curl returns `6.17.0`. You didn't touch anything. If you have time, also do a real Windows restart and check the same after logging in.
- [ ] 8f done

### CKA corner: Step 8
- **Domain:** Troubleshooting (30%), the biggest domain. Also Workloads (rollouts).
- **Practise:** `k -n podinfo describe pod <failing>` (read *Events*) · `k -n podinfo get events --sort-by=.lastTimestamp | tail` · `k -n podinfo rollout status deploy/podinfo --timeout=30s` · `k -n podinfo get rs -o wide` · `k -n podinfo logs deploy/podinfo --tail=20`
- **Drill (no Argo CD, in a scratch namespace):** `k create deploy web --image=nginx:1.29 -n scratch` → `k set image deploy/web nginx=nginx:9.9.9 -n scratch` → diagnose → `k rollout undo deploy/web -n scratch` → `k rollout history deploy/web -n scratch`. On the exam, `rollout undo` *is* the answer. Under GitOps it's `git revert`. Know both.

**Interview angle:** "I can show a live demo: a manual delete, a manual scale and a bad image push, each reverted or contained automatically, with rollback done as a Git revert and the full deployment history tied to commit SHAs."
**Phoenix angle:** a bad Phoenix release can't take down the running Command Center (old pods keep serving), and recovery is one `git revert` from your phone's GitHub app.

---

## Step 9: Rebuild drill (B9)

**Goal:** destroy the lab and prove that **Git + two secrets** (deploy key, admin password) bring everything back. Measure the time (your RTO).
**Why:** a backup you haven't restored isn't a backup. This drill tests the whole chain: WSL snapshot → host config from Git → k3s → Argo CD bootstrap → apps from Git. It's a DR test, the VMware "restore from template and re-run the playbooks" exercise.

### 9.1 Add the two bootstrap scripts to the repo (🐧)

```bash
cd ~/src/ai-platform-portfolio

cat > platform/k3s/halo/install-clients.sh <<'EOF'
#!/usr/bin/env bash
# platform/k3s/halo/install-clients.sh — pinned kubectl/helm/argocd/k9s in WSL + kubeconfig "halo" (+ copy to Windows)
# Usage (as your user, NOT sudo): platform/k3s/halo/install-clients.sh
set -euo pipefail
KV=v1.36.6; HV=v4.3.1; AV=v3.5.6; K9V=v0.51.0
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT; cd "$T"
curl -fsSLO "https://dl.k8s.io/release/${KV}/bin/linux/amd64/kubectl"
curl -fsSLO "https://dl.k8s.io/release/${KV}/bin/linux/amd64/kubectl.sha256"
echo "$(cat kubectl.sha256)  kubectl" | sha256sum --check --quiet
sudo rm -f /usr/local/bin/kubectl && sudo install -m 0755 kubectl /usr/local/bin/kubectl
curl -fsSLO "https://get.helm.sh/helm-${HV}-linux-amd64.tar.gz"
curl -fsSLO "https://get.helm.sh/helm-${HV}-linux-amd64.tar.gz.sha256sum"
sha256sum --check --quiet "helm-${HV}-linux-amd64.tar.gz.sha256sum"
tar xzf "helm-${HV}-linux-amd64.tar.gz" && sudo install -m 0755 linux-amd64/helm /usr/local/bin/helm
curl -fsSLO "https://github.com/argoproj/argo-cd/releases/download/${AV}/argocd-linux-amd64"
curl -fsSLO "https://github.com/argoproj/argo-cd/releases/download/${AV}/cli_checksums.txt"
grep ' argocd-linux-amd64$' cli_checksums.txt | sha256sum --check --quiet
sudo install -m 0755 argocd-linux-amd64 /usr/local/bin/argocd
curl -fsSLO "https://github.com/derailed/k9s/releases/download/${K9V}/k9s_Linux_amd64.tar.gz"
curl -fsSLO "https://github.com/derailed/k9s/releases/download/${K9V}/checksums.sha256"
grep ' k9s_Linux_amd64.tar.gz$' checksums.sha256 | sha256sum --check --quiet
tar xzf k9s_Linux_amd64.tar.gz k9s && sudo install -m 0755 k9s /usr/local/bin/k9s

# kubeconfig: context/cluster/user all named "halo"
mkdir -p ~/.kube
sudo cat /etc/rancher/k3s/k3s.yaml | sed -e 's/: default$/: halo/' > ~/.kube/config
chmod 600 ~/.kube/config
WINHOME=$(wslpath "$(/mnt/c/Windows/System32/cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')")
mkdir -p "$WINHOME/.kube" && cp ~/.kube/config "$WINHOME/.kube/config"

# shell setup (idempotent)
if ! grep -q '# --- k8s tooling (CKA habits) ---' ~/.bashrc; then cat >> ~/.bashrc <<'RC'
# --- k8s tooling (CKA habits) ---
source <(kubectl completion bash)
source <(helm completion bash)
source <(argocd completion bash)
alias k=kubectl
complete -o default -F __start_kubectl k
export do="--dry-run=client -o yaml"
export now="--force --grace-period 0"
export ARGOCD_OPTS="--port-forward --port-forward-namespace argocd --plaintext"
RC
fi
kubectl version && helm version --short && argocd version --client --short
echo "Windows kubeconfig refreshed (new cluster CA). Open a new shell: source ~/.bashrc"
EOF
chmod +x platform/k3s/halo/install-clients.sh

cat > platform/kubernetes/argocd/bootstrap/bootstrap-argocd.sh <<'EOF'
#!/usr/bin/env bash
# platform/kubernetes/argocd/bootstrap/bootstrap-argocd.sh — install Argo CD and hand the cluster to GitOps.
# Usage: platform/kubernetes/argocd/bootstrap/bootstrap-argocd.sh halo
#        (deploy key expected at ~/.ssh/argocd-<env>-deploy; override with DEPLOY_KEY=...)
set -euo pipefail
ENV="${1:-halo}"
CHART_VERSION="10.11.6"                     # <- the ONE place the Argo CD chart version is pinned for bootstrap
REPO_URL="git@github.com:nikhilgs817/ai-platform-portfolio.git"
DEPLOY_KEY="${DEPLOY_KEY:-$HOME/.ssh/argocd-${ENV}-deploy}"
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

echo ">> AppProjects + root application"
kubectl apply -k "$A/projects"
kubectl apply -f "$A/bootstrap/root-${ENV}.yaml"

cat <<MSG
>> Bootstrap complete. Now:
   1) argocd login --username admin --password "\$(argocd admin initial-password -n argocd | head -1)"
   2) argocd account update-password   (use the password-manager value)
   3) kubectl -n argocd delete secret argocd-initial-admin-secret
MSG
EOF
chmod +x platform/kubernetes/argocd/bootstrap/bootstrap-argocd.sh

git add -A && git commit -m "chore(halo): rebuild scripts for clients and Argo CD bootstrap" && git push
```

### 9.2 Run the drill: full DR from the baseline WSL export

> **Before you start:** the deploy private key and the Argo CD admin password are in your password manager (Step 5). Everything else has been pushed (`git status` is clean). If either is missing, stop and fix that first.

**Start the clock** and write down the time.

🪟A: safety snapshot, then destroy and restore the baseline:
```powershell
$bk = "$env:USERPROFILE\WSL-backups"
wsl --terminate halo
wsl --export halo "$bk\halo-predrill-$(Get-Date -Format yyyyMMdd-HHmm).tar"   # safety net, keep until the drill passes
wsl --unregister halo                                                        # destroys the distro and its vhdx
$base = (Get-ChildItem "$bk\halo-baseline-*.tar" | Sort-Object Name | Select-Object -Last 1).FullName
wsl --import halo "$env:LOCALAPPDATA\wsl\halo" $base
wsl --manage halo --set-sparse true
wsl --set-default halo
Start-ScheduledTask -TaskName 'WSL-halo-keepalive'
wsl -d halo -e sh -c 'hostname; whoami; ps -p1 -o comm='                     # halo, <you>, systemd
```

🐧: identity, repo, host, cluster, clients, Argo CD:
```bash
# 1) GitHub push identity: generate a NEW key (rotation), add it on GitHub, then delete the old "halo-wsl" key there
ssh-keygen -t ed25519 -C "halo-wsl-$(date +%Y%m)" -f ~/.ssh/id_ed25519_github -N ''
printf 'Host github.com\n  HostName github.com\n  User git\n  IdentityFile ~/.ssh/id_ed25519_github\n  IdentitiesOnly yes\n' > ~/.ssh/config
chmod 600 ~/.ssh/config; cat ~/.ssh/id_ed25519_github.pub      # 🐙 add as SSH key, remove the old one
ssh -T git@github.com                                          # run AFTER adding the key on GitHub

# 2) Repo
sudo apt-get update -qq && sudo apt-get install -y -qq git curl jq unzip bash-completion
git config --global user.name "Nikhil G S"; git config --global user.email "ID+nikhilgs817@users.noreply.github.com"
git config --global core.autocrlf input; git config --global pull.rebase true
mkdir -p ~/src && cd ~/src && git clone git@github.com:nikhilgs817/ai-platform-portfolio.git && cd ai-platform-portfolio

# 3) Host config + k3s (from Git)
sudo cp platform/k3s/halo/wsl.conf /etc/wsl.conf      # already there from the baseline; keeps them identical
sudo platform/k3s/halo/install-k3s.sh

# 4) Clients + kubeconfig (also refreshes the Windows kubeconfig: the cluster CA is new)
platform/k3s/halo/install-clients.sh && source ~/.bashrc

# 5) Deploy key: paste the PRIVATE key from the password manager
install -m 600 /dev/null ~/.ssh/argocd-halo-deploy && nano ~/.ssh/argocd-halo-deploy

# 6) Argo CD bootstrap; the apps come back from Git with no further commands
platform/kubernetes/argocd/bootstrap/bootstrap-argocd.sh halo
until kubectl -n argocd get application podinfo >/dev/null 2>&1; do sleep 5; done   # child app created from Git

# 7) Credentials: log in with the generated password, set the password-manager value, delete the bootstrap secret
argocd login --username admin --password "$(argocd admin initial-password -n argocd | head -1)"
argocd account update-password
kubectl -n argocd delete secret argocd-initial-admin-secret
```

Then:

```bash
argocd app wait podinfo --sync --health --timeout 600
argocd app list
curl -s -H 'Host: podinfo.halo.localhost' http://127.0.0.1/version
```

🪟 `kubectl get nodes; curl.exe -s http://podinfo.halo.localhost/version`

**Stop the clock.** Expected: podinfo `Synced`/`Healthy` with 3 replicas and `6.17.0`, without you applying a single app manifest. Typical time: 35–60 min (most of it downloads and key handling).

**Quick variant (k3s only, ~15 min):** `sudo /usr/local/bin/k3s-uninstall.sh && sudo platform/k3s/halo/install-k3s.sh && platform/k3s/halo/install-clients.sh && platform/kubernetes/argocd/bootstrap/bootstrap-argocd.sh halo`. Do this one whenever you change k3s config.

**If it fails**
1. `wsl --import` says "distribution already exists" → the unregister didn't finish. Run `wsl -l -v`, then `wsl --unregister halo` again.
2. The bootstrap script fails at the repo Secret → the deploy key file has Windows line endings or missing header lines. Re-paste it and check that `head -1 ~/.ssh/argocd-halo-deploy` prints `-----BEGIN OPENSSH PRIVATE KEY-----`.
3. Windows kubectl shows `x509: certificate signed by unknown authority` → the Windows kubeconfig still has the old CA. Re-run `install-clients.sh`.

Once the drill passes, delete the safety `halo-predrill-*.tar` and take a **new** post-platform export (`halo-platform-YYYYMMDD.tar`), so you have two restore points.

### 9.3 Write the runbook (🐧)

```bash
mkdir -p docs/runbooks
cat > docs/runbooks/rebuild-halo.md <<'EOF'
# Runbook: rebuild cluster "halo" from Git

| | |
|---|---|
| Scope | k3s node `halo` (WSL2 distro on the MS-S1 Max) + Argo CD + all GitOps apps |
| RTO target | 60 min · **Measured: __ min (YYYY-MM-DD)** |
| RPO | Git: last push · stateful data: see "Not covered" |
| Needs | baseline WSL export · password manager entries "Argo CD admin — halo", "Argo CD deploy key — halo" · GitHub access |

## When to use
WSL distro corrupted or deleted · k3s/etcd unrecoverable · after major host changes (as a drill, monthly).

## Procedure A: full DR (WSL baseline import), ~45 min
1. Windows (admin): `wsl --terminate halo` → `wsl --export halo <bk>\halo-predrill-<ts>.tar` → `wsl --unregister halo`
2. `wsl --import halo $env:LOCALAPPDATA\wsl\halo <bk>\halo-baseline-<date>.tar` → `wsl --manage halo --set-sparse true`
   → `wsl --set-default halo` → `Start-ScheduledTask WSL-halo-keepalive`
3. WSL: new GitHub SSH key (rotate: remove the old key on GitHub) → clone repo to `~/src/ai-platform-portfolio`
4. `sudo platform/k3s/halo/install-k3s.sh`
5. `platform/k3s/halo/install-clients.sh` (also refreshes the Windows kubeconfig)
6. Restore `~/.ssh/argocd-halo-deploy` (mode 600) from the password manager
7. `platform/kubernetes/argocd/bootstrap/bootstrap-argocd.sh halo`
8. Rotate the admin password to the password-manager value; `kubectl -n argocd delete secret argocd-initial-admin-secret`

## Procedure B: k3s only, ~15 min
`sudo /usr/local/bin/k3s-uninstall.sh` → steps 4, 5, 7, 8 above.

## Procedure C: etcd point-in-time restore (cluster state only)
`sudo k3s etcd-snapshot ls` → `sudo systemctl stop k3s` →
`sudo k3s server --cluster-reset --cluster-reset-restore-path=<snapshot>` → `sudo systemctl start k3s`

## Verification
- [ ] `kubectl get nodes` → halo Ready (WSL and Windows)
- [ ] `argocd app list` → all apps Synced/Healthy
- [ ] `curl.exe http://podinfo.halo.localhost/version` → expected version
- [ ] `wsl --shutdown` + keep-alive task → recovers unattended

## Not covered (yet)
PVC data (local-path) is NOT restored by Git. Before Phoenix stores real state: Retain StorageClass,
scheduled pg_dump / Redis RDB to a backup location, and a restore test in this runbook.

## Drill log
| Date | Procedure | Duration | Issues found | Follow-up |
|---|---|---|---|---|
| YYYY-MM-DD | A | __ min | | |
EOF
git add -A && git commit -m "docs(runbook): rebuild-halo with measured drill results" && git push
```

Fill in the measured time and the issues you hit, then commit again.

- [ ] Drill completed from baseline export; podinfo returned from Git alone
- [ ] `docs/runbooks/rebuild-halo.md` committed with the real duration
- [ ] New post-platform export taken; personal GitHub SSH key rotated

### CKA corner: Step 9
- **Domain:** Cluster Architecture, Installation & Configuration (etcd backup and restore is a near-certain exam task).
- **Practise:** `sudo k3s etcd-snapshot save --name pre-change` · `sudo k3s etcd-snapshot ls` · `sudo ls -l /var/lib/rancher/k3s/server/db/snapshots/` · `sudo k3s certificate check` · `kubectl get --raw /readyz/etcd`
- **Drill (kubeadm syntax, write from memory):** `ETCDCTL_API=3 etcdctl snapshot save /tmp/etcd.db --endpoints=https://127.0.0.1:2379 --cacert=/etc/kubernetes/pki/etcd/ca.crt --cert=/etc/kubernetes/pki/etcd/server.crt --key=/etc/kubernetes/pki/etcd/server.key`, then the matching `etcdutl snapshot restore /tmp/etcd.db --data-dir /var/lib/etcd-restore` and the manifest edit that points etcd at the new data dir.

**Interview angle:** "I run timed DR drills: I destroy the node, restore a base image, and the platform plus every app comes back from Git with two secrets. I documented the RTO and the gaps, such as stateful data, in a runbook."
**Phoenix angle:** worst case for Phoenix is now "about 45 minutes to a fully deployed Command Center". The runbook's "Not covered" section is the backlog item to fix *before* Timescale holds data you care about.

---

## Step 10 (optional, B10): Argo CD manages its own Helm install

**Goal:** an `argocd` Application that renders the same chart and values from the repo, so Argo CD upgrades are just Git commits too.
**Why:** it closes the last imperative gap (`helm upgrade`), and Argo CD 3.x's annotation-based tracking avoids the old label conflict with Helm's `app.kubernetes.io/instance`. **Risks:** a bad values change can break the very controller that would fix it. Two owners (Helm CLI and Argo CD) must never both be used again. CRDs and the Redis-secret init job (a Helm hook) behave a bit differently under Argo CD. Mitigations: `prune: false`, `ServerSideApply`, test changes with `helm template` first, and keep the bootstrap script as the break-glass path.

```bash
cat > platform/kubernetes/argocd/clusters/halo/argocd.yaml <<'EOF'
# platform/kubernetes/argocd/clusters/halo/argocd.yaml — Argo CD manages its own Helm release (same chart + values as bootstrap)
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: argocd
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "-20"
  # NO finalizer: deleting this Application must never delete Argo CD itself
spec:
  project: platform
  sources:
    - repoURL: https://argoproj.github.io/argo-helm
      chart: argo-cd
      targetRevision: 10.11.6                 # bump here = Argo CD upgrade (keep bootstrap script in sync)
      helm:
        releaseName: argocd                   # MUST match the bootstrap release name
        valueFiles:
          - $values/platform/kubernetes/argocd/install/values.yaml
          - $values/platform/kubernetes/argocd/install/values-halo.yaml
    - repoURL: git@github.com:nikhilgs817/ai-platform-portfolio.git
      targetRevision: main
      ref: values
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  ignoreDifferences:
    - kind: Secret
      name: argocd-secret
      jsonPointers: [/data]                   # admin password + server key are set at runtime, not from Git
  syncPolicy:
    automated:
      prune: false                            # never auto-delete parts of the controller
      selfHeal: true
    syncOptions:
      - ServerSideApply=true                  # large CRDs
      - RespectIgnoreDifferences=true
EOF
sed -i 's|^  # - argocd.yaml .*|  - argocd.yaml|' platform/kubernetes/argocd/clusters/halo/kustomization.yaml
git add -A && git commit -m "feat(argocd): Argo CD manages its own Helm release" && git push
argocd app get root-halo --refresh >/dev/null; sleep 20
argocd app get argocd | head -20
```

**Expected:** app `argocd` `Synced`/`Healthy` with no pod restarts (the rendered manifests match what Helm installed). From now on, **never run `helm upgrade argocd` again** except to break glass.
**Break glass:** if a bad commit breaks Argo CD, run `git revert`, then `helm upgrade --install …` from Step 5.1 (the bootstrap script) to force the last good state.
- [ ] (optional) `argocd` app Synced/Healthy; ADR note added: "Argo CD is self-managed from chart 10.11.6"
