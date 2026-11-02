# Step 0: Windows + WSL2 foundation (blocks B1–B2)

← [Overview](README.md) · Next → [k3s cluster](02-k3s-cluster.md)

**Outcome of this step:** an Ubuntu 24.04 distro named `halo` with systemd, sized for the lab, that stays running after you close the terminal. The kernel prerequisites are verified, and a clean baseline snapshot is saved to disk.

---

## 0.1 Windows and BIOS checklist (B1)

**Goal:** confirm the machine can run WSL2 and has no conflicting tools.
**Why:** WSL2 is a small Hyper-V VM, so hardware virtualization (AMD SVM) has to be on. Docker Desktop and older tools often put their own `kubectl.exe` on PATH, and later you'd be talking to the wrong cluster without noticing. Think of this as the VMware host-readiness check before installing ESXi.
**Where:** 🪟A

```powershell
# Windows version (any 23H2 / 24H2 / 25H2 build is fine)
[System.Environment]::OSVersion.Version; (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').DisplayVersion

# Virtualization: "A hypervisor has been detected" or "Virtualization Enabled In Firmware: Yes"
systeminfo | Select-String -Pattern 'Hyper-V|hypervisor'

# RAM Windows can actually see (Strix Halo hands part of the 128 GB to the GPU)
"{0:N1} GB visible to Windows" -f ((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB)

# Conflicts: other kubectl/helm on PATH, Docker Desktop distros, ports 80/443/6443 in use
Get-Command kubectl,helm,argocd -All -ErrorAction SilentlyContinue | Select-Object Source
wsl -l -v 2>$null
Get-NetTCPConnection -State Listen -LocalPort 80,443,6443 -ErrorAction SilentlyContinue |
  Select-Object LocalPort, OwningProcess, @{n='Process'; e={(Get-Process -Id $_.OwningProcess).ProcessName}}
```

**Expected:** a version like `10.0.26100` with DisplayVersion `24H2` (or newer); hypervisor detected or virtualization enabled; about 96–124 GB visible; no `kubectl` found; nothing listening on 80/443/6443.

- [ ] Virtualization is on. If not: reboot into BIOS (MS-S1 Max: **Del** at boot) → *Advanced → CPU Configuration → SVM Mode = Enabled*. Leave *IOMMU* on Auto. Save, then reboot.
- [ ] No stray `kubectl.exe`. If Docker Desktop is installed: *Settings → Kubernetes → off*, and remove `C:\Program Files\Docker\Docker\resources\bin` from PATH, or uninstall Docker Desktop. Docker Desktop's `docker-desktop` distro can stay.
- [ ] Ports 80/443/6443 are free on Windows. If `System` (PID 4) holds port 80, that's http.sys (IIS, or a service such as "World Wide Web Publishing"). Stop or disable it, or later change the Traefik ports (appendix T7).
- [ ] Wrote down the **visible RAM** number. You need it in 0.3.

**If it fails**
1. `systeminfo` says virtualization is disabled → turn on SVM in the BIOS (above).
2. Corporate-style device policy blocks WSL → this is your personal PC; check *Settings → Privacy & security → For developers* and make sure no MDM profile is applied.

---

## 0.2 Install / update WSL and Ubuntu 24.04 (B1)

**Goal:** WSL 3.0.x installed, and Ubuntu 24.04 registered as a distro named **halo**.
**Why:** WSL now ships through the Microsoft Store, not as a Windows feature, so `wsl --update` is how you patch it, and the Linux kernel comes with it. `wsl --install --no-distribution` turns on the one Windows feature it needs (*Virtual Machine Platform*). The *Windows Subsystem for Linux* optional feature is only needed for WSL1. Naming the distro `halo` (with `--name`) means every command and backup refers to the cluster by name.
**Where:** 🪟A

```powershell
wsl --install --no-distribution     # enables Virtual Machine Platform + installs WSL
# >>> If it asks for a reboot, reboot now and reopen PowerShell as Administrator <<<
wsl --update
wsl --version                       # expect: WSL version: 3.0.5 (or newer), Kernel version: 6.18.x
wsl --set-default-version 2
wsl --list --online | Select-String 24.04   # expect: Ubuntu-24.04   Ubuntu 24.04 LTS
```

Write `.wslconfig` (0.3) **before** installing the distro. `sparseVhd` only applies to disks created after it is set.

Then install. Use the default location, or add `--location D:\WSL\halo` for a second drive:

```powershell
wsl --install Ubuntu-24.04 --name halo
# First launch asks for a UNIX username + password. Use a short lowercase name; this password is your sudo password.
```

Expected output ends with: `Installing: Ubuntu 24.04 LTS … The operation completed successfully.` After you set a password you get a shell prompt like `nikhil@<random-hostname>:~$`. Type `exit`.

```powershell
wsl --set-default halo
wsl -l -v      # expect:  * halo   Stopped/Running   2
```

**Verify:** `wsl -l -v` shows `halo` with VERSION `2` and an asterisk (default).

**If it fails**
1. `0x80370102` / "Please enable the Virtual Machine Platform" → SVM is off in the BIOS, or the feature isn't on yet: `dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart`, then reboot.
2. `--name` / `--location` "unknown option" → WSL is too old. Run `wsl --update` again, or install the latest `.msixbundle` from the WSL releases page.
3. The download stalls → `wsl --install Ubuntu-24.04 --name halo --web-download`.

---

## 0.3 `.wslconfig`: size, networking, keep-alive (B1)

**Goal:** give the WSL VM fixed limits that leave Windows comfortable, pick the network mode, and turn off the idle shutdown.
**Why:** `.wslconfig` configures the *VM* (all distros), like the VM settings in vSphere: vCPU, RAM, swap, NIC type. Without limits, WSL can take up to half your RAM and holds on to the file cache. Strix Halo memory is *unified*: whatever the BIOS / AMD *Variable Graphics Memory* (VGM) gives the GPU disappears from Windows. Because your end goal is several local models, the GPU share will likely grow, so size WSL from what Windows *sees*, not from 128 GB.

**Sizing rule:** `WSL memory ≈ min(48 GB, visible RAM − GPU-heavy Windows work − 24 GB)`

| VGM (GPU share) | Visible to Windows | Recommended WSL `memory` | Notes |
|---|---|---|---|
| ≤ 16 GB | ~112 GB+ | **48GB** | Default for week 1 |
| 32 GB | ~96 GB | **48GB** | Good balance |
| 64 GB | ~64 GB | **32GB** | GPU models on Windows side, platform in WSL |
| 96 GB | ~32 GB | 16GB (tight) | Only if all models run on the GPU; drop the observability stack |

**Headroom budget (why 48 GB):** k3s + etcd ~1.5 GB · Argo CD ~1 GB · Traefik 0.1 GB · Phoenix (Timescale 4 + Redis 1 + services 2) ~7 GB · observability (Prometheus/Loki/Tempo/Grafana) ~6–8 GB · Harbor ~4 GB · MLflow/Prefect/Feast ~4 GB · LiteLLM + Langfuse ~6 GB → **≈ 31–33 GB**, leaving about 15 GB for builds, spikes and a small CPU model. Large models live in GPU memory on the Windows side (see 0.10).

**Where:** 🪟. Create or replace `C:\Users\<you>\.wslconfig`:

```powershell
@'
# C:\Users\<you>\.wslconfig — WSL2 VM settings for the "halo" lab (applies to ALL distros)
[wsl2]
memory=48GB                 # see sizing table; leaves >=48 GB for Windows + GPU
processors=16               # of 32 logical CPUs (Ryzen AI Max+ 395 = 16C/32T)
swap=16GB                   # protects against OOM-kills during image builds
networkingMode=nat          # recommended: single eth0, k3s node IP pinned to a dummy NIC
localhostForwarding=true    # Windows 127.0.0.1:<port> -> listening sockets in WSL (6443, 80, 443)
dnsTunneling=true           # DNS via Windows host; survives VPN/Wi-Fi changes
firewall=true               # Hyper-V firewall rules apply to the VM
vmIdleTimeout=-1            # never shut the VM down when idle (-1 = only on wsl --shutdown)
guiApplications=false       # no WSLg compositor: saves ~0.5 GB, not needed for a server

[experimental]
autoMemoryReclaim=gradual   # slowly hands unused page cache back to Windows
sparseVhd=true              # new ext4.vhdx files are sparse (shrink when you delete data)

[general]
instanceIdleTimeout=-1      # never stop the distro when no terminal is open (newer WSL; ignored if unknown)
'@ | Set-Content -Encoding ascii "$env:USERPROFILE\.wslconfig"
Get-Content "$env:USERPROFILE\.wslconfig"
```

> Changes take effect after `wsl --shutdown`. The **WSL Settings** app (Start → "WSL Settings") edits this same file, so use it if you want to look at the options in a GUI.

**NAT vs mirrored: the short version**

| | NAT (**recommended**) | Mirrored |
|---|---|---|
| Linux interfaces | one `eth0`, 172.x, new IP each boot | copies of every Windows adapter (Wi-Fi, LAN, VPN) |
| Windows → cluster | `localhost` relay of *listening sockets* | shared stack, `localhost` both ways |
| LAN devices → cluster | needs `netsh portproxy` | works directly |
| What breaks with k3s | Only iptables-only ports (ServiceLB/hostPort) aren't relayed → solved by Traefik hostNetwork | k3s auto-picks the active Windows adapter → node IP changes when you switch networks or a VPN connects; IPv6 `::1` surprises; Windows apps can steal ports |

**Verify** (after 0.4, once the distro is restarted): 🐧 `free -g` shows total ≈ 47 and `nproc` shows `16`.

**If it fails**
1. Settings ignored → the file has a `.txt` extension or the wrong encoding. Check with `Get-Item $env:USERPROFILE\.wslconfig`, then run `wsl --shutdown`.
2. `wsl` prints "Unknown key 'x'" → harmless for `[general]` / `[experimental]` keys on older builds. Update WSL.

---

## 0.4 `/etc/wsl.conf`: systemd, hostname, PATH hygiene (B1)

**Goal:** turn on systemd, set the hostname to `halo`, and keep Windows binaries off the Linux PATH.
**Why:** `wsl.conf` configures *one distro*, roughly what cloud-init does for a VM. k3s installs as a systemd service, so systemd must be PID 1. `appendWindowsPath=false` stops `kubectl.exe` and `helm.exe` from Windows ever running inside Linux by accident. That's a classic "why is it talking to the wrong cluster" bug.
**Where:** 🐧 (`wsl -d halo`)

```bash
sudo tee /etc/wsl.conf >/dev/null <<'EOF'
# /etc/wsl.conf — per-distro settings for "halo"
[boot]
systemd=true                 # k3s runs as a systemd unit

[network]
hostname=halo                # node name, kube context and overlay all match
generateHosts=true
generateResolvConf=true      # with dnsTunneling=true, DNS goes via Windows

[interop]
enabled=true                 # can still call /mnt/c/Windows/System32/*.exe explicitly
appendWindowsPath=false      # keep kubectl.exe/helm.exe off the Linux PATH

[automount]
enabled=true
options="metadata,umask=22,fmask=11"

[user]
default=REPLACE_ME
EOF
sudo sed -i "s/REPLACE_ME/$USER/" /etc/wsl.conf
cat /etc/wsl.conf
```

Restart the distro from 🪟:

```powershell
wsl --shutdown
wsl -d halo
```

Back in 🐧:

```bash
hostname                      # halo
ps -p 1 -o comm=              # systemd
systemctl is-system-running   # running   (or "degraded" — see If it fails)
free -g | head -2; nproc      # ~47 total, 16
```

Basic packages, plus a `code` shortcut, since Windows' PATH isn't appended anymore:

```bash
sudo apt-get update && sudo apt-get -y full-upgrade
sudo apt-get install -y curl git jq unzip bash-completion ca-certificates iptables conntrack
WINUSER=$(/mnt/c/Windows/System32/cmd.exe /c 'echo %USERNAME%' 2>/dev/null | tr -d '\r')
cat >> ~/.bashrc <<EOF

# --- halo lab ---
alias code='"/mnt/c/Users/${WINUSER}/AppData/Local/Programs/Microsoft VS Code/bin/code"'
alias explorer='/mnt/c/Windows/explorer.exe'
EOF
source ~/.bashrc
```

- [ ] `hostname` = halo, PID 1 = systemd, `nproc` = 16

**If it fails**
1. `systemctl is-system-running` → `degraded`: list failures with `systemctl --failed`. On WSL, `systemd-remount-fs` or `multipathd` failures are common and harmless. Mask them with `sudo systemctl mask multipathd.service multipathd.socket` if they show up.
2. Hostname is still random → the `[network]` section has a typo, or you didn't run `wsl --shutdown` (closing the window isn't enough).
3. The `code` alias fails → VS Code was installed system-wide. Use `"/mnt/c/Program Files/Microsoft VS Code/bin/code"`.

---

## 0.5 Kernel and networking prerequisites for k3s (B2)

**Goal:** prove the WSL kernel has everything k3s and flannel need, and make the settings persistent.
**Why:** Kubernetes networking is netfilter rules plus a bridge plus an overlay. `br_netfilter` lets iptables see bridged pod traffic, `overlay` is containerd's image filesystem, cgroup v2 is how the kubelet enforces CPU and memory limits, and shared mount propagation lets volumes mount into pods. The WSL 6.18 kernel has all of these, but some are **modules** (`=m`) that need loading at boot. In Ansible terms, this is your `prereqs` role.
**Where:** 🐧

Make it persistent first:

```bash
sudo tee /etc/modules-load.d/k3s.conf >/dev/null <<'EOF'
# /etc/modules-load.d/k3s.conf — loaded at every boot by systemd-modules-load
br_netfilter
overlay
dummy
EOF

sudo tee /etc/sysctl.d/90-k3s.conf >/dev/null <<'EOF'
# /etc/sysctl.d/90-k3s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
# Argo CD, Prometheus, Loki and friends watch many files; WSL defaults (128) are too low
fs.inotify.max_user_instances       = 8192
fs.inotify.max_user_watches         = 524288
vm.max_map_count                    = 262144
EOF

sudo systemctl restart systemd-modules-load
sudo sysctl --system >/dev/null
```

Then run the checks. Each line prints `OK`, or `FIX` plus what to look at:

```bash
chk(){ if eval "$2" >/dev/null 2>&1; then echo "OK   $1"; else echo "FIX  $1  -> $3"; fi; }
chk "systemd is PID 1"            '[ "$(ps -p1 -o comm=)" = systemd ]'                        "wsl.conf [boot] systemd=true + wsl --shutdown"
chk "cgroup v2 unified"           '[ "$(stat -fc %T /sys/fs/cgroup)" = cgroup2fs ]'            "appendix T2 (kernelCommandLine)"
chk "cgroup controllers"          '( for c in memory cpuset pids; do grep -qw $c /sys/fs/cgroup/cgroup.controllers || exit 1; done )' "wsl --update"
chk "kernel modules available"    '[ -d /lib/modules/$(uname -r) ]'                             "wsl --update (modules ship with WSL)"
chk "br_netfilter loaded"         'lsmod | grep -qw br_netfilter'                               "sudo modprobe br_netfilter"
chk "overlayfs"                   'grep -qw overlay /proc/filesystems'                          "sudo modprobe overlay"
chk "dummy NIC module"            'sudo modprobe dummy'                                         "wsl --update"
chk "bridge-nf-call-iptables=1"   '[ "$(sysctl -n net.bridge.bridge-nf-call-iptables)" = 1 ]'  "sudo sysctl --system"
chk "ip_forward=1"                '[ "$(sysctl -n net.ipv4.ip_forward)" = 1 ]'                  "sudo sysctl --system"
chk "iptables works (nf_tables)"  'sudo iptables -t nat -L -n'                                  "sudo update-alternatives --set iptables /usr/sbin/iptables-nft"
chk "root mount is shared"        'findmnt -no PROPAGATION / | grep -q shared'                  "sudo mount --make-rshared /  (systemd normally does this)"
chk "/dev/kmsg exists"            '[ -e /dev/kmsg ]'                                            "systemd off? see T1"
chk "clock in sync"               'timedatectl show -p NTPSynchronized --value | grep -q yes || true' "sudo hwclock -s"
iptables --version
```

**Expected:** every line starts with `OK`, and `iptables v1.8.10 (nf_tables)`.

**iptables vs nftables, in plain words:** Ubuntu 24.04's `iptables` command is a front end that writes **nftables** rules (`iptables-nft`). kube-proxy and flannel still speak iptables. Problems only start if two different iptables front ends write to the same kernel. In Step 1, k3s runs with `prefer-bundled-bin: true` so it uses its own tested iptables binaries every time.

- [ ] All checks `OK`

**If it fails**
1. `kernel modules available` = FIX → WSL is old or the modules VHD didn't mount. Run `wsl --update`, then `wsl --shutdown`.
2. `cgroup v2 unified` = FIX → appendix **T2** (add `kernelCommandLine = cgroup_no_v1=all systemd.unified_cgroup_hierarchy=1` under `[wsl2]`).
3. `iptables works` fails with "Could not fetch rule set generation id" → `sudo update-alternatives --set iptables /usr/sbin/iptables-nft` (k3s's bundled binaries avoid this anyway).

---

## 0.6 Keep it running: idle timeouts, logon task, no sleep (B2)

**Goal:** halo is up after every logon and stays up with no terminal open.
**Why:** by default WSL stops a distro about 15 s after the last terminal closes, and the VM about 60 s after that. That's fine for dev tools, but fatal for a cluster hosting Phoenix. There are three layers: the idle timeouts set to `-1` (0.3), a scheduled task that boots the distro at logon and holds one process open (belt and braces), and Windows never sleeping on AC. It's the WSL version of setting a VM to "start automatically with the host".
**Where:** 🪟A

```powershell
$action   = New-ScheduledTaskAction -Execute "$env:WINDIR\System32\conhost.exe" `
            -Argument '--headless wsl.exe -d halo --exec /bin/sh -c "exec sleep infinity"'
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$trigger.Delay = 'PT20S'
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
            -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'WSL-halo-keepalive' -Action $action -Trigger $trigger -Settings $settings `
  -Description 'Boots WSL distro halo (k3s) at logon and keeps it alive' -Force

# Never sleep or hibernate on AC power; the screen may still turn off
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 15

Start-ScheduledTask -TaskName 'WSL-halo-keepalive'
Start-Sleep 5; wsl -l -v
```

**Expected:** `halo  Running  2`. Close every terminal, wait 2 minutes, run `wsl -l -v` again, and it should still say **Running**.

> **Unattended reboots (Windows Update at 3 a.m.):** an *AtLogOn* task only fires when you log in. For real around-the-clock uptime later, add an *AtStartup* trigger and register the task with `-User $env:USERNAME -Password (Read-Host)` ("run whether user is logged on or not"), or set *Active hours* in Windows Update so reboots happen while you're around. Note it now; decide before Phoenix goes live.

- [ ] Task registered; distro still Running 2 minutes after closing all terminals
- [ ] Sleep on AC = Never

**If it fails**
1. The task shows "Last Run Result 0x1" → `wsl.exe` ran before WSL was ready. The 20 s delay normally covers it, so increase it to `PT60S`.
2. The distro still stops → check `wsl --version` (3.0.x) and that `.wslconfig` has `vmIdleTimeout=-1`, then run `wsl --shutdown` and start the task again.
3. A console window appears → `conhost --headless` isn't supported on your build. Use `-Execute wsl.exe -Argument '-d halo --exec /bin/sh -c "exec sleep infinity"'` and accept a minimised window.

---

## 0.7 Filesystem layout and disk hygiene (B2)

**Goal:** know where data lives, and keep it on fast ext4.
**Why:** the distro's root filesystem is an `ext4.vhdx` (a virtual disk, like a thin-provisioned VMDK). `/mnt/c` is a 9P network share into Windows, often **10–50× slower** for many small files, with no proper Linux permissions. Git repos, container images, etcd and PVs all belong on `~/` or `/var/lib`, never on `/mnt/c`.

| What | Path (inside halo) | On Windows |
|---|---|---|
| Your repo | `~/src/ai-platform-portfolio` | `\\wsl.localhost\halo\home\<you>\src\…` (open with VS Code WSL, not Explorer) |
| k3s data (etcd, certs, images) | `/var/lib/rancher/k3s` | inside `ext4.vhdx` |
| local-path PVs | `/var/lib/rancher/k3s/storage/pvc-<uid>_<ns>_<pvc>` | inside `ext4.vhdx` |
| The disk file | — | `%LOCALAPPDATA%\wsl\{guid}\ext4.vhdx` (or your `--location`) |

Find the vhdx and its size (🪟):

```powershell
Get-ChildItem HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss | ForEach-Object {
  $p = Get-ItemProperty $_.PSPath; if ($p.DistributionName -eq 'halo') {
    $v = Join-Path $p.BasePath 'ext4.vhdx'; "{0}  {1:N1} GB" -f $v, ((Get-Item $v).Length/1GB) } }
```

**How it grows and shrinks:** the vhdx grows on demand (up to 1 TB by default) and does **not** shrink on its own when you delete files. With `sparseVhd=true` (set before install) it gives space back after a trim. Monthly, or after deleting big images or models:

```bash
# 🐧 tell the virtual disk which blocks are free
sudo fstrim -av
```
```powershell
# 🪟A if the file is still big: shut down, then compact
wsl --shutdown
wsl --manage halo --set-sparse true        # no-op if already sparse
# Manual compaction (works on Home and Pro):
#   diskpart → select vdisk file="<path from above>" → attach vdisk readonly → compact vdisk → detach vdisk → exit
```

- [ ] I know where my vhdx lives and how big it is

---

## 0.8 GPU flag (information only, don't set up now)

**Question:** will WSL block L2 (llama.cpp on the Radeon 8060S) or the bigger goal of several self-hosted models?

**Status (Nov 2026):**
- **ROCm on WSL:** since **ROCm 7.2.1 + Adrenalin 26.2.2**, AMD officially supports **Strix Halo (gfx1151)** under WSL2, through the open-source **ROCDXG** (`librocdxg`) path over `/dev/dxg`. Known gaps remain (for example, `hipMallocManaged` isn't supported on gfx1151), and you need WSL-specific runtime packages, not the standard `hsa-rocr`. Old guides that use `HSA_OVERRIDE_GFX_VERSION` / gfx1100 workarounds are out of date.
- **Vulkan in WSL:** only through Mesa's *Dozen* (Vulkan-on-D3D12). It works but is slow. Not recommended for llama.cpp.
- **DirectML:** Windows-native ML API. Not a fit for llama.cpp.
- **Inside Kubernetes:** the AMD GPU device plugin expects `/dev/kfd` + `/dev/dri`, and WSL exposes `/dev/dxg`. A pod *can* use the GPU through hostPath mounts of `/dev/dxg` and `/usr/lib/wsl`, but with **no device-plugin scheduling or accounting**. That isn't how production GPU nodes work.

**Verdict:** WSL does **not** block L2. Recommended path for L2: run **llama.cpp natively on Windows** (Vulkan or HIP backend; mature and fast on Strix Halo, with full access to the GPU memory share), and register it inside k3s as an **external backend**: a Service without a selector plus an EndpointSlice pointing at the Windows host IP (give the PC a DHCP reservation). LiteLLM in k3s routes to it, applies budgets and falls back. Stretch goal: a llama.cpp pod using ROCDXG via `/dev/dxg`, to mimic a "GPU node pool". Real Kubernetes GPU scheduling (device plugin / GPU Operator, MIG, bin-packing) is what the **AWS** labs are for.

**Impact on today's choices:** keep WSL at ≤ 48 GB so the GPU share can grow, keep model files on a Windows NTFS drive (`D:\models`), and keep k3s's node IP stable so the external-backend pattern stays simple.

---

## 0.9 First baseline snapshot (B2)

**Goal:** a whole-distro backup of the clean, prepared OS before k3s. You restore it in the Step 9 rebuild drill.
**Why:** `wsl --export` writes the distro's root filesystem to a tarball, like a VM template or a cold snapshot in vSphere. It's your fastest "back to known-good" button. Terminate the distro first so nothing is writing.
**Where:** 🪟

```powershell
$bk = "$env:USERPROFILE\WSL-backups"; New-Item -ItemType Directory -Force $bk | Out-Null
wsl --terminate halo
wsl --export halo "$bk\halo-baseline-$(Get-Date -Format yyyyMMdd).tar"
Get-ChildItem $bk | Select-Object Name,@{n='GB';e={[math]::Round($_.Length/1GB,2)}}
Start-ScheduledTask -TaskName 'WSL-halo-keepalive'
```

**Expected:** `Export in progress, this may take a few minutes. The operation completed successfully.` The file is about 1.5–3 GB.

> **Treat every export as a secret.** From Step 1 on, exports contain the cluster CA, tokens and Argo CD credentials. Keep them out of OneDrive, Git, or anything you'd make public. Put a copy on an external disk.

- [ ] `halo-baseline-YYYYMMDD.tar` exists

**If it fails:** "The file is in use" or the export hangs → run `wsl --shutdown` and try again. Not enough space → export straight to another drive (`D:\WSL-backups`).

---

### CKA corner: Step 0
- **Domain:** Cluster Architecture, Installation & Configuration (25%): node prerequisites for kubeadm are the same (modules, sysctls, cgroups, swap, container runtime).
- **Practise:** `lsmod | grep br_netfilter` · `sysctl net.ipv4.ip_forward` · `stat -fc %T /sys/fs/cgroup` · `systemctl status <unit>` · `journalctl -u <unit> -f`
- **Drill:** write `/etc/modules-load.d/k8s.conf` and `/etc/sysctl.d/k8s.conf` from memory in under 2 minutes (the kubeadm "install container runtime" page asks for exactly this).

**Interview angle:** "I treat even a laptop lab like a fleet node: pinned OS image, hardware sizing from a capacity budget, kernel prerequisites written as code, and a golden snapshot before the platform layer."
**Phoenix angle:** the keep-alive task, no-sleep policy and memory budget are what let Phoenix run around the clock on a PC you also use every day.

**Block B2 done when:** - [ ] baseline export exists · - [ ] distro survives closing all terminals.
