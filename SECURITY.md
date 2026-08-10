# Security Policy

## Scope

EnvShelf is designed for local use. It stores project metadata and delegates
encryption to the `age` command. It is not a hosted secret manager and does
not provide authentication or multi-user access control.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Contact the
maintainers privately through the security contact configured for the public
repository. Include a description, affected version or commit, reproduction
steps that contain no real secrets, and the potential impact.

Allow reasonable time for triage and remediation before public disclosure.

## Secret-handling rules

- Never commit `.env` files, decrypted backups, identity/private-key files,
  tokens, passwords, or logs containing secrets.
- Keep age identity files in a password-manager or other protected local path.
- Review `git diff`, `git status --ignored`, and the repository contents before
  publishing or pushing.
- Treat any exposed credential as compromised: revoke or rotate it immediately.

If a secret has been committed, removing it in a later commit is not enough;
revoke or rotate the secret and then remove it from the repository history as
appropriate.
