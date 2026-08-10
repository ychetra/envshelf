# EnvShelf dashboard demo

[Watch the short product preview](assets/envshelf-preview.mp4). It is a brand
illustration, not a simulated app recording. The steps below run the real
dashboard against a disposable synthetic catalog—no real project paths, Git
repositories, environment values, or key material.

## Run the interactive demo

From the repository root:

```sh
./docs/demo.sh
```

Then open <http://localhost:8787>.

The demo flow is:

1. Select **Starlight API** in the project sidebar.
2. Confirm that the detail panel shows the local path, Git URL, encrypted backup path,
   and key names only (`APP_PORT`, `DATABASE_URL`, `SESSION_SECRET`).
3. Click **Backup now** after supplying a disposable age recipient in the demo fixture.
4. Click **Restore**, type `RESTORE`, and confirm. EnvShelf preserves the existing `.env`
   beside the restored file before replacement.

The dashboard is metadata-only: it never displays secret values. `docs/demo.sh`
creates a temporary fixture and removes it when stopped with Ctrl-C.

## Recording note

The included preview intentionally does not pretend to be an interaction
recording. To create a real walkthrough, run this synthetic demo and record the
four steps above with any local screen recorder. Never use a real project or
real environment file in release media.
