# OpenSSL Source Build: Investigation and Fix

## Problem

After migrating the builder base image from AlmaLinux 8 to UBI8, packages
requiring OpenSSL 3.x headers (notably **cmake** and **duckdb**) failed to
build. The build errors indicated that the system OpenSSL 1.1.1k headers were
being found instead of our source-built OpenSSL 3.5.4.

cmake's bundled curl produced:
```
#error "OpenSSL 3.0.0 or later required"
```

duckdb failed with similar version-mismatch errors during its httpfs extension
build.

## Root Cause

Two separate issues combined to prevent OpenSSL 3.5.4 from being available in
the final image:

### 1. build-openssl.sh had a version skip check (removed)

The upstream `build-openssl.sh` contained a version comparison that skipped
the source build if the system OpenSSL met a minimum version threshold
(`OPENSSL_MIN_VERSION=1.1.1`). Since UBI8 ships OpenSSL 1.1.1k, the check
passed and the entire source build was skipped.

**Fix**: Removed the version check entirely. We always build OpenSSL from
source to ensure the latest version (3.5.4) is available.

### 2. build-cpython.sh deletes OpenSSL headers after use

`build-cpython.sh` (line 87) explicitly removes OpenSSL headers, pkgconfig
files, and binaries after compiling CPython:

```bash
if [ "${OPENSSL_PREFIX}" != "" ]; then
    rm -rf "${OPENSSL_PREFIX:?}/bin" "${OPENSSL_PREFIX}/include" \
           "${OPENSSL_PREFIX}/lib/pkgconfig" "${OPENSSL_PREFIX}/lib/*.so"
fi
```

This is upstream behavior — once CPython is compiled, the build stage only
retains the `.so` runtime libraries. The Containerfile was copying OpenSSL
from the `build_cpython312` stage (post-cleanup), so only `.so` files made it
to the final image. Headers and pkgconfig files were lost.

**Fix**: Changed the Containerfile to copy OpenSSL from the `build_cpython`
stage (pre-cleanup) instead of `build_cpython312`:

```dockerfile
RUN    --mount=type=bind,target=/build_cpython312,from=build_cpython312 \
    --mount=type=bind,target=/build_cpython_base,from=build_cpython \
    mkdir -p /opt/_internal && \
    cp -rf /build_cpython*/opt/_internal/cpython* /opt/_internal/ && \
    if test -n "$(find /build_cpython_base/opt/_internal -maxdepth 1 -name 'openssl*' -print -quit)"; then \
        cp -rf /build_cpython_base/opt/_internal/openssl* /opt/_internal/; \
    fi && \
    manylinux-entrypoint /opt/_internal/build_scripts/finalize.sh pp311-pypy311_pp73
```

### 3. System openssl-devel provided conflicting old headers

The `openssl-devel` package (installed via dnf) placed OpenSSL 1.1.1k headers
at `/usr/include/openssl/`, which took precedence over our source-built
headers for some build systems.

**Fix**: Removed `openssl-devel` from the dnf install in the Containerfile.
The system `openssl` and `openssl-libs` packages are retained because many
system tools (curl, krb5, dnf, libssh) depend on them at runtime. These do
not conflict with builds since they only provide the runtime `.so` files, not
development headers.

### 4. Source-built OpenSSL symlinked into system paths

Added a Containerfile step to symlink our OpenSSL 3.5.4 files into standard
paths so all build systems find them:

```dockerfile
RUN set -e && \
    for dir in /opt/_internal/openssl*/include/*; do \
        [ -d "$dir" ] && ln -sf "$dir" /usr/local/include/; \
    done; \
    for lib in /opt/_internal/openssl*/lib/lib*.so*; do \
        [ -f "$lib" ] && ln -sf "$lib" /usr/local/lib/; \
    done; \
    for pc in /opt/_internal/openssl*/lib/pkgconfig/*.pc; do \
        [ -f "$pc" ] && ln -sf "$pc" /usr/local/lib/pkgconfig/; \
    done; \
    ldconfig
```

## Verification

After applying all fixes:

```
$ pkg-config --modversion openssl
3.5.4

$ ls /usr/local/include/openssl/opensslv.h
/usr/local/include/openssl/opensslv.h   (OPENSSL_VERSION_STR "3.5.4")

$ ls /usr/include/openssl/
ls: cannot access '/usr/include/openssl/': No such file or directory
```

Both previously-failing packages now build successfully:
- **cmake 4.3.1** — `cmake-4.3.1-0-py3-none-manylinux_2_28_x86_64.whl`
- **duckdb 1.5.1** — `duckdb-1.5.1-0-cp312-cp312-manylinux_2_26_x86_64.manylinux_2_28_x86_64.whl`

## Files Changed

| File | Change |
|------|--------|
| `build_scripts/build-openssl.sh` | Removed `OPENSSL_MIN_VERSION` check that skipped source build |
| `Containerfile` (line 282) | Added `build_cpython` bind mount, copy OpenSSL from there instead of `build_cpython312` |
| `Containerfile` (line 288-299) | Added symlink step for headers, libs, and pkgconfig into `/usr/local/` |
| `Containerfile` (line 308-313) | Removed `openssl-devel` from dnf install |

---

## Appendix: Conditional Build Logic in Other Library Scripts

Several build scripts from upstream manylinux contain conditional logic that
decides whether to build from source or use system packages. These conditions
are based on the target policy (`manylinux2014`, `manylinux_2_28`,
`musllinux`), the target architecture, or package availability. Below is a
survey of all such conditions.

### build-tcltk.sh — Skips source build entirely

```bash
# exit 0 on line 28 — never reaches the source build code
```

**Condition**: Unconditional `exit 0` (effectively policy-based).
**Rationale**: manylinux_2_28 (RHEL 8+) ships Tcl/Tk 8.6, which is
sufficient. Building from source was only needed for manylinux2014 (CentOS 7)
which had Tcl/Tk 8.5. Since we only target manylinux_2_28, the source build
is skipped.
**Impact**: None — system Tcl/Tk 8.6 works fine.

### build-curl.sh — Conditional based on package availability

```bash
if dnf list available curl-devel &>/dev/null; then
    echo "skipping installation of ${CURL_ROOT} - using system curl-devel"
    exit 0
fi
```

**Condition**: Checks if `curl-devel` is available via dnf.
**Rationale**: On UBI8, `curl-devel` is not available in the default
repositories, so curl is always built from source. On AlmaLinux or full RHEL,
`curl-devel` would be available and the source build would be skipped.
**Impact**: On our UBI8 image, curl is always built from source. No action
needed.

### build-openssl.sh — OS-specific package management (no skip)

```bash
if [ "${OS_ID_LIKE}" = "rhel" ]; then
    manylinux_pkg_remove openssl-devel
    manylinux_pkg_install perl-core
elif [ "${OS_ID_LIKE}" = "debian" ]; then
    manylinux_pkg_remove libssl-dev
elif [ "${OS_ID_LIKE}" = "alpine" ]; then
    manylinux_pkg_remove openssl-dev
fi
```

**Condition**: OS family detection to remove conflicting system dev packages
before building from source.
**Impact**: Always builds from source. The conditional only affects which
system packages to remove. No skip risk.

### build-git.sh — Policy and architecture adaptations

```bash
if [ "${BASE_POLICY}" == "musllinux" ]; then
    export NO_REGEX=NeedsStartEnd
fi
if [ "${AUDITWHEEL_POLICY}" == "manylinux2014" ]; then
    export NO_UNCOMPRESS2=1
    CSPRNG_METHOD=urandom
    echo "" > /usr/include/ctype.h
else
    CSPRNG_METHOD=getrandom
fi
```

**Condition**: Adjusts build flags for musllinux and manylinux2014.
**Impact**: Always builds from source. Conditionals only affect build
configuration, not whether the build happens.

### build-cpython.sh — Policy and architecture adaptations

```bash
if [ "${AUDITWHEEL_POLICY}" == "manylinux2014" ]; then
    export TCLTK_LIBS="-L/usr/local/lib -ltk8.6 -ltcl8.6"
fi
if [ "${BASE_POLICY}_${AUDITWHEEL_ARCH}" == "manylinux_armv7l" ]; then
    CONFIGURE_ARGS+=(--build=armv7l-unknown-linux-gnueabihf)
fi
```

**Condition**: Sets Tcl/Tk link flags for manylinux2014, cross-compilation
args for ARM architectures.
**Impact**: Always builds from source. No skip risk.

### build-sqlite3.sh — Conditional pkgconfig exposure

```bash
if [ "${AUDITWHEEL_POLICY}" == "manylinux2014" ] || \
   [ "${AUDITWHEEL_POLICY}" == "manylinux_2_28" ] || \
   [ "${AUDITWHEEL_POLICY}" == "musllinux_1_2" ]; then
    mkdir -p /manylinux-rootfs/usr/local/lib/pkgconfig/
    ln -s ${PREFIX}/lib/pkgconfig/sqlite3.pc /manylinux-rootfs/usr/local/lib/pkgconfig/sqlite3.pc
fi
```

**Condition**: Exposes the custom SQLite3 pkgconfig to the runtime image for
specific policies.
**Impact**: Always builds from source. The conditional only controls whether
pkgconfig is available at runtime (it is for our manylinux_2_28 policy).

### build-rust.sh, build-openblas.sh — Architecture selection only

These scripts contain `AUDITWHEEL_ARCH` conditionals to select the correct
target triple or CPU target for the architecture being built. They always
build from source.

### Summary

| Script | Skip Condition | Builds from source on UBI8? |
|--------|---------------|----------------------------|
| `build-openssl.sh` | None (fixed) | Yes, always |
| `build-tcltk.sh` | Unconditional `exit 0` | No — uses system Tcl/Tk 8.6 |
| `build-curl.sh` | `dnf list available curl-devel` | Yes — curl-devel unavailable on UBI8 |
| `build-git.sh` | None (config flags only) | Yes, always |
| `build-cpython.sh` | None (config flags only) | Yes, always |
| `build-sqlite3.sh` | None (pkgconfig exposure only) | Yes, always |
| `build-mpdecimal.sh` | None | Yes, always |
| `build-zstd.sh` | None | Yes, always |
| `build-rust.sh` | None (arch selection only) | Yes, always |
| `build-openblas.sh` | None (arch selection only) | Yes, always |
| `build-libjpeg-turbo.sh` | None | Yes, always |
| `build-libyaml.sh` | None | Yes, always |
| `build-libxml2.sh` | None | Yes, always |
| `build-libxslt.sh` | None | Yes, always |
| `build-libffi.sh` | None | Yes, always |

Only **build-tcltk.sh** and **build-curl.sh** have conditions that can skip
the source build. In both cases the behavior is correct for our UBI8 +
manylinux_2_28 target.
