# Standalone mode (no Docker)

EnvShelf can run as a native, loopback-only dashboard. The launcher accepts one
explicit project root, stores the metadata catalog in the operating system's
app-data folder, and starts the same Python server used by the Docker image.
Project files stay where the user selected them. No project contents are
uploaded to a service and the dashboard never returns environment values.

## Try it from a checkout

Install Python 3 and the official `age` executable, then run:

```sh
python3 standalone/run.py --projects-root "$HOME/Projects"
```

On Windows use `python standalone\run.py --projects-root "C:\Users\me\Projects"`.
The launcher chooses the normal OS app-data location for `catalog.json`:

| OS | Local catalog directory |
| --- | --- |
| macOS | `~/Library/Application Support/EnvShelf` |
| Windows | `%APPDATA%\\EnvShelf` |
| Linux | `$XDG_DATA_HOME/envshelf`, or `~/.local/share/envshelf` |

The dashboard binds to `127.0.0.1` and reports `standalone: true` from
`/api/config`. Projects can be dropped/registered directly in the native
folder. The server only permits paths below the selected root.

## Desktop app

EnvShelf Connect includes a **Open standalone dashboard** flow. Choose the
EnvShelf checkout/resource folder once and then choose the projects folder.
The app launches `standalone/run.py` and opens the local dashboard. The Docker
connector remains available as a separate flow for users who prefer Compose.

The current local proof expects Python 3 and the EnvShelf resource folder to be
available. Release builds will bundle the server resources and a verified age
sidecar; they must not silently search or mount a whole home directory.

## Encryption boundary

EnvShelf delegates encryption and decryption to the official age executable.
Install age v1.3.1 from the verified release resources described in
[`resources/age/README.md`](../resources/age/README.md), or set
`ENVSHELF_AGE_BIN` and `ENVSHELF_AGE_KEYGEN_BIN` to approved binaries. Keep the
identity file outside Git and outside the application bundle.

## Release packaging status

The Tauri workflow builds macOS, Windows, and Ubuntu artifacts from one source
tree. The age manifest pins the upstream URLs and SHA-256 digests. The `.proof`
files are retained with downloaded resources; Sigsum verification is a release
gate to wire into the packaging job before publishing installers. No local
Windows or Linux installer is claimed by a macOS build.
