# EnvShelf agent notes

EnvShelf is a Docker-first, local-only project metadata dashboard with an age-backed CLI for encrypted environment backups. It does not provide hosted syncing, authentication, or secret-value API responses.

- Never inspect, print, log, persist, or commit secret values.
- Keep `data/catalog.json` local and ignored; use the example fixture for tests.
- Crypto must remain delegated to the established age binary; do not implement cryptography in Python.
- The dashboard may expose only project name, Git URL, environment count, and backup status.
- Run `docker compose config` and tests before release changes.
