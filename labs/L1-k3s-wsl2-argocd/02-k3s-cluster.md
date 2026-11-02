# Steps 1–3: k3s, client tools, cluster verification (blocks B3–B4)

← [Step 0](01-windows-wsl.md) · Next → [Monorepo + GitOps layout](03-monorepo-gitops-layout.md)

> **Native k3s vs k3d / Rancher Desktop:** k3d runs k3s *inside Docker containers*. That's great for throwaway multi-node CI clusters, but it adds Docker as a second runtime and a second network layer, and your long-lived Phoenix workloads would then depend on both. Rancher Desktop wraps k3s in its own VM and GUI, and hides the systemd unit, config file, certs and etcd. Those are exactly what the CKA tests and what you'd run in production. **Native k3s as a systemd service is the right choice here.** Use k3d later only for disposable test clusters, such as CI eval gates.

---

## Step 1: Install k3s (single node, pinned) (B3)

### 1.1 Stable node IP: dummy interface `halo0`

**Goal:** a network interface whose IP (`10.255.255.10`) never changes, for k3s, etcd and flannel to bind to.
**Why:** in NAT mode, `eth0` gets a new 172.x address on every WSL boot. Embedded etcd records its peer URL by IP, and the API server certificate lists IPs, so a moving IP is the top cause of "my WSL cluster died after a reboot". A *dummy* interface is a virtual NIC that's always up, like a loopback adapter on a Windows server or a VMkernel port with a fixed IP. Outbound traffic still leaves through `eth0`.
**Where:** 🐧

```bash
sudo tee /etc/systemd/system/halo-node-ip.service >/dev/null <<'EOF'
# /etc/systemd/system/halo-node-ip.service
[Unit]
Description=Stable k3s node IP on dummy interface halo0 (10.255.255.10)
DefaultDependencies=no
After=systemd-modules-load.service
Before=network-pre.target k3s.service
Wants=network-pre.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'ip link show halo0 >/dev/null 2>&1 || ip link add halo0 type dummy'
ExecStart=/usr/sbin/ip addr replace 10.255.255.10/32 dev halo0
ExecStart=/usr/sbin/ip link set halo0 up
ExecStop=/usr/sbin/ip link del halo0

[Install]
WantedBy=multi-user.target
EOF

sudo mkdir -p /etc/systemd/system/k3s.service.d
sudo tee /etc/systemd/system/k3s.service.d/10-halo-node-ip.conf >/dev/null <<'EOF'
# /etc/systemd/system/k3s.service.d/10-halo-node-ip.conf — k3s must start after halo0 exists
[Unit]
Requires=halo-node-ip.service
After=halo-node-ip.service
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now halo-node-ip.service
ip -br addr show halo0
```

**Expected:** `halo0  UNKNOWN  10.255.255.10/32` (`UNKNOWN` is normal for a dummy interface).

> **Address choice:** `10.255.255.0/24` stays clear of the k3s pod CIDR (`10.42.0.0/16`), the service CIDR (`10.43.0.0/16`) and the WSL NAT range (172.16–31.x). If a VPN you use later claims `10.255.x`, change it in three files: this unit, the k3s config, and the Traefik config.

### 1.2 k3s configuration file

**Goal:** all k3s settings in one declarative file. No long command-line flags.
**Why:** `/etc/rancher/k3s/config.yaml` mirrors the `k3s server` flags one to one. It's the equivalent of a kubeadm `ClusterConfiguration`, or an Ansible vars file. Each setting below has a comment saying *why*. In Step 4 this file goes into Git (it holds no secrets).
**Where:** 🐧

```bash
sudo mkdir -p /etc/rancher/k3s
sudo tee /etc/rancher/k3s/config.yaml >/dev/null <<'EOF'
# /etc/rancher/k3s/config.yaml — k3s server config for node "halo"
# Source of truth: platform/k3s/halo/config.yaml in ai-platform-portfolio. No secrets in this file.

# --- identity & addressing -------------------------------------------------
node-name: halo
node-ip: 10.255.255.10            # dummy NIC halo0: survives WSL IP changes
advertise-address: 10.255.255.10  # IP the apiserver advertises to the cluster
flannel-iface: halo0              # pin flannel (pod network) to the stable NIC
cluster-cidr: 10.42.0.0/16        # k3s default, written down on purpose
service-cidr: 10.43.0.0/16        # k3s default, written down on purpose

# --- API server certificate SANs (what clients may call it) ----------------
tls-san:
  - halo
  - halo.localhost
  - localhost
  - 127.0.0.1                     # Windows kubeconfig uses this via localhost forwarding
  - 10.255.255.10

# --- datastore: embedded etcd (production-like; CKA snapshot practice) -----
cluster-init: true
etcd-snapshot-schedule-cron: "0 */6 * * *"   # every 6h
etcd-snapshot-retention: 12                  # keep 3 days

# --- security --------------------------------------------------------------
secrets-encryption: true          # encrypt Secret objects at rest in etcd
write-kubeconfig-mode: "0600"     # admin kubeconfig readable by root only

# --- runtime ---------------------------------------------------------------
prefer-bundled-bin: true          # use k3s's tested iptables/ipset, not the host's

# --- node labels & kubelet capacity protection -----------------------------
node-label:
  - "lab.platform/env=halo"
kubelet-arg:
  - "system-reserved=cpu=500m,memory=1Gi"      # keep room for systemd, WSL init, sshd...
  - "kube-reserved=cpu=500m,memory=1Gi"        # ...and for k3s itself
  - "eviction-hard=memory.available<500Mi,nodefs.available<10%,imagefs.available<10%"
  - "image-gc-high-threshold=80"
  - "image-gc-low-threshold=70"

# --- bundled add-ons: all KEPT (nothing under 'disable:') ------------------
# traefik       -> ingress controller (configured by traefik-config.yaml below)
# servicelb     -> LoadBalancer services via host ports (klipper-lb)
# local-storage -> local-path StorageClass for PVCs
# metrics-server, coredns
EOF
```

### 1.3 Traefik override: bind 80/443 for real (HelmChartConfig)

**Goal:** Traefik listens on real sockets on ports 80/443 so Windows `localhost` reaches it.
**Why:** by default k3s exposes Traefik through **ServiceLB**, which uses *iptables* rules to grab host ports. WSL's localhost relay only forwards ports that have a real *listening socket*, so those iptables-only ports would be invisible from Windows. Running Traefik with `hostNetwork: true` is the standard bare-metal "edge node" pattern: the ingress controller binds the node's ports directly. k3s lets you customise its bundled charts with a `HelmChartConfig` dropped into its auto-deploy folder.
**Where:** 🐧

```bash
sudo mkdir -p /var/lib/rancher/k3s/server/manifests
sudo tee /var/lib/rancher/k3s/server/manifests/traefik-config.yaml >/dev/null <<'EOF'
# /var/lib/rancher/k3s/server/manifests/traefik-config.yaml
# Source of truth: platform/k3s/halo/traefik-config.yaml
apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: traefik
  namespace: kube-system
spec:
  valuesContent: |-
    hostNetwork: true                 # real sockets on :80/:443 -> WSL localhost relay works
    service:
      type: ClusterIP                 # no ServiceLB pod fighting for the same host ports
    ports:
      web:
        port: 80
      websecure:
        port: 443
      traefik:
        port: 9000                    # internal ping/dashboard entrypoint, off :8080
      metrics:
        port: 9102                    # keep :9100 free for node-exporter later
    updateStrategy:                   # hostNetwork pods can't surge on the same ports
      type: RollingUpdate
      rollingUpdate:
        maxUnavailable: 1
        maxSurge: 0
    securityContext:                  # binding <1024 needs NET_BIND_SERVICE as root
      capabilities:
        drop: [ALL]
        add: [NET_BIND_SERVICE]
      readOnlyRootFilesystem: true
      runAsNonRoot: false
      runAsUser: 0
      runAsGroup: 0
    providers:
      kubernetesIngress:
        publishedService:
          enabled: false
    additionalArguments:
      # Write this IP into every Ingress status -> Argo CD sees Ingresses as Healthy
      - "--providers.kubernetesingress.ingressendpoint.ip=10.255.255.10"
EOF
```

### 1.4 Install k3s (pinned script + pinned version)

**Goal:** k3s v1.36.5+k3s1 running as the `k3s` systemd service.
**Why:** piping `get.k3s.io` straight into `sh` runs an unpinned script from the internet. Download the installer **from the release tag**, read it, then run it with `INSTALL_K3S_VERSION`. The installer checks the binary's SHA-256, writes `k3s.service`, and creates the `kubectl`, `crictl` and `ctr` symlinks plus `k3s-uninstall.sh`. In production this would be an Ansible role or a golden image.
**Where:** 🐧

```bash
K3S_VERSION='v1.36.5+k3s1'
curl -fsSL -o /tmp/k3s-install.sh "https://raw.githubusercontent.com/k3s-io/k3s/${K3S_VERSION/+/%2B}/install.sh"
head -5 /tmp/k3s-install.sh            # skim it; it's a long but readable shell script
sudo env INSTALL_K3S_VERSION="$K3S_VERSION" sh /tmp/k3s-install.sh
```

**Expected (last lines):**
```
[INFO]  Using v1.36.5+k3s1 as release
[INFO]  Downloading hash https://github.com/k3s-io/k3s/releases/download/v1.36.5+k3s1/sha256sum-amd64.txt
[INFO]  Verifying binary download
[INFO]  Creating /usr/local/bin/kubectl symlink to k3s
[INFO]  Creating /usr/local/bin/crictl symlink to k3s
[INFO]  systemd: Enabling k3s unit
[INFO]  systemd: Starting k3s
```

Set up your own kubeconfig. The context, cluster and user are all named `halo`:

```bash
mkdir -p ~/.kube
sudo cat /etc/rancher/k3s/k3s.yaml | sed -e 's/: default$/: halo/' > ~/.kube/config
chmod 600 ~/.kube/config
kubectl config get-contexts
kubectl get nodes -o wide
```

**Expected:**
```
CURRENT   NAME   CLUSTER   AUTHINFO   NAMESPACE
*         halo   halo      halo
NAME   STATUS   ROLES                AGE   VERSION        INTERNAL-IP     ...  CONTAINER-RUNTIME
halo   Ready    control-plane,etcd   60s   v1.36.5+k3s1   10.255.255.10   ...  containerd://2.x
```

**Verify:**
```bash
systemctl is-active k3s halo-node-ip                 # active, active
sudo k3s check-config | tail -5                      # STATUS: pass
sudo k3s secrets-encrypt status | head -3            # Encryption Status: Enabled
kubectl -n kube-system get helmchart,pods            # helm-install-traefik* Completed, traefik Running
kubectl -n kube-system get pods -l app.kubernetes.io/name=traefik -o wide   # IP = 10.255.255.10 (hostNetwork)
sudo ss -ltnp | grep -E ':(80|443|6443)\s'          # traefik on :80/:443, k3s on :6443
```

- [ ] `halo` Ready with INTERNAL-IP 10.255.255.10
- [ ] Traefik listening on :80 and :443; secrets encryption enabled

**If it fails**
1. k3s keeps restarting → `sudo journalctl -u k3s -e --no-pager | tail -50`. Look for `iptables` (→ appendix **T3**), `cgroup` (→ **T2**), or `failed to find interface halo0` (→ check that `halo-node-ip.service` is active).
2. Traefik pod `Pending`/`CrashLoopBackOff` → `kubectl -n kube-system logs job/helm-install-traefik` shows chart value errors. `bind: permission denied` means the securityContext block wasn't applied. Edit the file, and k3s re-applies it within seconds.
3. Something on Windows already holds port 80, so the relay can't forward → appendix **T7**.

### What the bundled add-ons do (kept on purpose)

| Add-on | What it is | Why keep it | Later |
|---|---|---|---|
| **Traefik** | Ingress controller: routes `Host:` / path rules to Services | Lets every app get a name like `x.halo.localhost` | Gateway API routes, TLS with cert-manager |
| **ServiceLB** (klipper-lb) | Implements `type: LoadBalancer` by grabbing host ports with iptables | Ready for TCP services (for example Postgres for a desktop client) without MetalLB | Not used by Traefik here (hostNetwork); still available |
| **local-path** | Dynamic PV provisioner: each PVC becomes a folder on the node | Zero-setup storage for Timescale/Redis | Phoenix needs a **Retain** StorageClass + backups (see Phoenix angle) |
| **metrics-server** | Resource metrics API | `kubectl top`, HPA | Prometheus later |
| **CoreDNS** | Cluster DNS | Service discovery | — |

> ### 📦 k3s vs kubeadm: what k3s hides that the CKA expects you to know
> | Topic | k3s (halo) | kubeadm (CKA exam) |
> |---|---|---|
> | Control plane | **One process** `k3s server` runs apiserver, scheduler, controller-manager, kubelet, kube-proxy and containerd. `kubectl -n kube-system get pods` shows **no** apiserver pods | Static pods in `/etc/kubernetes/manifests/` (`kube-apiserver.yaml`, `etcd.yaml`, …), run by the kubelet |
> | Datastore | SQLite by default (via *kine*); here **embedded etcd** in the k3s process, data in `/var/lib/rancher/k3s/server/db/etcd` | etcd static pod, data in `/var/lib/etcd`; backup with `etcdctl snapshot save` |
> | Certificates | `/var/lib/rancher/k3s/server/tls/` | `/etc/kubernetes/pki/` (`kubeadm certs check-expiration`) |
> | Admin kubeconfig | `/etc/rancher/k3s/k3s.yaml` | `/etc/kubernetes/admin.conf` |
> | Kubelet config | flags from `config.yaml` (`kubelet-arg`) | `/var/lib/kubelet/config.yaml` + `kubelet.service` drop-in |
> | Container runtime | bundled containerd, socket `/run/k3s/containerd/containerd.sock`; `sudo k3s crictl ps` | system containerd, `/run/containerd/containerd.sock`; `crictl ps` |
> | CNI | flannel (VXLAN) built in; config under `/var/lib/rancher/k3s/agent/etc/cni/net.d` | you install one (Calico/Flannel/Cilium); `/etc/cni/net.d` |
> | Auto-applied manifests | `/var/lib/rancher/k3s/server/manifests/` (k3s applies them like a mini-GitOps) | none (static pods are a different mechanism) |
> | Static pods | `/var/lib/rancher/k3s/agent/pod-manifests/` | `/etc/kubernetes/manifests/` |
> | Upgrades | swap the binary (`INSTALL_K3S_VERSION=…`) or the system-upgrade-controller | `kubeadm upgrade plan/apply`, drain, upgrade kubelet per node |
>
> **Exam trap:** on a kubeadm cluster, a broken control plane is fixed by editing the static pod YAML. On k3s there's no YAML, only `config.yaml` plus `systemctl restart k3s`. Practise both.

### CKA corner: Step 1
- **Domain:** Cluster Architecture, Installation & Configuration (25%).
- **Practise:** `kubectl get nodes -o wide` · `kubectl describe node halo | grep -A6 Allocatable` · `kubectl get --raw='/readyz?verbose'` · `sudo k3s crictl ps` · `sudo k3s etcd-snapshot save --name manual-1 && sudo k3s etcd-snapshot ls`
- **Drill:** `kubectl label node halo disk=ssd` → `kubectl get nodes -L disk` → `kubectl label node halo disk-` (labels and selectors come up a lot).

**Interview angle:** "I pinned the node identity to a stable interface so etcd and certificates survive network changes, ran embedded etcd with scheduled snapshots, encrypted Secrets at rest, and reserved kubelet capacity: the same hardening I'd ask for on a production node pool."
**Phoenix angle:** etcd snapshots every 6 h plus `secrets-encryption` mean Phoenix's cluster state is recoverable and its future Secrets aren't stored in plain text.

---

## Step 2: Client tools in WSL and on Windows (B4)

**Goal:** pinned `kubectl`, `helm` and `argocd` (plus optional `k9s`) in both shells. Windows uses the `halo` context.
**Why:** WSL is where you'll *operate* the platform (scripts, Git). Windows is where your browser, VS Code and habits live. Same versions on both sides means no "works in one shell" surprises. Every download is checksum-verified, as you'd do in a Jenkins agent image.

### 2.1 In WSL (🐧)

```bash
KV=v1.36.6; HV=v4.3.1; AV=v3.5.6; K9V=v0.51.0
T=$(mktemp -d); cd "$T"

# kubectl (replace k3s's symlink with the pinned standalone binary)
curl -fsSLO "https://dl.k8s.io/release/${KV}/bin/linux/amd64/kubectl"
curl -fsSLO "https://dl.k8s.io/release/${KV}/bin/linux/amd64/kubectl.sha256"
echo "$(cat kubectl.sha256)  kubectl" | sha256sum --check
sudo rm -f /usr/local/bin/kubectl            # removes the SYMLINK only; /usr/local/bin/k3s stays
sudo install -m 0755 kubectl /usr/local/bin/kubectl

# helm
curl -fsSLO "https://get.helm.sh/helm-${HV}-linux-amd64.tar.gz"
curl -fsSLO "https://get.helm.sh/helm-${HV}-linux-amd64.tar.gz.sha256sum"
sha256sum --check "helm-${HV}-linux-amd64.tar.gz.sha256sum"
tar xzf "helm-${HV}-linux-amd64.tar.gz" && sudo install -m 0755 linux-amd64/helm /usr/local/bin/helm

# argocd CLI
curl -fsSLO "https://github.com/argoproj/argo-cd/releases/download/${AV}/argocd-linux-amd64"
curl -fsSLO "https://github.com/argoproj/argo-cd/releases/download/${AV}/cli_checksums.txt"
grep ' argocd-linux-amd64$' cli_checksums.txt | sha256sum --check
sudo install -m 0755 argocd-linux-amd64 /usr/local/bin/argocd

# k9s (optional)
curl -fsSLO "https://github.com/derailed/k9s/releases/download/${K9V}/k9s_Linux_amd64.tar.gz"
curl -fsSLO "https://github.com/derailed/k9s/releases/download/${K9V}/checksums.sha256"
grep ' k9s_Linux_amd64.tar.gz$' checksums.sha256 | sha256sum --check
tar xzf k9s_Linux_amd64.tar.gz k9s && sudo install -m 0755 k9s /usr/local/bin/k9s
cd ~ && rm -rf "$T"

cat >> ~/.bashrc <<'EOF'
# --- k8s tooling (CKA habits) ---
source <(kubectl completion bash)
source <(helm completion bash)
source <(argocd completion bash)
alias k=kubectl
complete -o default -F __start_kubectl k
export do="--dry-run=client -o yaml"      # k create deploy x --image=y $do > x.yaml
export now="--force --grace-period 0"     # k delete pod x $now
# argocd CLI reaches the API through a kubectl port-forward (no DNS/TLS needed)
export ARGOCD_OPTS="--port-forward --port-forward-namespace argocd --plaintext"
EOF
source ~/.bashrc
kubectl version; helm version --short; argocd version --client --short
```

**Expected:** `Client Version: v1.36.6` · `Server Version: v1.36.5+k3s1` · `v4.3.1+g…` · `argocd: v3.5.6+…`

Copy the kubeconfig to Windows and lock down its permissions:

```bash
WINHOME=$(wslpath "$(/mnt/c/Windows/System32/cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')")
mkdir -p "$WINHOME/.kube"
[ -f "$WINHOME/.kube/config" ] && cp "$WINHOME/.kube/config" "$WINHOME/.kube/config.bak-$(date +%s)"
cp ~/.kube/config "$WINHOME/.kube/config"
```

### 2.2 On Windows (🪟)

```powershell
$bin = "$env:USERPROFILE\tools\bin"; New-Item -ItemType Directory -Force $bin | Out-Null
$KV='v1.36.6'; $HV='v4.3.1'; $AV='v3.5.6'; $K9V='v0.51.0'
$ProgressPreference = 'SilentlyContinue'; $tmp = New-Item -ItemType Directory -Force "$env:TEMP\halo-tools"
function Assert-Hash($file, $expected) { if ((Get-FileHash $file -Algorithm SHA256).Hash -ine $expected.Trim()) { throw "Checksum mismatch: $file" } else { "OK  $file" } }

# kubectl
Invoke-WebRequest "https://dl.k8s.io/release/$KV/bin/windows/amd64/kubectl.exe" -OutFile "$bin\kubectl.exe"
Invoke-WebRequest "https://dl.k8s.io/release/$KV/bin/windows/amd64/kubectl.exe.sha256" -OutFile "$tmp\kubectl.sha256"
Assert-Hash "$bin\kubectl.exe" (Get-Content "$tmp\kubectl.sha256" -Raw)

# helm
Invoke-WebRequest "https://get.helm.sh/helm-$HV-windows-amd64.zip" -OutFile "$tmp\helm.zip"
Invoke-WebRequest "https://get.helm.sh/helm-$HV-windows-amd64.zip.sha256sum" -OutFile "$tmp\helm.sha256sum"
Assert-Hash "$tmp\helm.zip" ((Get-Content "$tmp\helm.sha256sum" -Raw).Split(' ')[0])
Expand-Archive "$tmp\helm.zip" -DestinationPath $tmp -Force; Copy-Item "$tmp\windows-amd64\helm.exe" $bin -Force

# argocd
Invoke-WebRequest "https://github.com/argoproj/argo-cd/releases/download/$AV/argocd-windows-amd64.exe" -OutFile "$bin\argocd.exe"
Invoke-WebRequest "https://github.com/argoproj/argo-cd/releases/download/$AV/cli_checksums.txt" -OutFile "$tmp\argocd.sums"
Assert-Hash "$bin\argocd.exe" ((Select-String -Path "$tmp\argocd.sums" -Pattern 'argocd-windows-amd64.exe$').Line.Split(' ')[0])

# k9s (optional)
Invoke-WebRequest "https://github.com/derailed/k9s/releases/download/$K9V/k9s_Windows_amd64.zip" -OutFile "$tmp\k9s.zip"
Invoke-WebRequest "https://github.com/derailed/k9s/releases/download/$K9V/checksums.sha256" -OutFile "$tmp\k9s.sums"
Assert-Hash "$tmp\k9s.zip" ((Select-String -Path "$tmp\k9s.sums" -Pattern 'k9s_Windows_amd64.zip$').Line.Split(' ')[0])
Expand-Archive "$tmp\k9s.zip" -DestinationPath "$tmp\k9s" -Force; Copy-Item "$tmp\k9s\k9s.exe" $bin -Force

# PATH + argocd options (user scope), then lock down the kubeconfig (cluster-admin credentials!)
$userPath = [Environment]::GetEnvironmentVariable('Path','User')
if ($userPath -notlike "*$bin*") { [Environment]::SetEnvironmentVariable('Path', "$bin;$userPath", 'User') }
[Environment]::SetEnvironmentVariable('ARGOCD_OPTS','--port-forward --port-forward-namespace argocd --plaintext','User')
icacls "$env:USERPROFILE\.kube\config" /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
```

Open a **new** PowerShell window (so the PATH change applies), then:

```powershell
kubectl config get-contexts
kubectl --context halo get nodes
helm version --short; argocd version --client --short
```

**Expected:** context `halo` marked current; `halo   Ready   control-plane,etcd   …   v1.36.5+k3s1`.

- [ ] WSL: kubectl/helm/argocd at pinned versions, `k` alias works
- [ ] Windows: same versions; `kubectl get nodes` works through `https://127.0.0.1:6443`

**If it fails**
1. Windows `Unable to connect … 127.0.0.1:6443` → the distro isn't running (`wsl -l -v`), or `localhostForwarding` is off. Run `Test-NetConnection 127.0.0.1 -Port 6443`.
2. `x509: certificate is valid for …, not …` → the server URL in the Windows kubeconfig isn't `https://127.0.0.1:6443`. Copy it again from WSL.
3. An old `kubectl.exe` still runs → `Get-Command kubectl -All`. Remove the other path entry (Docker Desktop, Chocolatey or winget shims).

### CKA corner: Step 2
- **Domain:** Cluster Architecture (kubeconfig, contexts, RBAC basics).
- **Practise:** `kubectl config view --minify` · `kubectl config use-context halo` · `kubectl config set-context --current --namespace=kube-system` · `kubectl auth can-i '*' '*' --all-namespaces` · `kubectl api-resources --namespaced=false`
- **Drill:** `kubectl config set-context halo-dev --cluster=halo --user=halo --namespace=dev` → use it → delete it with `kubectl config delete-context halo-dev`.

**Interview angle:** "Same pinned, checksum-verified toolchain on every workstation and runner, one named context per cluster, cluster-admin kubeconfigs ACL'd, and the GitOps CLI going through the API server instead of a public endpoint."
**Phoenix angle:** you can run `kubectl`/`k9s` against Phoenix from Windows during market hours without opening a WSL shell.

---

## Step 3: Verify the cluster end to end (B4)

**Goal:** prove scheduling, Services, DNS, storage and ingress from a Windows browser, then prove it all survives `wsl --shutdown`.
**Why:** smoke-test every layer the later labs depend on *before* adding GitOps, so any later failure is about Argo CD and not the platform. These objects are throwaway, so imperative commands are fine. From Step 5 on, Argo CD is the only thing that applies app manifests.
**Where:** 🐧 unless marked

```bash
# 1) control plane + system pods
kubectl get nodes
kubectl get pods -A -o wide
kubectl top node                                   # metrics-server works (may need ~60s after boot)

# 2) a throwaway deployment + service + ingress (imperative on purpose — CKA style)
kubectl create namespace smoke
kubectl -n smoke create deployment hello --image=ghcr.io/stefanprodan/podinfo:6.17.0 --replicas=2 --port=9898
kubectl -n smoke expose deployment hello --port=80 --target-port=9898
kubectl -n smoke create ingress hello --class=traefik --rule="hello.halo.localhost/*=hello:80"
kubectl -n smoke rollout status deploy/hello
kubectl -n smoke get deploy,svc,ingress,endpointslices

# 3) DNS from inside a pod
kubectl -n smoke run dnscheck --image=busybox:1.37.0 --rm -it --restart=Never -- nslookup hello.smoke.svc.cluster.local

# 4) a PVC on local-path, written by a pod
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: data, namespace: smoke }
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: local-path
  resources: { requests: { storage: 1Gi } }
---
apiVersion: v1
kind: Pod
metadata: { name: writer, namespace: smoke }
spec:
  containers:
    - name: w
      image: busybox:1.37.0
      command: ["sh","-c","date > /data/hello.txt && sleep 3600"]
      volumeMounts: [{ name: d, mountPath: /data }]
  volumes: [{ name: d, persistentVolumeClaim: { claimName: data } }]
EOF
kubectl -n smoke wait --for=condition=Ready pod/writer --timeout=120s
kubectl -n smoke get pvc,pv
sudo ls /var/lib/rancher/k3s/storage/ && sudo cat /var/lib/rancher/k3s/storage/*_smoke_data/hello.txt
curl -s -H 'Host: hello.halo.localhost' http://127.0.0.1/version
```

**Expected:** the ingress `ADDRESS` is `10.255.255.10`; the PVC is `Bound` (it was `Pending` until the pod started, because local-path uses `WaitForFirstConsumer`); the host folder holds `hello.txt`; curl returns JSON with `"version": "6.17.0"`.

From 🪟 and 🌐:

```powershell
curl.exe -s http://hello.halo.localhost/version
```
Open **http://hello.halo.localhost** in Edge or Chrome and you should see the podinfo UI. Browsers send `*.localhost` to 127.0.0.1 themselves, so there's no hosts file and no DNS.

Clean up:
```bash
kubectl delete namespace smoke
```

### 3.1 Restart test (🪟)

```powershell
wsl --shutdown
Start-Sleep 10
Start-ScheduledTask -TaskName 'WSL-halo-keepalive'     # same thing that happens at logon
Start-Sleep 60
kubectl get nodes; kubectl get pods -A | Select-String -NotMatch 'Running|Completed'
```

**Expected:** `halo Ready`. Only the header line appears in the second output (every pod is Running or Completed). The first boot after a shutdown takes about 30–90 s.

- [ ] Browser shows podinfo at `hello.halo.localhost`
- [ ] PVC bound and the file is visible under `/var/lib/rancher/k3s/storage`
- [ ] Cluster back by itself after `wsl --shutdown` + keep-alive task

**If it fails**
1. Browser 404 → Traefik is up but no rule matched. Check `kubectl get ingress -A` for the host spelling and `ingressClassName: traefik`. Appendix **T7**.
2. Browser "connection refused" → nothing reachable on Windows :80. In WSL run `sudo ss -ltnp | grep ':80 '`; from Windows run `Test-NetConnection 127.0.0.1 -Port 80`. Appendix **T7**.
3. PVC stays `Pending` → there's no pod using it yet (expected), or `kubectl -n kube-system logs deploy/local-path-provisioner` shows an error.

### CKA corner: Step 3
- **Domain:** Services & Networking (20%), Storage (10%), Workloads (15%).
- **Practise:** `k get endpointslices -n smoke` · `k describe ingress hello -n smoke` · `k get sc local-path -o yaml | grep -E 'provisioner|volumeBindingMode|reclaimPolicy'` · `k run tmp --image=busybox:1.37.0 --rm -it --restart=Never -- wget -qO- hello.smoke` · `k get events -n smoke --sort-by=.lastTimestamp`
- **Drill:** generate (don't apply) a Deployment + Service + Ingress YAML trio with `$do` in under 3 minutes:
  `k create deploy web --image=nginx:1.29 --replicas=3 $do > web.yaml; k expose -f web.yaml --port=80 $do >> web.yaml` (add `---` between documents), then `k create ingress web --rule="web.halo.localhost/*=web:80" $do`.

**Interview angle:** "Before layering GitOps I smoke-test every primitive (scheduling, DNS, storage binding, ingress) and the restart path, so platform faults and delivery faults never get confused."
**Phoenix angle:** you've just seen exactly where a Phoenix PVC lives on disk and that it survives a restart. **Call-out:** the `local-path` StorageClass uses `reclaimPolicy: Delete`, so deleting a PVC deletes the data. Before Timescale moves in, add a `local-path-retain` StorageClass (Retain) and scheduled `pg_dump` backups.

**Block B4 done when:** - [ ] both shells talk to `halo` · - [ ] the browser reaches an ingress · - [ ] restart verified.
