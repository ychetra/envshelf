# Architecture

- `app/cli.py` registers metadata and delegates encryption/decryption to the installed `age` binary. It accepts paths and metadata, not secret values.
- `app/server.py` serves `/api/health`, `/api/projects`, and slug-only `POST /api/projects/<slug>/{backup,restore}` routes. It reads `.env.example` only to derive key names and returns an explicit metadata allowlist.
- `src/App.svelte` is compiled with Svelte 5 + Vite into static assets. The dashboard has a sidebar, project detail panel, backup action, and typed-confirmation restore modal; no secret value crosses the browser boundary.
- Docker uses a multi-stage Node build followed by a small Python + `age` runtime. Compose persists only the metadata catalog in a named volume; project access is an explicit configurable mount and the key mount is read-only.

The catalog lives at `ENVSHELF_DATA_DIR/catalog.json` or `data/catalog.json` when run natively. It is machine-local and ignored by Git. Encrypted backups are separate files chosen by the user, commonly `backups/<slug>.env.age`.

The workflow is deliberately small:

```text
registered path + recipient file -> age -> ciphertext in repository
private identity + ciphertext -> age -> temporary plaintext -> preserved target
```

No secret value crosses the dashboard API or is persisted in the catalog.
