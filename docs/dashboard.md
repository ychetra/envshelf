# EnvShelf dashboard

The dashboard is a small Svelte 5 + Vite app compiled into static files and served by the dependency-free Python server. It is designed for one developer on one trusted machine: local metadata is convenient, while encrypted ciphertext can remain Git-friendly.

## Configuration

Set these non-secret values in `.env` before `docker compose up --build`:

| Variable | Meaning |
| --- | --- |
| `ENVSHELF_PROJECTS_HOST_PATH` | Host directory mounted as `/workspace`; only registered projects beneath it may run actions. |
| `ENVSHELF_CATALOG_ROOT` | Host root represented by paths in `catalog.json`; set it to the same absolute path as `ENVSHELF_PROJECTS_HOST_PATH` for Docker host-path catalogs. |
| `ENVSHELF_PROJECT_ROOT` | Container-side project root, normally `/workspace`. |
| `ENVSHELF_KEYS_HOST_PATH` | Host directory mounted as `/keys` read-only. |
| `ENVSHELF_RECIPIENT_FILE` | Container path to the public age recipient. |
| `ENVSHELF_IDENTITY_FILE` | Container path to the private age identity. |

The dashboard intentionally does not provide a path picker or secret input. This keeps a browser request from selecting arbitrary files or sending credentials. Register projects and choose their backup path with the CLI; the dashboard then uses the catalog metadata.

### Docker path mapping

For a host project tree at `/Users/me/Projects`, use this in `.env`:

```dotenv
ENVSHELF_PROJECTS_HOST_PATH=/Users/me/Projects
ENVSHELF_CATALOG_ROOT=/Users/me/Projects
ENVSHELF_PROJECT_ROOT=/workspace
```

The container mounts the host tree at `/workspace`. A catalog entry such as `/Users/me/Projects/api` is translated to `/workspace/api`, and action requests are rejected if the original path is outside the configured host root. The browser cannot override either root.

## Actions

- `Backup now` runs the registered project’s `encrypt` workflow using the configured recipient and writes its configured encrypted backup path.
- `Restore` requires typing `RESTORE`, runs the registered `restore` workflow using the configured identity, and preserves an existing `.env` as `.env.before-restore.<UTC timestamp>` first.
- Errors are intentionally generic. The server captures age/CLI output rather than returning it, because tool output can contain sensitive material.

Required key names come from each project’s `.env.example`. EnvShelf never reads `.env` into the dashboard and never shows any right-hand-side value.
