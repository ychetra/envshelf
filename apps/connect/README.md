# EnvShelf Connect

EnvShelf Connect is a Tauri v2 desktop companion for macOS, Windows, and Linux.
It offers both a Docker connector and a Docker-free standalone dashboard:

- **Open standalone dashboard** starts the bundled/source EnvShelf server on
  loopback with one native project-root choice and OS app-data catalog.
- **Connect to Docker** configures the explicit Compose mount flow below.

The Docker flow makes onboarding feel like a normal desktop drop target:

1. Drop a project folder or choose it with the native folder picker.
2. EnvShelf reads names and Git metadata only; it never reads or sends `.env`
   values.
3. Choose the EnvShelf repository once (the folder containing
   `docker-compose.yml`).
4. Approve the project parent folder. Connect writes an ignored local Compose
   override, starts Compose through the installed Docker CLI, and registers the
   project as `/workspace/...` in the local dashboard.

The companion does not use the Docker socket. It invokes `docker compose` as a
normal host process and captures no command output. The generated override is
stored under `.envshelf/`, protected by a local `.gitignore` and `.git/info/exclude`.

## Development

```sh
npm install
npm run tauri:dev
```

Build installers for the current platform:

```sh
npm run tauri:build
```

Release builds are configured in the repository workflow for macOS, Windows,
and Ubuntu. Docker must already be installed and the EnvShelf dashboard must be
running locally for automatic registration.
