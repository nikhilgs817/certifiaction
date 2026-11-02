# Rebuild the Week 2–3 PDF

```bash
pip install markdown
python3 tools/build_pdf.py week2-lab-guide.md /tmp/week2.html
node tools/render.js /tmp/week2.html "$PWD/week2-lab-guide.pdf"     # needs Playwright + Chromium
```
`week2-lab-guide.md` is the source of truth; it embeds the files under `repo-files/` as copy-paste blocks.
