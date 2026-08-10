# Contributing to EnvShelf

Thanks for helping improve EnvShelf. Small, focused pull requests are easiest
to review.

## Before you start

- Read the README and the documentation in `docs/`.
- For behavior changes, open an issue first so the scope is clear.
- Never include `.env` files, decrypted backups, age identity files, tokens,
  passwords, or other private material in an issue or pull request.

## Development

Run the test suite and validate the Compose file before submitting a change:

```sh
python3 -m unittest discover -s tests -v
docker compose config
```

Keep the dashboard metadata-only. Do not add endpoints or logs that expose
secret values. Cryptographic operations must continue to use the established
`age` executable; do not implement cryptography in application code.

## Pull requests

Describe what changed, why it changed, and how you verified it. Include tests
for bug fixes and new behavior. Keep unrelated formatting or generated files
out of the pull request.
