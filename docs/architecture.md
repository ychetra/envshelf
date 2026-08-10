# Architecture

- `app/cli.py` registers metadata and delegates encryption/decryption to the installed `age` binary. It accepts paths and metadata, not secret values.
- `app/server.py` serves `/api/health`, `/api/config`, `/api/projects`, `POST /api/projects/init`, pin/reorder routes, and slug-only backup/restore routes. It reads `.env` and `.env.example` only to derive key names/presence booleans and returns an explicit metadata allowlist.
- `src/App.svelte` is compiled with Svelte 5 + Vite into static assets. The dashboard has a responsive draggable card workspace, Grid/List preference, project details dialog, initialization dialog, backup action, and typed-confirmation restore modal; no secret value crosses the browser boundary.
- Docker uses a multi-stage Node build followed by a small Python + `age` runtime. Compose persists only the metadata catalog in a named volume; project access is an explicit configurable mount and the key mount is read-only.
- `macos/EnvShelfDrop` is an optional SwiftUI native helper for Finder drag-and-drop. It sends metadata-only registration requests; host paths are translated server-side through the configured catalog root and never become unrestricted filesystem access.

The catalog lives at `ENVSHELF_DATA_DIR/catalog.json` or `data/catalog.json` when run natively. It is machine-local and ignored by Git. Encrypted backups are separate files chosen by the user, commonly `backups/<slug>.env.age`.

The workflow is deliberately small:

```text
registered path + recipient file -> age -> ciphertext in repository
private identity + ciphertext -> age -> temporary plaintext -> preserved target
```

No secret value crosses the dashboard API or is persisted in the catalog.
