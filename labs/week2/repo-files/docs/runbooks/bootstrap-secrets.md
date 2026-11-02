# Runbook: bootstrap secrets (what is done by hand on a rebuild)

Everything else comes back from Git. These items cannot: they are the keys that make Git's ciphertext usable.

## Inventory (password manager, vault "lab-halo")

| Item | Used by | If lost |
|---|---|---|
| `sealed-secrets-key-halo.yaml` (file attachment) | Sealed Secrets controller: decrypts every SealedSecret in Git | Re-seal everything (section "Key lost") |
| `Argo CD deploy key — halo` (private key) | Argo CD reads the repo | Generate a new deploy key, replace it on GitHub |
| `Argo CD admin — halo` (password) | Argo CD UI/CLI | `argocd account update-password` after bootstrap |
| `GHCR pull — halo` (classic PAT, read:packages, 90-day expiry) | `ghcr-pull` SealedSecret | New PAT -> `platform/scripts/seal-ghcr-pull.sh` |
| `Phoenix DB` (postgres + phoenix passwords) | Timescale, `phoenix-db-app` | Needed to reach an existing data directory |
| `Phoenix app` (basic auth, Fernet key), `Redis` | command-center, redis | Re-seal with new values |

## Rebuild order
1. Week 1 runbook `rebuild-halo.md` up to (not including) the Argo CD bootstrap.
2. Restore the sealing key file **before** the controller starts:
   `install -m 600 /dev/null ~/.secrets/sealed-secrets-key-halo.yaml` then paste the attachment into it
   (the bootstrap script applies it automatically).
3. Restore the deploy key to `~/.ssh/argocd-halo-deploy` (mode 600).
4. `platform/kubernetes/argocd/bootstrap/bootstrap-argocd.sh halo` -> rotate the admin password -> delete the initial secret.
5. Verify: `kubectl -n phoenix get secrets` lists timescale-auth, phoenix-db-app, redis-auth, phoenix-secrets, ghcr-pull.
6. `shred -u ~/.secrets/sealed-secrets-key-halo.yaml` (the password manager is the copy).

## Back up the sealing key (after the first install, and after any manual rotation)
```bash
mkdir -p ~/.secrets && chmod 700 ~/.secrets
kubectl -n kube-system get secret -l sealedsecrets.bitnami.com/sealed-secrets-key -o yaml \
  | yq 'del(.items[].metadata.resourceVersion, .items[].metadata.uid, .items[].metadata.creationTimestamp, .items[].metadata.managedFields)' \
  > ~/.secrets/sealed-secrets-key-halo.yaml
```
Attach the file to the password manager entry, then `shred -u ~/.secrets/sealed-secrets-key-halo.yaml`.

## Key lost (controller generated a new key)
SealedSecrets show `no key could decrypt secret`. Re-run `seal-ghcr-pull.sh`, `seal-phoenix-db.sh` (reuse the DB passwords
from the password manager if the data directory survived: seal them with `seal-secret.sh` instead of generating),
`seal-secret.sh` for redis-auth and phoenix-secrets; commit; back up the new key.

## Rotation calendar
GHCR PAT every 90 days (GitHub reminds you). Sealing key yearly (manual). Deploy key yearly.
