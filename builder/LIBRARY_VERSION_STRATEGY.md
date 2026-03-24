# Strategy Options: Keeping Source-Built Library Versions Up to Date

## Problem

The Containerfile and build scripts hardcode versions and SHA256 hashes for all source-built libraries (libjpeg-turbo, libyaml, libxml2, libxslt, libffi, OpenBLAS, Rust, etc.). There is no mechanism to detect when new upstream releases are available, which means we can fall behind on security patches and bug fixes.

## Options

### 1. Automated update script + CI schedule

A script that queries upstream release APIs (GitHub releases API, download pages), compares against current pinned versions, and opens a PR with updated versions and SHA256 hashes. Run on a weekly cron in CI.

**Pros:**
- Preserves reproducibility (pinned versions + hashes stay in the repo)
- Catches new releases automatically
- Full control over update logic per library

**Cons:**
- Custom code to write and maintain
- Each library has a different upstream source (GitHub, GNU mirrors, etc.)

### 2. Renovate/Dependabot with custom datasources

Renovate supports custom regex managers that can match version patterns in arbitrary files. Define a regex that matches e.g. `export LIBFFI_VERSION=3.5.2` and configure Renovate to check GitHub releases for `libffi/libffi`. PRs are opened automatically.

**Pros:**
- Less custom code
- Well-tested update infrastructure
- Handles PR creation, changelogs, grouping

**Cons:**
- Requires Renovate configuration per library
- SHA256 hash updates may need a custom post-upgrade script
- Some libraries (GNU mirrors, pyyaml.org) may not have supported datasources

### 3. Centralize versions into a single file

Extract all versions and hashes from the Containerfile and build scripts into a single file (e.g. `library-versions.env` or `library-versions.yaml`). The Containerfile and scripts read from it.

**Pros:**
- Single place to review and update all versions
- Makes any automation (options 1 or 2) simpler to implement
- Easier to audit in PRs

**Cons:**
- Doesn't solve the "check for updates" problem on its own
- Requires plumbing to pass values from the versions file into the Containerfile

### 4. Resolve latest at build time

Query upstream for the latest release during `podman build`. Download whatever is newest.

**Pros:**
- Always builds with latest versions

**Cons:**
- Sacrifices reproducibility (same Containerfile produces different images on different days)
- Loses SHA256 verification (security risk)
- Builds can break without any code change

**Not recommended.**

## Recommendation

Combine options 3 and 1: centralize versions into a single file first, then add an automated checker script on a CI schedule. This gives reproducibility, easy auditability, and automatic notifications when updates are available.

## Current Libraries and Upstream Sources

| Library | Version | Upstream |
|---------|---------|----------|
| Rust | 1.94.0 | https://github.com/rust-lang/rust/releases |
| libjpeg-turbo | 3.1.3 | https://github.com/libjpeg-turbo/libjpeg-turbo/releases |
| libyaml | 0.2.5 | https://github.com/yaml/libyaml/releases |
| libxml2 | 2.15.1 | https://github.com/GNOME/libxml2/releases |
| libxslt | 1.1.45 | https://github.com/GNOME/libxslt/releases |
| libffi | 3.5.2 | https://github.com/libffi/libffi/releases |
| OpenBLAS | 0.3.31 | https://github.com/OpenMathLib/OpenBLAS/releases |
| OpenSSL | 3.5.4 | https://github.com/openssl/openssl/releases |
| curl | 8.17.0 | https://github.com/curl/curl/releases |
| Git | 2.51.2 | https://github.com/git/git/tags |
| SQLite | 3.51.0 | https://www.sqlite.org/changes.html |
| Tcl/Tk | 8.6.17 | https://sourceforge.net/projects/tcl/files/ |
| mpdecimal | 4.0.1 | https://www.bytereef.org/mpdecimal/ |
| zstd | 1.5.7 | https://github.com/facebook/zstd/releases |
