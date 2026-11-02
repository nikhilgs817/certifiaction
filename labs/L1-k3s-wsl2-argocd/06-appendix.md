# Appendix: troubleshooting, glossary, final checklist, what's next

← [Steps 8–10](05-prove-rebuild.md) · [Overview](README.md)

---

## Troubleshooting

Start with the same triage every time (🐧):
```bash
systemctl is-active halo-node-ip k3s; kubectl get nodes; kubectl get pods -A | grep -vE 'Running|Completed'; argocd app list
```

### T1: WSL won't start, or systemd is off
| Symptom | Likely cause | Fix |
|---|---|---|
| `wsl -d halo` errors `0x80370102` / `HCS_E_HYPERV_NOT_INSTALLED` | Virtual Machine Platform off, or SVM off in BIOS | `dism /online /enable-feature /featurename:VirtualMachinePlatform /all`, reboot; check SVM in BIOS |
| `ps -p1 -o comm=` prints `init` | `wsl.conf` `[boot] systemd=true` missing or typo, or no full restart | fix `/etc/wsl.conf`, then `wsl --shutdown` (closing the window isn't enough) |
| Hangs on start after a `.wslconfig` edit | Bad value (for example `memory=48G B`) | rename `.wslconfig`, run `wsl --shutdown`, start, fix the value |
| Distro gone from `wsl -l` | unregistered or profile reset | restore: `wsl --import halo <dir> <export.tar>` (runbook) |

### T2: k3s fails on cgroups
`journalctl -u k3s` shows `failed to find memory cgroup (v2)` or `cpuset` missing.
1. `stat -fc %T /sys/fs/cgroup` must be `cgroup2fs`. If it's `tmpfs` (hybrid), add under `[wsl2]` in `.wslconfig`:
   `kernelCommandLine = cgroup_no_v1=all systemd.unified_cgroup_hierarchy=1`, then `wsl --shutdown`.
2. `cat /sys/fs/cgroup/cgroup.controllers` must list `cpuset cpu io memory pids`. If not, run `wsl --update` (old kernel).
3. `sudo k3s check-config` lists the failing items.

### T3: k3s fails on iptables / nftables
`journalctl -u k3s` shows `iptables: … Could not fetch rule set generation id` or flannel `failed to set up masquerade`.
1. Make sure `prefer-bundled-bin: true` is in `/etc/rancher/k3s/config.yaml`, then `sudo systemctl restart k3s`.
2. Host tools mixing legacy and nft: `sudo update-alternatives --set iptables /usr/sbin/iptables-nft && sudo update-alternatives --set ip6tables /usr/sbin/ip6tables-nft`.
3. `lsmod | grep br_netfilter` is empty → `sudo modprobe br_netfilter`, and check `/etc/modules-load.d/k3s.conf`.

### T4: ImagePullBackOff
`kubectl -n <ns> describe pod <pod>` → read the last *Events*:
| Message | Cause | Fix |
|---|---|---|
| `manifest unknown` / `not found` | tag typo (Step 8d on purpose) | fix the tag in the overlay → push (or `git revert`) |
| `toomanyrequests` | Docker Hub anonymous rate limit | prefer ghcr.io/quay.io images now; Harbor proxy-cache later |
| `dial tcp: lookup … no such host` | node DNS broken (VPN, DNS tunneling) | in WSL: `resolvectl`/`cat /etc/resolv.conf`, `curl -I https://ghcr.io`; try `dnsTunneling=false`; `wsl --shutdown` |
| `x509: certificate signed by unknown authority` | TLS-intercepting proxy/AV | add the proxy CA under `/usr/local/share/ca-certificates/`, `update-ca-certificates`, restart k3s |

### T5: App stuck OutOfSync
1. `argocd app diff <app>` shows exactly which field differs.
2. A controller or webhook mutates a field (for example an HPA on `replicas`, or defaulted fields) → add `ignoreDifferences` for that path in the Application, in Git.
3. Someone keeps changing it by hand → selfHeal will revert it. Find out who with `kubectl get events` and the audit trail.
4. Kustomize build error → `argocd app get <app>` shows `ComparisonError`. Reproduce it with `kubectl kustomize <path>` locally.
5. Hard refresh: `argocd app get <app> --hard-refresh` (clears the repo-server cache).

### T6: Repo fails to connect
`argocd repo list` STATUS `Failed`:
1. `ssh: handshake failed: ssh: unable to authenticate` → the deploy key is on another repo, or the *public* key was put in the Secret. Check with `kubectl -n argocd get secret repo-… -o jsonpath='{.data.sshPrivateKey}' | base64 -d | head -1`, which should print `-----BEGIN OPENSSH PRIVATE KEY-----`.
2. `knownhosts: key is unknown` → `argocd cert list --cert-type ssh | grep github`. Add the key with `ssh-keyscan github.com | argocd cert add-ssh --batch` (and confirm the fingerprint against GitHub's published one).
3. URL mismatch: Applications must use the identical URL (`git@github.com:nikhilgs817/ai-platform-portfolio.git`), not `https://` or `ssh://` variants.

### T7: Ingress returns 404 (or refuses connection) from Windows
| Test | Meaning |
|---|---|
| 🐧 `curl -sI -H 'Host: podinfo.halo.localhost' http://127.0.0.1/` → 200 | cluster side is fine; problem is Windows ↔ WSL |
| 🐧 → **404** | Traefik reached, no matching rule: check `kubectl get ingress -A` (host, `ingressClassName: traefik`, Service name/port) |
| 🐧 → connection refused | Traefik not on :80: `sudo ss -ltnp \| grep ':80 '`, `kubectl -n kube-system get pods -l app.kubernetes.io/name=traefik`, `kubectl -n kube-system logs job/helm-install-traefik` |
| 🪟 `Test-NetConnection 127.0.0.1 -Port 80` False | port not relayed: Windows already uses :80 (`Get-NetTCPConnection -LocalPort 80 -State Listen`), `localhostForwarding=false`, or relay stale → `wsl --shutdown` and start again |
| 🪟 works in curl.exe, not in browser | browser proxy/VPN extension, or browser tried `::1` first and gave up: try `http://127.0.0.1` with a Host-header extension, or disable the proxy for `*.localhost` |

**If port 80 on Windows can't be freed:** move Traefik to 8080/8443 in `platform/k3s/halo/traefik-config.yaml` (`ports.web.port: 8080`, `ports.websecure.port: 8443`; you can then drop the root/NET_BIND_SERVICE override), re-run `install-k3s.sh`, and browse to `http://podinfo.halo.localhost:8080`.

### T8: Cluster gone after a Windows reboot
1. `wsl -l -v` → `halo Stopped` → the keep-alive task didn't fire. Check *Task Scheduler → WSL-halo-keepalive → History / Last Run Result*, then `Start-ScheduledTask WSL-halo-keepalive`.
2. Running but `kubectl` times out → k3s still starting (30–90 s), or failed: `wsl -d halo -e sudo journalctl -u k3s -b --no-pager | tail -40`.
3. `halo0` missing → `systemctl status halo-node-ip`. The `dummy` module must load (`/etc/modules-load.d/k3s.conf`).
4. Stops again after about 1 min with no terminal → `.wslconfig` idle settings (`vmIdleTimeout=-1`, `instanceIdleTimeout=-1`) not applied: `wsl --version` (update), `wsl --shutdown`.
5. Reboot happened while logged out → *AtLogOn* didn't trigger. See the note in Step 0.6 about adding an *AtStartup* trigger.

### T9: "The WSL IP changed"
With this design that's **expected and harmless**: `eth0` changes, the node stays on `10.255.255.10`, and Windows uses `127.0.0.1`. If something does break:
1. `kubectl get node halo -o wide` INTERNAL-IP isn't `10.255.255.10` → `node-ip` / `flannel-iface` missing from `config.yaml`, or k3s started before `halo0` existed (check the drop-in `10-halo-node-ip.conf`).
2. Windows kubeconfig points at a `172.x` address → copy it again (`install-clients.sh`). It must be `https://127.0.0.1:6443`.
3. Something on Windows needs the WSL IP (rare) → `wsl -d halo hostname -I`. Never hard-code it.

### T10: Clock skew after sleep (`x509: certificate has expired or is not yet valid`)
`timedatectl` in WSL shows a wrong time → `sudo hwclock -s` or `sudo systemctl restart systemd-timesyncd`. Avoid sleep (Step 0.6).

---

## Glossary

| Term | Plain words (and the comparison you already know) |
|---|---|
| **WSL2** | A lightweight Hyper-V VM that runs real Linux kernels for "distros" (like a single-purpose ESXi VM managed by Windows) |
| **Distro** | One Linux root filesystem inside WSL (`halo`); export/import ≈ VM template |
| **.wslconfig / wsl.conf** | VM-level settings (vCPU/RAM/NIC) / per-distro settings (≈ cloud-init) |
| **k3s** | CNCF-certified Kubernetes in one binary; the same API as kubeadm clusters |
| **etcd** | The cluster's database: every object you `kubectl apply` lives here |
| **containerd** | The container runtime the kubelet asks to run containers |
| **flannel** | The pod network (VXLAN overlay) that gives every pod an IP |
| **Traefik / Ingress** | HTTP router: picks a Service by hostname/path (≈ IHS/F5 virtual host rules in front of WebSphere) |
| **ServiceLB** | k3s's simple `LoadBalancer` implementation using host ports |
| **local-path** | Storage provisioner: each PVC is a folder on the node's disk |
| **PSA** (Pod Security Admission) | Namespace label that rejects unsafe pods (`restricted` = non-root, no privilege escalation, …) |
| **ResourceQuota / LimitRange** | Namespace budget / default per-container sizes |
| **PDB** | "Keep at least N pods" during voluntary disruptions such as drains |
| **Helm** | Package manager: chart + values → manifests (≈ a parameterised Ansible role) |
| **Kustomize** | Patch-based overlays on plain YAML (base + env differences), built into kubectl |
| **GitOps** | Git holds desired state; an in-cluster agent pulls and reconciles continuously (pull, not Jenkins-push) |
| **Argo CD Application** | "Sync this Git path to this cluster/namespace", a continuously running deploy pipeline |
| **AppProject** | Guardrails for a group of Applications: allowed repos, namespaces, resource kinds (≈ Jenkins folder + credentials scope) |
| **App of apps** | A root Application whose manifests are other Applications |
| **Sync / Prune / Self-heal** | Apply Git → delete what Git removed → undo manual drift |
| **Sync wave** | Ordering hint (lower first), for example projects before apps |
| **Health: Progressing / Healthy / Degraded** | Argo CD's view of whether resources actually work, not just whether they were applied |
| **Deploy key** | SSH key scoped to one GitHub repo, read-only if write is unticked |
| **RTO / RPO** | How long a restore takes / how much data you may lose |

---

## ✅ Final checklist: "Argo CD syncing a sample app from Git"

**Foundation**
- [ ] WSL 3.0.x, distro `halo` (Ubuntu 24.04.5), systemd, hostname `halo`, 48 GB / 16 vCPU
- [ ] `.wslconfig` NAT + localhost forwarding + idle timeouts −1; keep-alive task; no sleep on AC
- [ ] Kernel prerequisites persistent (modules-load.d, sysctl.d); all preflight checks OK
- [ ] Baseline export taken (and a post-platform export after Step 9)

**Cluster**
- [ ] k3s v1.36.5+k3s1, node `halo` Ready on 10.255.255.10, embedded etcd, secrets encryption on, snapshots scheduled
- [ ] Traefik on :80/:443 (hostNetwork); ServiceLB and local-path available
- [ ] kubectl/helm/argocd pinned in WSL **and** Windows; Windows context `halo` → `https://127.0.0.1:6443`
- [ ] Smoke tests passed (deployment, DNS, PVC, ingress from Windows browser); survives `wsl --shutdown`

**GitOps**
- [ ] `ai-platform-portfolio` (private) with skeleton, `.gitignore`, `.gitattributes`, ADR-0001, `platform/k3s/halo/`
- [ ] Argo CD chart 10.11.6 / v3.5.6 installed from committed values; UI at `http://argocd.halo.localhost`
- [ ] Admin password rotated and in password manager; `argocd-initial-admin-secret` deleted
- [ ] Repo connected with **read-only** deploy key; private key not in Git
- [ ] AppProjects `platform` + `lab`; `root-halo` → `argocd-projects` + `podinfo`, all Synced/Healthy
- [ ] **podinfo deployed only via `git push`, reachable at `http://podinfo.halo.localhost`**

**Proofs**
- [ ] 8a replicas via Git · 8b delete healed · 8c scale reverted · 8d Degraded → `git revert` · 8e history in UI + CLI · 8f recovers after `wsl --shutdown`
- [ ] Rebuild drill done; `docs/runbooks/rebuild-halo.md` with measured RTO
- [ ] (optional) Argo CD self-managed

**Hygiene**
- [ ] `git log -p | grep -E 'PRIVATE KEY|password'` finds nothing sensitive
- [ ] Export tarballs stored off-Git, treated as secrets

---

## What's next (out of scope this week)

**L1, the rest of the paved road (weeks 2–4)**
- **Service template + CI (Week 2):** FastAPI + Dockerfile + Helm chart in `platform/helm-charts/`. CI is **GitHub Actions** on GitHub-hosted runners: a reusable workflow in `.github/workflows/` called per service, composite actions in `.github/actions/`, and images pushed to **GHCR** (private, until Harbor in Week 4). The new image tag is promoted through Git into `overlays/halo`.
- **Supply chain:** Harbor (registry + proxy cache), Trivy (scan), Syft (SBOM), cosign (sign), **Kyverno** policy that blocks unsigned images in tenant namespaces.
- **Progressive delivery:** Argo Rollouts canary for the template service.
- **Platform services:** Sealed Secrets or External Secrets, cert-manager + TLS (then turn off `server.insecure`), the observability stack (Prometheus, Loki, Tempo, OTel, Grafana), OpenCost.
- **Terraform** for AWS GPU node groups, plus the `aws` overlay and `root-aws`.
- **Phoenix Command Center moves in:** `apps/command-center` with Timescale + Redis on a **Retain** StorageClass, backups, and the restore test added to the runbook.

**Toward the end goal: self-hosted models instead of paying per token**
1. **L2:** llama.cpp natively on Windows (Vulkan/HIP on the Radeon 8060S) as an external backend in k3s → **LiteLLM** in front (routing, per-tenant budgets, fallbacks, usage logs) → Phoenix agents (Morning Brief 08:55, Explain-This-Grade, EOD Journal 16:20) with read-only MCP tools.
2. **Several models side by side:** size by GPU memory (model weights + KV cache × concurrent requests). Keep small and fast models always loaded, load large ones on demand, and route by task in LiteLLM.
3. **Measure the savings:** Langfuse and OpenCost give cost per request and per tenant. Compare that with the equivalent API price per million tokens. That comparison is your interview story.
4. **AWS:** vLLM, plus Triton or NIM on GPU nodes with the NVIDIA device plugin, batching and VRAM sizing, all synced by the same Argo CD layout through the `aws` overlay.
