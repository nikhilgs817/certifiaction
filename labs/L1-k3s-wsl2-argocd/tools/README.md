# Rebuild the PDF

```bash
pip install markdown
python3 tools/build.py . /tmp/guide.html
node tools/render.js /tmp/guide.html "$PWD/L1-k3s-wsl2-argocd-guide.pdf"   # needs Playwright + Chromium
```
