# Security boundary

EnvShelf is local-only metadata plus a thin wrapper around `age`. It does not provide a hosted secret manager, authentication, access control, key escrow, or cloud sync. The dashboard is not a secret editor and its API allowlists metadata fields. Bind the published port to loopback (the Compose default) and treat the local machine as the trust boundary.

## What is protected

- The source `.env` is passed to the external `age` process by path; its contents are not loaded into the catalog, HTTP response, or normal CLI output.
- Encryption uses a public age recipient. Decryption requires the private age identity file, which is supplied by path and never parsed by EnvShelf.
- Output is written to a temporary file and atomically renamed. Restore preserves an existing target beside it before replacement.
- The Docker service is non-root, read-only at its root filesystem, and has no-new-privileges. Project and key access exists only when explicitly mounted for a CLI run.
- Browser actions accept only a validated registered slug and an empty POST body. The server derives project, backup, catalog, recipient, and identity paths from local configuration; it rejects projects outside `ENVSHELF_PROJECT_ROOT` and never returns subprocess output.
- Required environment names are parsed from `.env.example`; values from that file and `.env` are never included in API responses.

## Public Git rules

Ciphertext such as `backups/project.env.age` may be committed when encrypted to the intended recipient. Never commit `.env`, restore-preservation files, age identities/private keys, passwords, tokens, or logs containing them. An encrypted file is not proof that the recipient or repository policy is correct; review the recipient and repository access separately.

## Recovery and rotation

Back up the private identity using a trusted encrypted store and verify a restore on a disposable checkout. Loss of the identity makes the ciphertext unrecoverable. For rotation, create a new identity, decrypt an existing backup using the old identity, encrypt it to the new recipient, verify restore, then revoke/remove the old identity according to your access policy. Do not delete the old identity before verification.

## Limits

EnvShelf cannot prevent a user or another process with filesystem access from reading a plaintext `.env`. It also cannot make a compromised host safe. Use filesystem permissions, host disk encryption, protected key storage, repository review, and least-privilege mounts alongside this tool.
