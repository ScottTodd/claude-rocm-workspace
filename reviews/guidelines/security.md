# Security Review Guidelines

Checklist and patterns for security-focused code review. This covers secrets
and credential leaks, command injection, and other common security issues in
build infrastructure code.

## Secrets and Credential Scanning

### Why This Matters

Secrets committed to a public repository are immediately compromised. Even if
the commit is later reverted, the secret remains in Git history and in any
forks/clones created during the exposure window. Rotation is the only safe
remediation.

Build infrastructure code is especially prone to credential leaks because it
often handles:
- Package signing keys
- Repository authentication tokens
- Cloud service credentials
- Internal infrastructure URLs that reveal network topology

### What to Scan For

#### Cryptographic Keys and Keyrings

| Pattern | Risk | Examples |
|---------|------|---------|
| `*.gpg` binary files | GPG keyrings may contain private signing keys | `rocm-internal.gpg`, `signing-key.gpg` |
| `*.asc` files | ASCII-armored GPG keys (public or private) | `release-key.asc` |
| `*.pem`, `*.key` files | TLS/SSH private keys | `server.key`, `ca.pem` |
| `*.p12`, `*.pfx` files | PKCS#12 keystores (contain private keys + certs) | `signing.p12` |
| `*.keystore`, `*.jks` files | Java keystores | `release.keystore` |
| `id_rsa`, `id_ed25519` (no ext) | SSH private keys | `deploy_key`, `id_rsa` |

**How to check:** For `.gpg` binary files, inspect with:
```bash
gpg --list-packets --keyid-format long <file>
```
Look for `secret key packet` — if present, it contains a private key. Public
keyrings (`pubring.gpg`) used for package verification are generally safe to
commit, but should still be reviewed to confirm they only contain public keys.

**Naming signals:** Files or directories with `internal`, `private`, `secret`,
or `signing` in the name warrant extra scrutiny.

#### API Keys, Tokens, and Passwords

| Pattern | Risk | Examples |
|---------|------|---------|
| `PRIVATE_KEY`, `SECRET_KEY`, `API_KEY` in source | Hardcoded credentials | `AWS_SECRET_ACCESS_KEY=AKIA...` |
| Bearer tokens in scripts | Hardcoded auth tokens | `Authorization: Bearer ghp_...` |
| Passwords in config files | Plaintext credentials | `password=hunter2`, `DB_PASS=...` |
| `.env` files | Environment variable dumps | `.env`, `.env.production` |
| `credentials.json`, `service-account.json` | Cloud provider credentials | GCP service account keys |
| URLs with embedded credentials | Auth in URL | `https://user:pass@internal.amd.com/...` |

#### Internal Infrastructure Exposure

| Pattern | Risk | Examples |
|---------|------|---------|
| Internal hostnames/URLs | Reveals internal network topology | `artifactory-internal.amd.com` |
| Internal IP addresses | Network mapping | `10.x.x.x`, `172.16.x.x` |
| VPN/proxy configurations | Access path exposure | `proxy.internal.corp:8080` |
| Internal repository URLs | May require auth that leaks separately | `https://repo.internal/...` |

Internal URLs aren't secrets per se, but they reveal infrastructure details
that shouldn't be in a public repository. Mark as ⚠️ IMPORTANT unless they
also contain embedded credentials (then ❌ BLOCKING).

### Binary Files Require Extra Scrutiny

Binary files are especially dangerous because:
1. **They can't be grep'd for secrets** — a binary `.gpg` file, a `.p12`
   keystore, or a compiled binary could contain embedded credentials
2. **Diffs don't show content** — GitHub shows "Binary file added" with no
   content preview, making it easy to miss during review
3. **Git history retains them forever** — even after deletion, the blob
   persists in history

**Rule of thumb:** Any binary file added to the repository should be explicitly
justified. Ask:
- What is this file? (Inspect it with appropriate tools)
- Does it contain secrets or private material?
- Should it be generated at build time instead of committed?
- Is there a `.gitignore` entry that should have caught it?

### Severity Guide

| Finding | Severity | Rationale |
|---------|----------|-----------|
| Private key committed (GPG, SSH, TLS) | ❌ BLOCKING | Immediate credential compromise |
| API key or password in source | ❌ BLOCKING | Immediate credential compromise |
| Cloud credentials (AWS, GCP, Azure) | ❌ BLOCKING | Immediate credential compromise |
| `.env` file with real values | ❌ BLOCKING | Credential compromise |
| Unverified binary `.gpg`/`.p12`/`.key` file | ❌ BLOCKING | Must verify contents before merge |
| Internal URLs without credentials | ⚠️ IMPORTANT | Information disclosure |
| Public key committed (verified public-only) | 💡 SUGGESTION | Consider fetching at build time instead |
| `.env.example` with placeholder values | ✅ OK | Template files are fine |

### Remediation

If a secret is found in a PR:
1. **Do NOT merge the PR** — even to "fix it later"
2. **Request the author remove the secret** and force-push to eliminate it from
   branch history
3. **If already merged:** The secret must be rotated immediately. Removing it
   from future commits is insufficient — it remains in Git history
4. **Consider:** Should this file be in `.gitignore`? Should there be a
   pre-commit hook to catch this pattern?

---

## Command Injection

Build infrastructure scripts frequently compose shell commands from variables.
This is the most common security issue in this codebase.

### Patterns to Flag

| Pattern | Severity | Fix |
|---------|----------|-----|
| `system(user_input)` in C | ❌ BLOCKING | Use `execv()` family |
| `eval "$user_var"` in bash | ❌ BLOCKING | Use `declare -n` for namerefs |
| `source $config` without validation | ⚠️ IMPORTANT | Validate contents or use safer parsing |
| `curl | bash` or `wget | sh` | ❌ BLOCKING | Download, verify, then execute |

For general bash safety (`set -euo pipefail`, variable quoting, etc.), defer to
the [Bash Style Guide](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/bash_style_guide.md).
Those are correctness issues that also have security implications, but the style
guide is the primary authority.

---

## Review Checklist

When performing a security review, verify:

- [ ] No private keys committed (GPG, SSH, TLS, cloud credentials)
- [ ] All binary files justified and inspected for secrets
- [ ] No API keys, tokens, or passwords in source code
- [ ] No internal URLs with embedded credentials
- [ ] No `system()` or `eval` with unsanitized user input
- [ ] Config files validated before `source`ing
- [ ] No `[trusted=yes]` / `gpgcheck=0` without documented justification
- [ ] Temporary files use `mktemp`, not predictable paths
- [ ] Bash safety basics (quoting, `set -euo pipefail`) per [Bash Style Guide](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/bash_style_guide.md)
