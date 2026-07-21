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
| **C/C++ (node-gyp)** | **gcc-toolset-14** (CodeReady Builder) | toolset version in [`gcc-toolset.lock`](./gcc-toolset.lock); C++20 on UBI 8 glibc |
| **SBOM** | **Syft** from `registry.redhat.io/rh-syft-tech-preview/syft-rhel9` (digest-pinned via `SYFT_IMAGE`, same as [tssc-dev-multi-ci](https://github.com/redhat-appstudio/tssc-dev-multi-ci/blob/main/Dockerfile)) | SPDX JSON → `package/sboms/redhat.spdx.json` (same name as Python wheels) |
| **Rust** | AppStream **`rust-toolset`** module | **exact RPM VR** in [`rust-toolset.lock`](./rust-toolset.lock) |
| node-gyp deps | `python3`, `openssl-devel`, stock `make`, etc. | stock gcc remains installed; **`CC`/`CXX`** point at toolset |

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

**Edit [`gcc-toolset.lock`](./gcc-toolset.lock) when bumping gcc-toolset** — set
`GCC_TOOLSET` and update Containerfile `ENV` paths
(`/opt/rh/gcc-toolset-${GCC_TOOLSET}/...`).

To refresh the rust lock file from current UBI (uses `baseimage.lock` as the query image).
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

The Python **`plumbing-builder`** uses the same **gcc-toolset-14** pattern for manylinux
wheels. npm-builder reuses it so Tier C addons (e.g. **better-sqlite3 ≥ 11.2**) can
compile with **C++20** without moving the base image to UBI 9. For Rust, **`plumbing-builder`**
uses **rustup** from the internet; this npm image deliberately uses **Red Hat RPMs only**.

## Quay

Built by Konflux component `npm-builder` under application `calunga-v2`:

```text
quay.io/redhat-user-workloads/calunga-tenant/npm-builder:<tag>
```

### `registry.redhat.io` pull secret (required for Syft)

The Containerfile `COPY --from`s Syft from `registry.redhat.io`, same pattern as
[tssc-dev-multi-ci](https://github.com/redhat-appstudio/tssc-dev-multi-ci/blob/main/Dockerfile).
That registry is authenticated — without a pull secret, buildah fails with
`invalid username/password` / `Please login to the Red Hat Registry`.

1. Create a [registry service account](https://access.redhat.com/terms-based-registry/accounts).
2. In Konflux (`calunga-tenant` → Secrets), add an **Image pull secret** for
   `registry.redhat.io` with those credentials.
3. Link it to component **`npm-builder`** (or all components) so it attaches to
   `build-pipeline-npm-builder`. No PipelineRun YAML change is needed.

Local builds: `podman login registry.redhat.io` before `docker`/`podman` build.

## Scripts

| Script | Role |
| ------ | ---- |
| `build-npm-package` | Run entrypoint + smoke for one manifest |
| `build-npm-packages` | Build multiple package dirs (Tekton `PACKAGES` args) |
| `collect-npm-artifacts` | Stage `out/*.tgz` for OCI push / optional Pulp publish |
| `generate-npm-sbom` | Syft → SPDX JSON embedded as `package/sboms/redhat.spdx.json` (Python parity) |
| `npm-publish-pulp` | Optional Pulp npm publish (deferred; Tekton step only) |
| `build_scripts/install-gcc-toolset.sh` | Install gcc-toolset from `gcc-toolset.lock` |
| `build_scripts/install-rust-toolset.sh` | Install + versionlock pinned rust-toolset RPMs |
| `hack/update-rust-toolset-lock.sh` | Refresh `rust-toolset.lock` from UBI |

Publishing to Quay (OCI artifact) and optional Pulp are handled in **Tekton steps**.
Package attestations are **release-phase** (like Python `rh-sign-python-wheels`); see
`utils/scripts/generate-and-sign-npm-attestations`.

## Local build

Requires `docker` on the host (`CONTAINER_RUNTIME=podman ./hack/update-rust-toolset-lock.sh` for lock refresh only).

```bash
docker build -t npm-builder -f Containerfile .
docker run --rm npm-builder node --version
docker run --rm npm-builder go version
docker run --rm npm-builder g++ --version
docker run --rm npm-builder bash -c 'echo | g++ -std=c++20 -x c++ - -o /dev/null -'
docker run --rm npm-builder rustc --version
docker run --rm npm-builder cargo --version
docker run --rm npm-builder syft version
```
