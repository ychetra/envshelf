# EnvShelf dashboard

The dashboard is a local Svelte 5 + Vite app served by the Python API. It is a card workspace for one developer on one trusted machine: drag cards to reorder them, pin favorites, switch between Grid/List view, click a card for details, and run guarded Backup/Restore actions.

## Configuration

Set these non-secret values in `.env` before `docker compose up --build`:

| Variable | Meaning |
| --- | --- |
| `ENVSHELF_PROJECTS_HOST_PATH` | Host directory mounted as `/workspace`; only registered projects beneath it may run actions. |
| `ENVSHELF_CATALOG_ROOT` | Host root represented by paths in `catalog.json`; set it to the same absolute path as `ENVSHELF_PROJECTS_HOST_PATH` for Docker host-path catalogs. |
| `ENVSHELF_PROJECT_ROOT` | Container-side project root, normally `/workspace`. |
| `ENVSHELF_ALLOWED_PROJECT_ROOTS` | Comma-separated container paths accepted by initialization and action guards, for example `/workspace,/workspace-2`. |
| `ENVSHELF_KEYS_HOST_PATH` | Host directory mounted as `/keys` read-only. |
| `ENVSHELF_RECIPIENT_FILE` | Container path to the public age recipient. |
| `ENVSHELF_IDENTITY_FILE` | Container path to the private age identity. |

The add-project dialog has two modes:

- **Existing folder** accepts a folder drop or folder picker for filename-only detection. The browser never uploads, copies, or reads file contents. A browser cannot reveal the host's absolute path, so confirm the corresponding Docker-mounted path (for example `/workspace/my-app`) before registering.
- **Clone Git repo** clones into an explicit mounted root and registers metadata.

For literal Finder drag-and-drop, the optional unsigned macOS helper at
[`macos/EnvShelfDrop`](../macos/EnvShelfDrop) can inspect a dropped folder
locally and call the same register endpoint. It sends only the absolute path,
folder name, environment filenames, and credential-free Git origin. It never
uploads the folder or reads environment values. The server translates a host
path under `ENVSHELF_CATALOG_ROOT` to the explicit container mount and rejects
paths outside that root or containing user-controlled symlinks.

Both modes accept a display name and environment filenames. The server rejects paths outside `ENVSHELF_ALLOWED_PROJECT_ROOTS`, traversal, existing targets, symlinks, and unsafe environment filenames. It registers or clones the project; it never asks for a secret or returns a decrypted value. The dashboard opens in a light-first theme, supports an optional dark toggle, and uses a responsive full-width Grid/List shelf with local drag ordering and pins.

### Docker connection helper

The container can only see folders explicitly mounted in Compose. A browser cannot
grant Docker access to a Finder folder, so the dashboard explains the boundary
instead of pretending that a browser drop copied the project.

For the easiest macOS flow, build the optional `EnvShelfDrop` helper:

```sh
cd macos/EnvShelfDrop
swift run
```

Drop a project folder into the helper, choose the EnvShelf folder containing
`docker-compose.yml`, then approve the mount scope. The helper creates the ignored
local `docker-compose.override.yml`, mounts the selected folder's parent at
`/workspace`, runs `docker compose up -d`, waits for the dashboard, and registers
the dropped project. The parent scope is shown in the confirmation dialog because
all folders under that parent become visible to the container. It never reads or
sends `.env` values. Review the generated override if you do not want to expose
the selected parent; delete it and restart Compose to disconnect.

Without the helper, set `ENVSHELF_PROJECTS_HOST_PATH` to the host folder (such as
`~/Projects`) and restart Compose. In the dialog, the allowed root is shown; use
the matching container path under `/workspace`. Browser folder drop remains a
convenience for detecting names like `.env` and `.env.example`, not a file
transfer mechanism.

### Docker path mapping

For a host project tree at `/Users/me/Projects`, use this in `.env`:

```dotenv
ENVSHELF_PROJECTS_HOST_PATH=/Users/me/Projects
ENVSHELF_CATALOG_ROOT=/Users/me/Projects
ENVSHELF_PROJECT_ROOT=/workspace
ENVSHELF_ALLOWED_PROJECT_ROOTS=/workspace
```

The container mounts the host tree at `/workspace`. A catalog entry such as `/Users/me/Projects/api` is translated to `/workspace/api`, and action requests are rejected if the original path is outside the configured host root. The browser cannot override either root.

For two host trees, use the included second explicit mount:

```dotenv
ENVSHELF_PROJECTS_HOST_PATH=/Users/me/Projects
ENVSHELF_PROJECTS_HOST_PATH_2=/Users/me/Work
ENVSHELF_ALLOWED_PROJECT_ROOTS=/workspace,/workspace-2
```

Add another explicit Compose volume and root entry for additional trees; do not mount the whole host filesystem.

## Actions

- `Backup now` runs the registered project’s `encrypt` workflow using the configured recipient and writes its configured encrypted backup path.
- `Restore` requires typing `RESTORE`, runs the registered `restore` workflow using the configured identity, and preserves an existing `.env` as `.env.before-restore.<UTC timestamp>` first.
- Errors are intentionally generic. The server captures age/CLI output rather than returning it, because tool output can contain sensitive material.
- Grid/List preference is saved in browser local storage. Pins and card order are safe metadata saved in the local catalog volume.

Required key names come from each project’s `.env.example`. EnvShelf never reads `.env` into the dashboard and never shows any right-hand-side value.
