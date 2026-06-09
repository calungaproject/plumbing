# npm builder image

Container image for the npm Trusted Libraries factory. Runs onboarder recipes
(`build.entrypoint.sh`, `verify.smoke.sh`) inside Konflux build tasks.

## Toolchain (v1)

All packages from **UBI 8 repositories** (AppStream/BaseOS) — no rustup or
downloads from `static.rust-lang.org`.

| Tool | Source | Pinning |
| ---- | ------ | ------- |
| UBI 8 base | `registry.access.redhat.com/ubi8/ubi` | digest in [`baseimage.lock`](./baseimage.lock) + Containerfile `ARG BASEIMAGE` |
| Node.js 20 LTS | AppStream `nodejs:20` module | stream `20` |
| Go | AppStream `golang` | distro default |
| **Rust** | AppStream **`rust-toolset`** module | **exact RPM VR** in [`rust-toolset.lock`](./rust-toolset.lock) |
| C/C++ / node-gyp | `gcc`, `python3`, `openssl-devel`, etc. | — |

### Rust pinning (RHEL 8)

Unlike `nodejs:20`, **`rust-toolset` is a rolling Application Stream** — Red Hat
rebases the single module in place. There is no `dnf module install rust-toolset:1.84`
stream selector.

**Edit [`rust-toolset.lock`](./rust-toolset.lock) for Rust** — the Containerfile and
install script read `RUST_VERSION` and `RUST_VR` from there. UBI rust-toolset RPMs
use epoch `(none)`; we pin by installing exact version-release specs, then
`dnf versionlock`.

**Edit [`baseimage.lock`](./baseimage.lock) when bumping UBI** — keep the same
digest in Containerfile `ARG BASEIMAGE` (required before `FROM`; buildkit cannot
read the lock file into that line).

To refresh the lock file from current UBI (uses `baseimage.lock` as the query image).
Requires `docker` on the host (`CONTAINER_RUNTIME=podman` also works):

```bash
./hack/update-rust-toolset-lock.sh
```

Or query manually, then update `rust-toolset.lock` by hand:

```bash
docker run --rm --platform linux/amd64 "$(grep BASEIMAGE= baseimage.lock | cut -d= -f2-)" bash -c \
  'dnf -y module install rust-toolset && rpm -q rust cargo rust-std-static rust-toolset'
```

**Caveat:** UBI CDN may eventually drop older module RPMs after a rebase. If a
pinned VR disappears, the image build fails until you bump `rust-toolset.lock` —
that is intentional.

The Python `plumbing-builder` uses **rustup** from the internet for a specific
version; this npm image deliberately uses **Red Hat RPMs only**.

## Quay

Built by Konflux component `npm-builder` under application `calunga-v2`:

```text
quay.io/redhat-user-workloads/calunga-tenant/npm-builder:<tag>
```

## Scripts

| Script | Role |
| ------ | ---- |
| `build-npm-package` | Run entrypoint + smoke for one manifest |
| `collect-npm-artifacts` | Stage `out/*.tgz` for OCI / publish steps |
| `build_scripts/install-rust-toolset.sh` | Install + versionlock pinned rust-toolset RPMs |

Publishing to Pulp and cosign are handled in **Tekton steps**, not in these scripts.

## Local build

Requires `docker` on the host (`CONTAINER_RUNTIME=podman ./hack/update-rust-toolset-lock.sh` for lock refresh only).

```bash
docker build -t npm-builder -f Containerfile .
docker run --rm npm-builder node --version
docker run --rm npm-builder go version
docker run --rm npm-builder rustc --version
docker run --rm npm-builder cargo --version
```
