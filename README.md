# EnvShelf

EnvShelf is a local-first project shelf with a small dashboard and a Git-friendly encrypted environment workflow. It stores project metadata locally and uses the established `age` tool for encryption. It never accepts, returns, or logs secret values.

The dashboard is intentionally read-only: it shows project names, Git URLs, environment counts, and backup status. The CLI performs the path-based encrypt and restore operations so credentials never pass through a browser form or API.

## Start the dashboard

```sh
cp .env.example .env
docker compose up --build
```

Open <http://localhost:8787>. The named Docker volume keeps the local catalog across container recreation. Stop it with `docker compose down`; this leaves the volume in place.

## CLI in one minute

Run natively with Python and `age` installed, or run the same commands through the Docker image:

```sh
python3 -m app.cli init \
  --identity-file ~/.config/envshelf/age/identity.txt \
  --recipient-file ~/.config/envshelf/age/recipient.txt
python3 -m app.cli register --slug my-api --repo https://github.com/me/my-api --path /path/to/my-api
python3 -m app.cli encrypt --slug my-api --recipient-file ~/.config/envshelf/age/recipient.txt
python3 -m app.cli restore --slug my-api --identity-file ~/.config/envshelf/age/identity.txt
```

The default encrypted output is `backups/my-api.env.age`. Existing plaintext is preserved as `.env.before-restore.<UTC timestamp>` before restore. The catalog contains metadata and paths only; it never contains environment values or private key contents.

## First and second machine

1. On the first machine, run `init` once and keep the identity file in a secure password-manager/Keychain-backed location. Keep the recipient file with the project tooling.
2. Commit only the encrypted `backups/<slug>.env.age` file and metadata that is safe for your repository. The private identity file must stay out of Git and out of the Docker image.
3. On another machine, clone the repository, install/run EnvShelf, copy the private identity into the same protected local key path, register the local project path, then run `restore`.
4. If the identity is lost, an age backup cannot be recovered. Test restore on a disposable checkout before relying on the workflow.

## Public-repository boundary

Safe to publish: EnvShelf source, `catalog.example.json`, documentation, and `.age` ciphertext encrypted to your recipient. Never publish: `.env` files, decrypted restore backups, age identity/private-key files, tokens, passwords, or logs containing them. Review `git diff` and `git status --ignored` before every push.

See [docs/quickstart.md](docs/quickstart.md), [docs/security.md](docs/security.md), and [docs/architecture.md](docs/architecture.md) for the complete workflow.
