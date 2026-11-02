#!/usr/bin/env python3
"""Collate the L1 guide markdown files into one print-ready HTML (then PDF via Chromium)."""
import html, re, sys, os
import markdown
sys.path.insert(0, os.path.dirname(__file__))
from codefix import find_comment

SRC = sys.argv[1]
OUT = sys.argv[2]
CODE_LIMIT = 165  # max chars per code line that fits the landscape page

PARTS = [
    ("README.md", "overview", "Overview: versions, architecture, plan"),
    ("01-windows-wsl.md", "part-0", "Step 0: Windows + WSL2 foundation"),
    ("02-k3s-cluster.md", "part-1", "Steps 1-3: k3s, client tools, verification"),
    ("03-monorepo-gitops-layout.md", "part-4", "Step 4: Monorepo + GitOps layout"),
    ("04-argocd-app-of-apps.md", "part-5", "Steps 5-7: Argo CD, app of apps, podinfo"),
    ("05-prove-rebuild.md", "part-8", "Steps 8-10: Prove GitOps, rebuild, self-manage"),
    ("06-appendix.md", "appendix", "Appendix: troubleshooting, glossary, checklist"),
]
LINKMAP = {f: "#" + a for f, a, _ in PARTS}

TAGS = [("🪟A", "[WIN-ADMIN]"), ("🪟", "[WIN]"), ("🐧", "[WSL]"), ("🌐", "[BROWSER]"), ("🐙", "[GITHUB]"),
        ("🎯 ", ""), ("✅ ", ""), ("📦 ", ""), ("🚧 ", "(in progress) "), ("🚧", "(in progress)")]

ASCII_ARCH = r"""Windows 11 (daily PC) - MS-S1 Max, 128 GB, Radeon 8060S
 |  Browser ...... http://podinfo.halo.localhost  |  http://argocd.halo.localhost   (*.localhost -> 127.0.0.1, no DNS)
 |  PowerShell ... kubectl / helm / argocd -> kubeconfig https://127.0.0.1:6443
 |  Task Scheduler at logon -> keeps WSL distro "halo" alive
 |
 '--> WSL localhost relay (NAT mode, localhostForwarding): 127.0.0.1:80 / :443 / :6443  --> into the VM
        |
        v
 WSL2 utility VM (Hyper-V) - 48 GB / 16 vCPU
 '-- Ubuntu 24.04 distro "halo" (systemd, ext4.vhdx)
      |-- eth0   172.x.x.x       (changes every boot - not used by k3s)
      |-- halo0  10.255.255.10   (dummy NIC, stable node IP)
      '-- k3s v1.36.5 server (systemd), node "halo"
           |-- control plane: apiserver, scheduler, controller-manager, embedded etcd, containerd, flannel
           |-- Traefik (hostNetwork :80/:443)
           |     |-- Host: argocd.halo.localhost   --> Service argocd-server  (ns argocd)
           |     '-- Host: podinfo.halo.localhost  --> Service podinfo --> pods  (ns podinfo)
           |-- Argo CD --(apply / prune / self-heal)--> podinfo
           '-- local-path PVs: /var/lib/rancher/k3s/storage
                |
 Argo CD  --(git pull over SSH every ~3 min, read-only deploy key)-->  GitHub: ai-platform-portfolio (private)"""

LABELS = {
    "bash": ("cmd-wsl", "WSL Ubuntu shell (bash) - copy &amp; paste"),
    "powershell": ("cmd-win", "Windows PowerShell - copy &amp; paste"),
    "": ("ref", "Output / reference - not a command"),
    "diagram": ("ref", "Diagram"),
}

stash, counter = {}, {"n": 0, "cmd": 0}
too_long = []


def fix_code(lang, lines):
    out = []
    for ln in lines:
        for a, b in TAGS:
            ln = ln.replace(a, b)
        if len(ln) > CODE_LIMIT and lang in ("bash", "powershell"):
            i = find_comment(ln)
            prev = out[-1].rstrip() if out else ""
            if i > 0 and not prev.endswith(("\\", "`", "|")):
                ind = re.match(r"\s*", ln).group(0)
                out += [ind + ln[i:].strip(), ln[:i].rstrip()]
                continue
        if len(ln) > CODE_LIMIT:
            too_long.append(ln)
        out.append(ln)
    while out and out[-1] == "":
        out.pop()
    return out


def code_html(lang, lines):
    if lang == "mermaid":
        lang, lines = "diagram", ASCII_ARCH.split("\n")
    lines = fix_code(lang, lines)
    cls, label = LABELS.get(lang, ("ref", lang))
    if cls.startswith("cmd"):
        counter["cmd"] += 1
        label = f"#{counter['cmd']:03d} &nbsp;{label}"
    body = html.escape("\n".join(lines))
    avoid = " avoid" if len(lines) <= 22 else ""
    return (f'<div class="code {cls}{avoid}"><div class="code-h">{label}</div>'
            f'<pre><code>{body}</code></pre></div>')


def extract_fences(text):
    out, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        m = re.match(r"^(\s*(?:>\s?)?)```(\w*)\s*$", lines[i])
        if not m:
            out.append(lines[i]); i += 1; continue
        prefix, lang = m.group(1), m.group(2)
        body, i = [], i + 1
        while i < len(lines) and not re.match(r"^\s*(?:>\s?)?```\s*$", lines[i]):
            ln = lines[i]
            body.append(ln[len(prefix):] if ln.startswith(prefix) else ln.lstrip("> ") if prefix.strip() else ln)
            i += 1
        i += 1
        counter["n"] += 1
        key = f"CODEBLOCK{counter['n']:04d}X"
        stash[key] = code_html(lang, body)
        out += [prefix, prefix + key, prefix]
    return "\n".join(out)


def prep(text):
    text = extract_fences(text)
    text = "\n".join(l for l in text.split("\n") if not l.lstrip().startswith("← "))
    for a, b in TAGS:
        text = text.replace(a, b)
    text = re.sub(r"\]\(((?:0\d-[\w-]+|README)\.md)\)", lambda m: "](" + LINKMAP.get(m.group(1), "#") + ")", text)
    text = re.sub(r"^ {2,3}([-*] |\d+\. )", r"    \1", text, flags=re.M)  # nested lists need 4 spaces
    text = re.sub(r"^(\s*)- \[ \] ", r"\1- ☐ ", text, flags=re.M)
    text = text.replace(" - [ ] ", " ☐ ").replace("· - [ ]", "· ☐")
    return text


md = markdown.Markdown(extensions=["tables", "sane_lists", "attr_list"])
sections, toc = [], []
for fname, anchor, title in PARTS:
    raw = open(os.path.join(SRC, fname), encoding="utf-8").read()
    h = md.reset().convert(prep(raw))
    for key, val in stash.items():
        h = h.replace(f"<p>{key}</p>", val).replace(key, val)
    subs = re.findall(r"<h2>(.*?)</h2>", h)
    n = [0]
    def addid(m):
        n[0] += 1
        return f'<h2 id="{anchor}-{n[0]}">{m.group(1)}</h2>'
    h = re.sub(r"<h2>(.*?)</h2>", addid, h)
    toc.append((anchor, title, [(f"{anchor}-{k+1}", re.sub('<[^>]+>', '', s)) for k, s in enumerate(subs)]))
    sections.append(f'<section class="part" id="{anchor}">{h}</section>')

toc_html = "".join(
    f'<li><a href="#{a}"><b>{html.escape(t)}</b></a><ul>' +
    "".join(f'<li><a href="#{i}">{s}</a></li>' for i, s in subs if not s.startswith("CKA corner")) +
    "</ul></li>" for a, t, subs in toc)

CSS = r"""
@page { size: A4 landscape; margin: 13mm 12mm 14mm 12mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: 'DejaVu Sans', 'Liberation Sans', sans-serif; font-size: 9.6pt; line-height: 1.42; color: #1b1f24; margin: 0; }
h1 { font-size: 19pt; color: #0b3d2e; border-bottom: 2.5px solid #2d6a4f; padding-bottom: 4px; margin: 0 0 10px; }
h2 { font-size: 13.5pt; color: #0b3d2e; margin: 18px 0 6px; padding: 4px 8px; background: #e8f3ee; border-left: 5px solid #2d6a4f; break-after: avoid; }
h3 { font-size: 11pt; color: #14532d; margin: 14px 0 4px; break-after: avoid; }
h4 { font-size: 10pt; margin: 10px 0 3px; break-after: avoid; }
p, li { max-width: 245mm; }
p { margin: 4px 0 6px; }
ul, ol { margin: 3px 0 6px; padding-left: 20px; }
li { margin: 1px 0; }
a { color: #1d4ed8; text-decoration: none; }
code { font-family: 'DejaVu Sans Mono', monospace; font-size: 8.4pt; background: #f1f3f5; padding: 0 3px; border-radius: 3px; font-variant-ligatures: none; }
table { border-collapse: collapse; margin: 6px 0 10px; font-size: 8.7pt; max-width: 100%; break-inside: auto; }
th, td { border: 1px solid #cfd6dd; padding: 3px 6px; vertical-align: top; text-align: left; }
th { background: #eef2f5; }
tr { break-inside: avoid; }
blockquote { margin: 8px 0; padding: 6px 12px; background: #fff8e6; border-left: 4px solid #e0a100; }
blockquote h3 { margin-top: 2px; }
hr { border: 0; border-top: 1px solid #d0d7de; margin: 12px 0; }
.part { break-before: page; }
.code { margin: 6px 0 10px; border: 1px solid #c9d1d9; border-radius: 5px; overflow: hidden; }
.code.avoid { break-inside: avoid; }
.code-h { font-size: 7.6pt; font-weight: bold; letter-spacing: .3px; padding: 2px 8px; color: #fff; }
.cmd-wsl .code-h { background: #6f42c1; }
.cmd-win .code-h { background: #0b5cad; }
.ref .code-h { background: #6b7280; }
.code pre { margin: 0; padding: 6px 9px; background: #fbfcfd; white-space: pre; overflow: hidden; }
.ref pre { background: #f6f7f9; }
.code pre code { font-family: 'DejaVu Sans Mono', monospace; font-size: 7.6pt; line-height: 1.32; background: none; padding: 0; font-variant-ligatures: none; }
.cover { height: 175mm; display: flex; flex-direction: column; justify-content: center; }
.cover h1 { font-size: 30pt; border: 0; margin-bottom: 4px; }
.cover .sub { font-size: 14pt; color: #2d6a4f; margin-bottom: 18px; }
.cover .meta { font-size: 10.5pt; color: #374151; line-height: 1.7; }
.legend { margin-top: 18px; font-size: 9.5pt; }
.legend span { display: inline-block; color: #fff; padding: 1px 8px; border-radius: 3px; font-weight: bold; font-size: 8pt; margin-right: 6px; }
.toc { break-before: page; columns: 2; column-gap: 12mm; font-size: 9.4pt; }
.toc h1 { column-span: all; }
.toc ul { list-style: none; padding-left: 0; } .toc ul ul { padding-left: 14px; margin-bottom: 6px; }
.toc li { max-width: none; break-inside: avoid; }
"""

cover = f"""
<div class="cover">
  <h1>L1 Week 1: k3s on WSL2 + Argo CD</h1>
  <div class="sub">Cluster <b>halo</b> &middot; Checkpoint: Argo CD syncing a sample app from Git</div>
  <div class="meta">
    Production-style home-lab build on the Minisforum MS-S1 Max (Windows 11 + WSL2 Ubuntu 24.04)<br>
    k3s v1.36.5+k3s1 &middot; kubectl v1.36.6 &middot; Helm v4.3.1 &middot; Argo CD chart 10.11.6 (v3.5.6) &middot; podinfo 6.17.0<br>
    Versions checked 2026-11-02 &middot; Project MLOps / ai-platform-portfolio
  </div>
  <div class="legend"><b>How to copy commands:</b> every command box is numbered and colour-coded by where it runs.
    Select the whole box (from its first to last line) and paste it into the matching shell.<br><br>
    <span style="background:#6f42c1">WSL Ubuntu shell (bash)</span>
    <span style="background:#0b5cad">Windows PowerShell</span>
    <span style="background:#6b7280">Output / reference - not a command</span><br><br>
    Text tags: [WIN-ADMIN] = PowerShell as Administrator &middot; [WIN] = normal PowerShell &middot; [WSL] = WSL shell (<code>wsl -d halo</code>) &middot;
    [BROWSER] = browser &middot; [GITHUB] = GitHub web UI &middot; &#9744; = checkbox to tick
  </div>
</div>
<div class="toc"><h1>Contents</h1><ul>{toc_html}</ul></div>
"""

doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>L1 k3s on WSL2 + Argo CD - halo</title>
<style>{CSS}</style></head><body>{cover}{''.join(sections)}</body></html>"""
open(OUT, "w", encoding="utf-8").write(doc)
print(f"html written: {OUT}  code blocks={counter['n']} commands={counter['cmd']}  too_long={len(too_long)}")
for l in too_long:
    print("  LONG", len(l), l[:120])
