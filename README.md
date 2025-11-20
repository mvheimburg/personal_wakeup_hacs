# AksoTech CLI (ATC)

A small toolbox of developer utilities for AksoTech:

- `atc uv-index` – convenience wrapper for configuring authenticated `uv` indexes (keyring or Vault-backed)
- `git-credential-vault` – Git/VCS credential helper that pulls tokens from HashiCorp Vault

Everything is installable as a single `uv` tool.

---

## Installation

### With `uv` (recommended)

Install directly from Git:

```bash
uv tool install git+https://gitlab.com/akso_tech/tools/aksotech-cli.git
