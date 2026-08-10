# EnvShelf Connect

EnvShelf Connect is the optional desktop companion for literal Finder,
Explorer, and Linux file-manager folder drops. It is built with Tauri v2 and
ships installers for macOS, Windows, and Linux.

## Why a companion app?

Browsers can inspect a selected folder’s filenames, but they cannot grant a
Docker container access to an arbitrary host path. The companion receives the
folder path from the operating system, then performs the local connection
without uploading the folder or opening a Docker socket.

## First run

1. Start EnvShelf with Docker and open the dashboard once.
2. Install and open **EnvShelf Connect**.
3. Drop a project folder into the window, or use the native folder picker.
4. Choose the EnvShelf repository folder once—the folder containing
   `docker-compose.yml`.
5. Click **Approve & connect**.

The app detects only the project name, `.env*` filenames, and a redacted Git
remote. It never reads environment values. On approval it creates an ignored
`.envshelf/docker-compose.connect.local.yml`, starts `docker compose` through
the host CLI, and registers the project under `/workspace/...`.

The parent folder mount is explicit and visible before approval. This is the
one security confirmation that cannot be automated safely: Docker must not be
given whole-disk access by a browser or installer.

## Build locally

```sh
cd apps/connect
npm install
npm run tauri:dev
npm run tauri:build
```

The release workflow builds platform installers on every manual run or
`connect-v*` tag and uploads them as workflow artifacts.
