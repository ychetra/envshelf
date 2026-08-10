# Pinned age sidecar resources

EnvShelf never implements cryptography. Release packaging downloads the
official [age v1.3.1 release](https://github.com/FiloSottile/age/releases/tag/v1.3.1)
from FiloSottile's repository, verifies the SHA-256 digest, and keeps the
matching `.proof` file beside it. The binary is only used through the existing
CLI boundary.

The pinned values below were read from the upstream GitHub release metadata on
2026-08-10. The release job must fail closed if a URL, digest, or proof is
missing or changes.

| Platform | Archive | SHA-256 |
| --- | --- | --- |
| macOS Intel | `age-v1.3.1-darwin-amd64.tar.gz` | `2b233301ad21ab7b1eabd9ae1198a164005fa4928fcdd745d47c39f8593209d7` |
| macOS Apple Silicon | `age-v1.3.1-darwin-arm64.tar.gz` | `01120ea2cbf0463d4c6bd767f99f3271bbed1cdc8a9aa718a76ba1fe4f01998b` |
| Windows x64 | `age-v1.3.1-windows-amd64.zip` | `c56e8ce22f7e80cb85ad946cc82d198767b056366201d3e1a2b93d865be38154` |
| Linux x64 | `age-v1.3.1-linux-amd64.tar.gz` | `bdc69c09cbdd6cf8b1f333d372a1f58247b3a33146406333e30c0f26e8f51377` |
| Linux arm64 | `age-v1.3.1-linux-arm64.tar.gz` | `c6878a324421b69e3e20b00ba17c04bc5c6dab0030cfe55bf8f68fa8d9e9093a` |

The upstream age source is BSD-3-Clause licensed. Keep the upstream `LICENSE`
file in any redistributed sidecar bundle; EnvShelf's own source remains under
the repository's license.

## Sigsum gate

Each supported archive has a corresponding upstream `.proof` asset. The
release workflow downloads it, but this repository does not vendor third-party
binaries or claim a local proof verification. Before publishing an installer,
wire the pinned release-log public key and `sigsum-verify` into the
`age-artifacts` job, verify the proof against the exact archive digest, and
fail the build on any mismatch. This explicit gate prevents a convenient
checksum-only path from being mistaken for provenance verification.
