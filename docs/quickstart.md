# EnvShelf quickstart

This guide uses file paths only. Never put a secret value after a CLI flag, in a catalog, or in a browser form.

## Native setup

Install Python 3.9+ and the `age` package. From this repository:

```sh
mkdir -p ~/.config/envshelf/age
python3 -m app.cli init \
  --identity-file ~/.config/envshelf/age/identity.txt \
  --recipient-file ~/.config/envshelf/age/recipient.txt
```

The identity file is private. Restrict its access and back it up through a trusted encrypted store. The recipient file is public encryption metadata, but keeping it beside the identity is convenient.

Register one local checkout. This writes only metadata to `data/catalog.json` (which is ignored by Git):

```sh
python3 -m app.cli register \
  --slug example-api \
  --repo https://github.com/your-org/example-api \
  --path /absolute/path/to/example-api \
  --env-file .env
```

Create an encrypted backup. The source `.env` is passed directly to age; EnvShelf does not read it into Python:

```sh
python3 -m app.cli encrypt \
  --slug example-api \
  --recipient-file ~/.config/envshelf/age/recipient.txt \
  --output backups/example-api.env.age
```

Commit `backups/example-api.env.age` only after reviewing the diff. To restore, provide the private identity by path:

```sh
python3 -m app.cli restore \
  --slug example-api \
  --identity-file ~/.config/envshelf/age/identity.txt \
  --input backups/example-api.env.age
```

If `.env` already exists, restore first copies it to `.env.before-restore.<UTC timestamp>` and then replaces it atomically. Review and remove that plaintext backup yourself when it is no longer needed.

## Docker setup

The image includes Python, the dashboard, and `age`. The dashboard alone does not need access to any project directory. For CLI operations, mount the checkout and key directory explicitly:

```sh
docker compose up -d --build
docker compose run --rm \
  -v "$PWD:/workspace" \
  -v "$HOME/.config/envshelf/age:/keys:ro" \
  envshelf python -m app.cli register \
  --slug example-api --repo https://github.com/your-org/example-api \
  --path /workspace --catalog /var/lib/envshelf/catalog.json
docker compose run --rm \
  -v "$PWD:/workspace" \
  -v "$HOME/.config/envshelf/age:/keys:ro" \
  envshelf python -m app.cli encrypt \
  --slug example-api --recipient-file /keys/recipient.txt \
  --output /workspace/backups/example-api.env.age \
  --catalog /var/lib/envshelf/catalog.json
```

For restore, use the same mounts and replace `encrypt` with `restore`, passing `--identity-file /keys/identity.txt`. Keep the key mount read-only. Do not bake keys into an image or use `docker build` context containing a private identity.

## Moving machines

Clone or pull the repository, install EnvShelf, place the private identity in the protected local key path, register the new checkout path, and restore. The encrypted file is portable; the local catalog path is intentionally machine-local. Keep a tested copy of the identity before rotating or retiring a machine.
