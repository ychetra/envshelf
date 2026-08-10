# Architecture

- `app/cli.py` registers metadata and delegates encryption/decryption to the installed `age` binary. It accepts paths and metadata, not secret values.
- `app/server.py` serves `/api/health` and `/api/projects`. It reads a local catalog and returns an explicit metadata allowlist.
- `web/index.html` is a dependency-free, read-only dashboard. It is useful for discovery and backup status, not secret entry or decryption.
- Docker packages Python and `age`. Compose persists only the metadata catalog in a named volume; project and key mounts are opt-in for one CLI invocation.

The catalog lives at `ENVSHELF_DATA_DIR/catalog.json` or `data/catalog.json` when run natively. It is machine-local and ignored by Git. Encrypted backups are separate files chosen by the user, commonly `backups/<slug>.env.age`.

The workflow is deliberately small:

```text
registered path + recipient file -> age -> ciphertext in repository
private identity + ciphertext -> age -> temporary plaintext -> preserved target
```

No secret value crosses the dashboard API or is persisted in the catalog.
