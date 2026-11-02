# Steps 5–7: Argo CD, app of apps, podinfo (blocks B6–B7)

← [Step 4](03-monorepo-gitops-layout.md) · Next → [Prove GitOps + rebuild](05-prove-rebuild.md)

---

## Step 5: Install Argo CD with Helm (B6)

### 5.1 Helm install from the committed values

**Goal:** Argo CD v3.5.6 (chart 10.11.6) in namespace `argocd`, configured only by the values files in Git.
**Why:** Argo CD can't install itself on an empty cluster (chicken and egg), so the very first install is a Helm release, exactly as in production bootstraps. Using the values files from the repo means the same command reproduces the same Argo CD on any cluster. In Jenkins terms, this installs the controller from a JCasC file.
**Where:** 🐧 (repo root)

```bash
cd ~/src/ai-platform-portfolio
kubectl config current-context            # must print: halo
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update argo
helm search repo argo/argo-cd --version 10.11.6     # CHART VERSION 10.11.6, APP VERSION v3.5.6

helm upgrade --install argocd argo/argo-cd \
  --version 10.11.6 \
  --namespace argocd --create-namespace \
  -f platform/kubernetes/argocd/install/values.yaml \
  -f platform/kubernetes/argocd/install/values-halo.yaml \
  --wait --timeout 10m
```

**Expected:** `Release "argocd" does not exist. Installing it now.` … `STATUS: deployed` … `REVISION: 1`, followed by chart notes.

**Verify:**
```bash
kubectl -n argocd get pods
kubectl -n argocd get ingress
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: argocd.halo.localhost' http://127.0.0.1/
helm -n argocd list
```
**Expected:** pods `argocd-application-controller-0`, `-applicationset-controller-…`, `-redis-…`, `-repo-server-…`, `-server-…` all `Running`; ingress `argocd-server` with host `argocd.halo.localhost` and address `10.255.255.10`; HTTP `200`.

🌐 Open **http://argocd.halo.localhost**. The Argo CD login page should appear. If it doesn't, the fallback is a port-forward: `kubectl -n argocd port-forward svc/argocd-server 8080:80`, then open http://localhost:8080.

### 5.2 Log in, rotate the admin password, delete the bootstrap secret

**Why:** the chart generates a random first password and stores it in `argocd-initial-admin-secret`. Production practice is to rotate it straight away, keep the real one only in a password manager, and delete the bootstrap secret so it can't leak through a `kubectl get secret`. The CLI goes through a port-forward (`ARGOCD_OPTS`, set in Step 2), so there's no DNS or TLS dependency.
**Where:** 🐧

```bash
echo "$ARGOCD_OPTS"                                   # --port-forward --port-forward-namespace argocd --plaintext
INITIAL=$(argocd admin initial-password -n argocd | head -1)
argocd login --username admin --password "$INITIAL"
# 1) Generate a strong password IN YOUR PASSWORD MANAGER (entry: "Argo CD admin — halo"), then:
argocd account update-password --current-password "$INITIAL"     # prompts for the new password twice
unset INITIAL
argocd login --username admin                         # prompts; use the new password
kubectl -n argocd delete secret argocd-initial-admin-secret
argocd account get-user-info
```

**Expected:** `'admin:login' logged in successfully` … `Password updated` … `secret "argocd-initial-admin-secret" deleted` … `Logged In: true, Username: admin`.

🌐 Log in to the UI with `admin` and the new password. On Windows (🪟) the CLI works the same way: `argocd login --username admin`.

### 5.3 Connect the private repo with a read-only deploy key

**Why:** a *deploy key* is an SSH key that grants access to **one repo**, and with "Allow write access" unticked it's read-only. If Argo CD is ever compromised, the attacker can read one repo and can't push. The private key goes into the cluster as a Secret (encrypted at rest, thanks to `secrets-encryption`) and into your password manager, and never into Git. `argocd repo add` simply creates a labelled Secret in `argocd`. Step 9 creates that same Secret with `kubectl`.
**Where:** 🐧 then 🐙 then 🐧

```bash
ssh-keygen -t ed25519 -C "argocd-halo-readonly" -f ~/.ssh/argocd-halo-deploy -N ''
cat ~/.ssh/argocd-halo-deploy.pub
# Also store the PRIVATE key (~/.ssh/argocd-halo-deploy) in the password manager entry "Argo CD deploy key — halo"
```

🐙 repo → **Settings → Deploy keys → Add deploy key**. Title `argocd-halo (read-only)`, paste the `.pub` line, **leave "Allow write access" unticked**, then **Add key**.

```bash
argocd repo add git@github.com:nikhilgs817/ai-platform-portfolio.git \
  --name ai-platform-portfolio \
  --ssh-private-key-path ~/.ssh/argocd-halo-deploy
argocd repo list
kubectl -n argocd get secrets -l argocd.argoproj.io/secret-type=repository
```

**Expected:** `Repository 'git@github.com:nikhilgs817/ai-platform-portfolio.git' added`. `argocd repo list` shows `TYPE git … STATUS Successful`. One repository Secret exists. In the UI, *Settings → Repositories* shows a green *Successful*.

> GitHub's SSH host keys come preloaded in `argocd-ssh-known-hosts-cm`, so you don't need `--insecure-ignore-host-key`. Never use that flag.

- [ ] UI reachable at `argocd.halo.localhost`
- [ ] Admin password rotated and in the password manager; initial secret deleted
- [ ] Repo connected (Successful) with a read-only deploy key; private key only in ~/.ssh and the password manager

**If it fails**
1. `helm … context deadline exceeded` → `kubectl -n argocd get pods` and describe the pending pod. Usually images are still pulling on a slow link. Re-run the same `helm upgrade --install` command (it's idempotent).
2. `argocd login` hangs → the port-forward needs a Running `argocd-server` pod and a working kubeconfig. Run `kubectl -n argocd get pods`, then `argocd login --username admin --port-forward --port-forward-namespace argocd --plaintext` explicitly.
3. Repo status `Failed … ssh: handshake failed` → the deploy key isn't on *this* repo, or you pasted the private key in GitHub. Appendix **T6**.

### CKA corner: Step 5
- **Domain:** Cluster Architecture (Helm and Kustomize are in the 2025+ curriculum; CRDs and operators).
- **Practise:** `helm -n argocd list` · `helm -n argocd get values argocd` · `helm template argocd argo/argo-cd --version 10.11.6 -f platform/kubernetes/argocd/install/values.yaml | grep -c '^kind:'` · `kubectl get crd | grep argoproj` · `kubectl -n argocd get secret -l argocd.argoproj.io/secret-type=repository -o yaml | head -20`
- **Drill:** `kubectl create secret generic demo --from-literal=user=lab $do` → decode one value with `kubectl get secret demo -o jsonpath='{.data.user}' | base64 -d`, and explain why base64 isn't encryption (that's what `secrets-encryption` is for).

**Interview angle:** "Argo CD itself is installed from version-pinned, Git-tracked Helm values. Bootstrap credentials are rotated and destroyed on day 0, and Git access is a single-repo, read-only key that never touches the repo."
**Phoenix angle:** Phoenix deploys need nothing on the box except Argo CD's read-only key. The trading code never gets cluster credentials.

---

## Step 6: AppProjects + the root Application (app of apps) (B7)

**Goal:** apply the two AppProjects and `root-halo` once. After that, Argo CD manages everything else, including the projects themselves.
**Why:** an **AppProject** is a guardrail: which repos, which namespaces and which kinds of resources a group of apps may touch. Think of it as the Jenkins folder-level permissions plus allowed credentials. `lab` is least privilege (named namespaces only, no cluster objects except Namespace). `platform` is broad, for platform components. The **root Application** points at `clusters/halo`, a folder that contains only *other Application manifests*. One root, many children: "app of apps". `automated` + `prune` + `selfHeal` means Git is enforced, not just suggested.
**Where:** 🐧

```bash
cd ~/src/ai-platform-portfolio
kubectl apply -k platform/kubernetes/argocd/projects          # the two AppProjects (adopted by Argo CD next)
kubectl apply -f platform/kubernetes/argocd/bootstrap/root-halo.yaml
```

**Expected:**
```
appproject.argoproj.io/lab created
appproject.argoproj.io/platform created
application.argoproj.io/root-halo created
```

**Verify** (give it about 30 s):
```bash
argocd proj list
argocd app list
argocd app get root-halo
```
**Expected:** projects `default`, `lab`, `platform`. Apps `root-halo` and `argocd-projects` both `Synced` / `Healthy`. In the UI, `root-halo` shows a tree with one child Application, `argocd-projects`, which owns the two AppProjects.

**What the sync options mean**

| Setting | Effect | Production note |
|---|---|---|
| `automated` | Applies every new commit on `main` without a click | Keep for apps; some orgs use manual sync for prod with automated PR promotion |
| `prune: true` | Deletes live objects that were removed from Git | Protected here: AppProjects have `Prune=false` |
| `selfHeal: true` | Reverts manual `kubectl` changes within seconds | Makes Git the only change path; break-glass = disable selfHeal in Git |
| `CreateNamespace=true` | Argo CD creates the destination namespace | Labels set via `managedNamespaceMetadata` (Step 7) |
| no finalizer on root | Deleting `root-halo` leaves children running | Children *do* have the finalizer, so removing one from Git cleans up its resources |

- [ ] `root-halo` and `argocd-projects` Synced/Healthy
- [ ] `lab` project restricts destinations to `podinfo`

**If it fails**
1. `root-halo` shows `ComparisonError … repository not accessible` → the repo URL in `root-halo.yaml` must match `argocd repo list` **exactly** (`git@github.com:…`). Appendix **T6**.
2. `application destination … is not permitted in project` → the destination namespace isn't in the AppProject. Fix it in Git (`projects/*.yaml`), then push.
3. Stuck `OutOfSync` → appendix **T5** (`argocd app diff root-halo`).

---

## Step 7: Sample app podinfo: base + halo overlay, deployed only through Git (B7)

**Goal:** podinfo at **http://podinfo.halo.localhost**, deployed only by a Git push.
**Why podinfo:** it's built for exactly this. It has `/healthz` and `/readyz` probes, a UI that shows **version and hostname** (you can *see* replicas and rollouts), Prometheus metrics, and it runs non-root with a read-only filesystem, so it passes the **restricted** Pod Security level that production namespaces should enforce. It also gives you a believable stand-in for a FastAPI service before the Phoenix template exists.
**Where:** 🐧

### 7.1 Base (`apps/podinfo/base/`)

```bash
B=platform/kubernetes/apps/podinfo/base; mkdir -p "$B"

cat > $B/deployment.yaml <<'EOF'
# platform/kubernetes/apps/podinfo/base/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: podinfo
spec:
  replicas: 1
  revisionHistoryLimit: 5
  progressDeadlineSeconds: 120          # a bad rollout turns Degraded after 2 min, not 10
  strategy:
    type: RollingUpdate
    rollingUpdate: { maxUnavailable: 0, maxSurge: 1 }   # old pods keep serving if the new ones fail
  selector:
    matchLabels:
      app.kubernetes.io/name: podinfo
  template:
    metadata:
      labels:
        app.kubernetes.io/name: podinfo
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "9797"
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile: { type: RuntimeDefault }
      containers:
        - name: podinfo
          image: ghcr.io/stefanprodan/podinfo:6.17.0
          imagePullPolicy: IfNotPresent
          command:
            - ./podinfo
            - --port=9898
            - --port-metrics=9797
            - --level=info
            - --data-path=/data
          ports:
            - { name: http, containerPort: 9898, protocol: TCP }
            - { name: http-metrics, containerPort: 9797, protocol: TCP }
          readinessProbe:
            httpGet: { path: /readyz, port: http }
            initialDelaySeconds: 2
            periodSeconds: 5
          livenessProbe:
            httpGet: { path: /healthz, port: http }
            initialDelaySeconds: 5
            periodSeconds: 10
          resources:
            requests: { cpu: 25m, memory: 32Mi }
            limits:   { memory: 128Mi }         # no CPU limit: avoid throttling; requests drive scheduling
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: { drop: [ALL] }
          volumeMounts:
            - { name: data, mountPath: /data }
      volumes:
        - name: data
          emptyDir: { sizeLimit: 64Mi }
EOF

cat > $B/service.yaml <<'EOF'
# platform/kubernetes/apps/podinfo/base/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: podinfo
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: podinfo
  ports:
    - { name: http, port: 80, targetPort: http, protocol: TCP }
EOF

cat > $B/ingress.yaml <<'EOF'
# platform/kubernetes/apps/podinfo/base/ingress.yaml — host is set per environment in the overlay
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: podinfo
spec:
  ingressClassName: traefik
  rules:
    - host: podinfo.example.invalid
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: podinfo
                port: { name: http }
EOF

cat > $B/pdb.yaml <<'EOF'
# platform/kubernetes/apps/podinfo/base/pdb.yaml — keeps 1 pod during voluntary disruptions (kubectl drain)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: podinfo
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: podinfo
EOF

cat > $B/limitrange.yaml <<'EOF'
# platform/kubernetes/apps/podinfo/base/limitrange.yaml — defaults for any container that forgets resources
apiVersion: v1
kind: LimitRange
metadata:
  name: defaults
spec:
  limits:
    - type: Container
      defaultRequest: { cpu: 50m, memory: 64Mi }
      default:        { memory: 256Mi }
      max:            { memory: 1Gi }
EOF

cat > $B/kustomization.yaml <<'EOF'
# platform/kubernetes/apps/podinfo/base/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
labels:
  - pairs:
      app.kubernetes.io/part-of: lab-samples
      app.kubernetes.io/managed-by: argocd
    includeSelectors: false              # never change selectors (immutable on Deployments)
resources:
  - deployment.yaml
  - service.yaml
  - ingress.yaml
  - pdb.yaml
  - limitrange.yaml
EOF
```

### 7.2 Overlay `halo` (and the `aws` placeholder)

```bash
O=platform/kubernetes/apps/podinfo/overlays; mkdir -p $O/halo $O/aws

cat > $O/halo/kustomization.yaml <<'EOF'
# platform/kubernetes/apps/podinfo/overlays/halo/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: podinfo
resources:
  - ../../base
  - resourcequota.yaml
labels:
  - pairs:
      lab.platform/env: halo
    includeSelectors: false
images:
  - name: ghcr.io/stefanprodan/podinfo
    newTag: "6.17.0"                     # Step 8d breaks this on purpose
patches:
  - path: patch-deployment.yaml
  - target: { kind: Ingress, name: podinfo }
    patch: |-
      - op: replace
        path: /spec/rules/0/host
        value: podinfo.halo.localhost
EOF

cat > $O/halo/patch-deployment.yaml <<'EOF'
# platform/kubernetes/apps/podinfo/overlays/halo/patch-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: podinfo
spec:
  replicas: 2                            # Step 8a changes this to 3
  template:
    spec:
      containers:
        - name: podinfo
          env:
            - name: PODINFO_UI_MESSAGE
              value: "halo - deployed by Argo CD from Git"
            - name: PODINFO_UI_COLOR
              value: "#2d6a4f"
EOF

cat > $O/halo/resourcequota.yaml <<'EOF'
# platform/kubernetes/apps/podinfo/overlays/halo/resourcequota.yaml — tenant budget on halo
apiVersion: v1
kind: ResourceQuota
metadata:
  name: tenant-budget
spec:
  hard:
    requests.cpu: "1"
    requests.memory: 1Gi
    limits.memory: 2Gi
    pods: "10"
    persistentvolumeclaims: "2"
    services.loadbalancers: "0"          # tenants use the shared ingress, not host ports
EOF

cat > $O/aws/README.md <<'EOF'
# overlays/aws — placeholder (AWS GPU labs). Intentionally no kustomization.yaml yet.
EOF

kubectl kustomize $O/halo | grep -E '^kind:|image:|host:|replicas:|namespace:' | sort | uniq -c
```

**Expected render check:** kinds `Deployment, Service, Ingress, PodDisruptionBudget, LimitRange, ResourceQuota`; `image: ghcr.io/stefanprodan/podinfo:6.17.0`; `host: podinfo.halo.localhost`; `replicas: 2`; `namespace: podinfo`.

### 7.3 The child Application, then deploy by pushing

```bash
cat > platform/kubernetes/argocd/clusters/halo/podinfo.yaml <<'EOF'
# platform/kubernetes/argocd/clusters/halo/podinfo.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: podinfo
  namespace: argocd
  labels:
    lab.platform/env: halo
    lab.platform/tenant: podinfo
  annotations:
    argocd.argoproj.io/sync-wave: "10"
  finalizers:
    - resources-finalizer.argocd.argoproj.io   # removing this app from Git also removes its resources
spec:
  project: lab
  source:
    repoURL: git@github.com:nikhilgs817/ai-platform-portfolio.git
    targetRevision: main
    path: platform/kubernetes/apps/podinfo/overlays/halo
  destination:
    server: https://kubernetes.default.svc
    namespace: podinfo
  revisionHistoryLimit: 10
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - PruneLast=true
    managedNamespaceMetadata:
      labels:
        pod-security.kubernetes.io/enforce: restricted
        pod-security.kubernetes.io/enforce-version: latest
        pod-security.kubernetes.io/warn: restricted
        lab.platform/tenant: podinfo
        lab.platform/env: halo
    retry:
      limit: 5
      backoff: { duration: 10s, factor: 2, maxDuration: 3m }
EOF

sed -i 's|^  # - podinfo.yaml .*|  - podinfo.yaml|' platform/kubernetes/argocd/clusters/halo/kustomization.yaml
cat platform/kubernetes/argocd/clusters/halo/kustomization.yaml

git add -A
git commit -m "feat(podinfo): base + halo overlay, child Application in lab project"
git push
argocd app get root-halo --refresh >/dev/null      # don't wait for the 3-min poll
until argocd app get podinfo >/dev/null 2>&1; do sleep 5; done   # child app appears within ~10 s
argocd app wait podinfo --sync --health --timeout 300
```

**Expected:** `podinfo` appears under `root-halo` and ends `Synced` / `Healthy`.

**Verify:**
```bash
argocd app get podinfo
kubectl get ns podinfo --show-labels                     # PSA restricted + tenant labels
kubectl -n podinfo get deploy,rs,pods,svc,ingress,pdb,quota,limitrange
kubectl -n podinfo describe quota tenant-budget | tail -8
curl -s -H 'Host: podinfo.halo.localhost' http://127.0.0.1/version
```
🪟 `curl.exe -s http://podinfo.halo.localhost/version` → `{"commit":"…","version":"6.17.0"}`
🌐 **http://podinfo.halo.localhost**: green page with "halo - deployed by Argo CD from Git". Refresh a few times and the hostname switches between the 2 pods.

- [ ] podinfo Synced/Healthy, created **only** by `git push`
- [ ] Namespace enforces PSA `restricted`; quota and LimitRange present
- [ ] UI reachable from the Windows browser

**🎯 Checkpoint reached: Argo CD is syncing a sample app from Git.**

**If it fails**
1. Pods rejected with `violates PodSecurity "restricted:latest"` → a securityContext field is missing. The event tells you which one. Fix it in `base/deployment.yaml` and push.
2. `ImagePullBackOff` → appendix **T4** (tag typo, rate limit, DNS from the node).
3. Ingress 404 in the browser but `curl -H Host:` works in WSL → host spelling (`podinfo.halo.localhost`), or the browser is using a proxy. Appendix **T7**.

### CKA corner: Steps 6–7
- **Domain:** Workloads & Scheduling (15%): Deployments, rollouts, probes, resource requests, quotas, PDBs. Also Services & Networking (Ingress).
- **Practise:** `k -n podinfo rollout history deploy/podinfo` · `k -n podinfo get pods -o custom-columns=NAME:.metadata.name,IMAGE:.spec.containers[0].image,NODE:.spec.nodeName` · `k -n podinfo describe quota` · `k auth can-i create deployments -n podinfo --as=system:serviceaccount:podinfo:default` · `k get ns podinfo -o jsonpath='{.metadata.labels}'`
- **Drill:** in a scratch namespace, `k create quota q --hard=pods=2,requests.cpu=500m -n scratch`, then `k create deploy x --image=nginx:1.29 --replicas=3 -n scratch` and find why only 2 pods exist (`k describe rs -n scratch`). Delete the namespace afterwards.

**Interview angle:** "Tenants get a namespace with restricted Pod Security, a quota and default limits, all declared next to the app and created by Argo CD under a least-privilege AppProject. Onboarding a team is one PR."
**Phoenix angle:** Phoenix Command Center follows this exact template: restricted PSA, probes for "survives any pod kill", quota so a runaway backtest can't starve the live service, and a PDB for safe node maintenance.
