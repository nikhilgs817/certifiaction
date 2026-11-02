# repo-files — the Week 2–3 files, ready to copy

The final state of every file the Week 2–3 guide creates or changes in `ai-platform-portfolio`, after Step B4,
mirrored here so you can copy instead of pasting from the PDF. Paths are relative to the monorepo root.

```bash
# in WSL, with this repo cloned at ~/src/certifiaction
cp -rn ~/src/certifiaction/labs/week2/repo-files/. ~/src/ai-platform-portfolio/   # -n: never overwrite your files
```

Not included (you generate them; they are secret-derived): `platform/kubernetes/apps/phoenix-data/overlays/halo/sealed/*.yaml`
(`seal-phoenix-db.sh`, `seal-secret.sh`), the ciphertext in `apps/_shared/halo/values.yaml` (`seal-ghcr-pull.sh`) and
`apps/sealed-secrets/pub-cert.pem` (`kubeseal --fetch-cert`). Follow the guide's step order: several files have an
earlier version (A1, B2) before this final one. The Phoenix code changes are in nikhilgs817/PHOENIX_TRADER (PR #3).
