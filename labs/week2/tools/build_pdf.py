#!/usr/bin/env python3
"""Render the Week 2-3 guide (one Markdown file) into print-ready HTML; render.js turns it into the PDF."""
import html, re, sys, os
import markdown
sys.path.insert(0, os.path.dirname(__file__))
from codefix import find_comment

SRC = sys.argv[1]   # one Markdown file; every "# " heading starts a part
OUT = sys.argv[2]
CODE_LIMIT = 165  # max chars per code line that fits the landscape page

PARTS = []  # filled from the H1 headings of the single source file
LINKMAP = {}

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
    """Stash fenced code blocks (``` or longer fences, optionally inside a > blockquote) before Markdown runs."""
    out, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        m = re.match(r"^(\s*(?:>\s?)?)(`{3,})(\w*)\s*$", lines[i])
        if not m:
            out.append(lines[i]); i += 1; continue
        prefix, fence, lang = m.group(1), m.group(2), m.group(3)
        close = re.compile(r"^\s*(?:>\s?)?" + fence + r"\s*$")
        body, i = [], i + 1
        while i < len(lines) and not close.match(lines[i]):
            ln = lines[i]
            body.append(ln[len(prefix):] if ln.startswith(prefix) else ln.lstrip("> ") if prefix.strip() else ln)
            i += 1
        i += 1
        counter["n"] += 1
        key = f"CODEBLOCK{counter['n']:04d}X"
        stash[key] = code_html(lang, body)
        out += [prefix, prefix + key, prefix]
    return "\n".join(out)


def separate_lists(text):
    """Markdown needs a blank line before a list that follows a paragraph line (e.g. "**If it fails**")."""
    out = []
    for line in text.split("\n"):
        starts_list = re.match(r"^(\d+\.|[-*]) ", line)
        prev = out[-1] if out else ""
        if starts_list and prev.strip() and not re.match(r"^\s*(\d+\.|[-*]) ", prev) \
                and not prev.lstrip().startswith(("|", ">", "#")) and not prev.startswith("   "):
            out.append("")
        elif line.startswith("**") and prev.startswith("**"):
            out.append("")             # "**Goal:**", "**Why:**", "**CKA corner:**" ... each its own paragraph
        out.append(line)
    return "\n".join(out)


def prep(text):
    text = separate_lists(extract_fences(text))
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
raw_all = open(SRC, encoding="utf-8").read()
chunks, cur, in_fence = [], [], False  # in_fence holds the open fence string
for line in raw_all.split("\n"):          # split at "# " headings, but never inside ``` fences
    fm = re.match(r"^\s*(?:>\s?)?(`{3,})", line)
    if fm and not in_fence:
        in_fence = fm.group(1)
    elif fm and in_fence and fm.group(1) == in_fence and line.strip().strip(">").strip() == in_fence:
        in_fence = False
    if not in_fence and line.startswith("# ") and cur:
        chunks.append("\n".join(cur)); cur = []
    cur.append(line)
chunks.append("\n".join(cur))
chunks = [c for c in chunks if c.strip()]
for idx, raw in enumerate(chunks):
    title = raw.split("\n", 1)[0].lstrip("# ").strip()
    anchor = f"part-{idx}"
    h = md.reset().convert(prep(raw))
    for key, val in stash.items():
        h = h.replace(f"<p>{key}</p>", val).replace(key, val)
    subs = re.findall(r"<h2>(.*?)</h2>", h)
    n = [0]
    def addid(m, anchor=anchor):
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
  <h1>L1 Weeks 2&ndash;3: Paved road + Phoenix on halo</h1>
  <div class="sub">Service template &middot; GitHub Actions + GHCR &middot; Sealed Secrets &middot; Phoenix Command Center as first tenant &middot; CKA drills</div>
  <div class="meta">
    W3 checkpoint: <b>the Command Center deploys through the template</b><br>
    Builds on the Week 1 guide (Rev 2): k3s v1.36.5+k3s1 &middot; Argo CD 10.11.6 (v3.5.6) &middot; Helm v4.3.1<br>
    New: FastAPI 0.162.0 &middot; Python 3.14.10 / 3.12.16 &middot; uv 0.13.6 &middot; Copier 9.19.1 &middot; Sealed Secrets 0.41.2 &middot; TimescaleDB 2.31.0-pg18 &middot; Redis 8.10.3<br>
    Versions checked 2026-11-02 &middot; Plan: Nov 12&ndash;15 (Part A), Nov 16&ndash;22 (Part B)
  </div>
  <div class="legend"><b>How to copy commands:</b> every command box is numbered and colour-coded by where it runs.
    Select the whole box (from its first to last line) and paste it into the matching shell. File boxes write the
    file with <code>cat &gt; 'path' &lt;&lt;'__EOF__'</code> from the repo root (<code>~/src/ai-platform-portfolio</code>).<br><br>
    <span style="background:#6f42c1">WSL Ubuntu shell (bash)</span>
    <span style="background:#0b5cad">Windows PowerShell</span>
    <span style="background:#6b7280">Output / reference - not a command</span><br><br>
    Text tags: [WSL] = WSL shell &middot; [WIN] = PowerShell &middot; [VS Code] &middot; [BROWSER] &middot; [GITHUB] = github.com &middot; &#9744; = checkbox
  </div>
</div>
<div class="toc"><h1>Contents</h1><ul>{toc_html}</ul></div>
"""

doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>L1 Weeks 2-3 - paved road + Phoenix</title>
<style>{CSS}</style></head><body>{cover}{''.join(sections)}</body></html>"""
open(OUT, "w", encoding="utf-8").write(doc)
print(f"html written: {OUT}  code blocks={counter['n']} commands={counter['cmd']}  too_long={len(too_long)}")
for l in too_long:
    print("  LONG", len(l), l[:120])
