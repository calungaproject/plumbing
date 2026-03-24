# Library Version Updates - Corrected to Latest

**Date:** 2026-03-20
**Status:** All versions updated to latest stable releases

## Version Corrections Applied

### Phase 2: High-Priority Source Builds (Active in Containerfile)

| Library | Original Version | **Latest Version** | Status |
|---------|-----------------|-------------------|---------|
| Rust | 1.84.0 | **1.94.0** | ✅ Updated |
| libjpeg-turbo | 3.0.1 | **3.1.3** | ✅ Updated |
| libyaml | 0.2.5 | **0.2.5** | ✓ Correct |
| libxml2 | 2.12.5 | **2.13.9** | ✅ Updated |
| libxslt | 1.1.39 | **1.1.45** | ✅ Updated |

### Phase 3: Complex Numeric Libraries (Prepared, Not Yet Active)

| Library | Original Version | **Latest Version** | Status |
|---------|-----------------|-------------------|---------|
| OpenBLAS | 0.3.26 | **0.3.31** | ⚠️ Script ready, needs Containerfile update |
| libffi | 3.4.6 | **3.5.2** | ⚠️ Script ready, needs Containerfile update |

### Phase 4: Compression & Utilities (Prepared, Not Yet Active)

| Library | Original Version | **Latest Version** | Status |
|---------|-----------------|-------------------|---------|
| zlib | 1.3.1 | **1.3.2** | ⚠️ Script ready, needs Containerfile update |
| bzip2 | 1.0.8 | **1.0.8** | ✓ Correct |
| libpng | 1.6.44 | **1.6.55** | ⚠️ Script ready, needs Containerfile update |
| libtiff | 4.6.0 | **4.7.1** | ⚠️ Script ready, needs Containerfile update |

---

## Updated SHA256 Hashes

### Phase 2 (Active)

```bash
# Rust 1.94.0 (rustup-init for x86_64)
RUST_VERSION=1.94.0
RUST_HASH=4acc9acc76d5079515b46346a485974457b5a79893cfb01112423c89aeb5aa10

# libjpeg-turbo 3.1.3
LIBJPEG_TURBO_VERSION=3.1.3
LIBJPEG_TURBO_HASH=075920b826834ac4ddf97661cc73491047855859affd671d52079c6867c1c6c0

# libyaml 0.2.5 (unchanged)
LIBYAML_VERSION=0.2.5
LIBYAML_HASH=c642ae9b75fee120b2d96c712538bd2cf283228d2337df2cf2988e3c02678ef4

# libxml2 2.13.9
LIBXML2_VERSION=2.13.9
LIBXML2_HASH=a2c9ae7b770da34860050c309f903221c67830c86e4a7e760692b803df95143a

# libxslt 1.1.45
LIBXSLT_VERSION=1.1.45
LIBXSLT_HASH=9acfe68419c4d06a45c550321b3212762d92f41465062ca4ea19e632ee5d216e
```

### Phase 3 (Ready for Activation)

```bash
# OpenBLAS 0.3.31
OPENBLAS_VERSION=0.3.31
OPENBLAS_HASH=6dd2a63ac9d32643b7cc636eab57bf4e57d0ed1fff926dfbc5d3d97f2d2be3a6

# libffi 3.5.2
LIBFFI_VERSION=3.5.2
LIBFFI_HASH=f3a3082a23b37c293a4fcd1053147b371f2ff91fa7ea1b2a52e335676bac82dc
```

### Phase 4 (Ready for Activation)

```bash
# zlib 1.3.2
ZLIB_VERSION=1.3.2
ZLIB_HASH=bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16

# bzip2 1.0.8 (unchanged)
BZIP2_VERSION=1.0.8
BZIP2_HASH=ab5a03176ee106d3f0fa90e381da478ddae405918153cca248e682cd0c4a2269

# libpng 1.6.55
LIBPNG_VERSION=1.6.55
LIBPNG_HASH=d925722864837ad5ae2a82070d4b2e0603dc72af44bd457c3962298258b8e82d

# libtiff 4.7.1
LIBTIFF_VERSION=4.7.1
LIBTIFF_HASH=b92017489bdc1db3a4c97191aa4b75366673cb746de0dce5d7a749d5954681ba
```

---

## Significant Version Changes

### Major Updates

**libxml2: 2.12.5 → 2.13.9**
- Major version bump (2.12 → 2.13)
- Multiple bug fixes and improvements
- Better standards compliance
- **Action:** Test lxml thoroughly after build

**Rust: 1.84.0 → 1.94.0**
- 10 minor versions forward
- Numerous language improvements and bug fixes
- Better compilation performance
- **Action:** Test all Rust-based wheels (cryptography, ruff, pydantic-core)

**libpng: 1.6.44 → 1.6.55**
- 11 patch versions forward
- Security fixes and bug fixes
- **Action:** Test Pillow and other image libraries

### Notable Updates

**libjpeg-turbo: 3.0.1 → 3.1.3**
- Minor version + patches
- Performance improvements

**libxslt: 1.1.39 → 1.1.45**
- 6 patch versions
- Bug fixes and improvements

**OpenBLAS: 0.3.26 → 0.3.31**
- 5 patch versions
- Performance optimizations and bug fixes
- Architecture-specific improvements

**libffi: 3.4.6 → 3.5.2**
- Minor version bump + patches
- Bug fixes and portability improvements

**libtiff: 4.6.0 → 4.7.1**
- Minor version bump + patch
- Bug fixes and security improvements

---

## Download URLs

### Phase 2 (Active)

```bash
# Rust (rustup-init)
https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init

# libjpeg-turbo
https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/3.1.3/libjpeg-turbo-3.1.3.tar.gz

# libyaml
https://pyyaml.org/download/libyaml/yaml-0.2.5.tar.gz

# libxml2
https://download.gnome.org/sources/libxml2/2.13/libxml2-2.13.9.tar.xz

# libxslt
https://download.gnome.org/sources/libxslt/1.1/libxslt-1.1.45.tar.xz
```

### Phase 3 (Ready)

```bash
# OpenBLAS
https://github.com/OpenMathLib/OpenBLAS/releases/download/v0.3.31/OpenBLAS-0.3.31.tar.gz

# libffi
https://github.com/libffi/libffi/releases/download/v3.5.2/libffi-3.5.2.tar.gz
```

### Phase 4 (Ready)

```bash
# zlib
https://github.com/madler/zlib/releases/download/v1.3.2/zlib-1.3.2.tar.gz

# bzip2
https://sourceware.org/pub/bzip2/bzip2-1.0.8.tar.gz

# libpng
https://download.sourceforge.net/libpng/libpng-1.6.55.tar.xz

# libtiff
https://download.osgeo.org/libtiff/tiff-4.7.1.tar.xz
```

---

## Files Updated

### Containerfile
✅ Updated Phase 2 libraries to latest versions:
- Rust: 1.84.0 → 1.94.0
- libjpeg-turbo: 3.0.1 → 3.1.3
- libxml2: 2.12.5 → 2.13.9
- libxslt: 1.1.39 → 1.1.45

### Build Scripts
All build scripts use environment variables from Containerfile, so no script changes needed. Scripts are version-agnostic and will build whatever version is specified via environment variables.

---

## Testing Priority

Given the scope of version updates, testing should focus on:

1. **HIGH PRIORITY - Rust-based packages:**
   - cryptography (uses Rust, critical for many packages)
   - ruff (modern Python linter)
   - pydantic-core (validation library)

2. **HIGH PRIORITY - XML/HTML libraries:**
   - lxml (uses libxml2 2.13.9 with major version bump)

3. **MEDIUM PRIORITY - Image libraries:**
   - Pillow (uses libjpeg-turbo 3.1.3 and libpng 1.6.55)

4. **MEDIUM PRIORITY - YAML:**
   - PyYAML (uses libyaml, version unchanged but re-test)

---

## Next Steps for Phase 3 & 4

When ready to activate Phase 3 and 4, use these updated values in the Containerfile:

### Add to Containerfile (Phase 3)

```dockerfile
FROM build_base AS build_openblas
COPY build_scripts/build-openblas.sh /opt/_internal/build_scripts/
RUN --mount=type=bind,from=static_clang,target=/tmp/cross-compiler,ro \
    export OPENBLAS_VERSION=0.3.31 && \
    export OPENBLAS_HASH=6dd2a63ac9d32643b7cc636eab57bf4e57d0ed1fff926dfbc5d3d97f2d2be3a6 && \
    export OPENBLAS_DOWNLOAD_URL=https://github.com/OpenMathLib/OpenBLAS/releases/download && \
    /tmp/cross-compiler/entrypoint /opt/_internal/build_scripts/build-openblas.sh

FROM build_base AS build_libffi
COPY build_scripts/build-libffi.sh /opt/_internal/build_scripts/
RUN --mount=type=bind,from=static_clang,target=/tmp/cross-compiler,ro \
    export LIBFFI_VERSION=3.5.2 && \
    export LIBFFI_HASH=f3a3082a23b37c293a4fcd1053147b371f2ff91fa7ea1b2a52e335676bac82dc && \
    export LIBFFI_DOWNLOAD_URL=https://github.com/libffi/libffi/releases/download && \
    /tmp/cross-compiler/entrypoint /opt/_internal/build_scripts/build-libffi.sh
```

### Add to Containerfile (Phase 4)

```dockerfile
FROM build_base AS build_zlib
COPY build_scripts/build-zlib.sh /opt/_internal/build_scripts/
RUN --mount=type=bind,from=static_clang,target=/tmp/cross-compiler,ro \
    export ZLIB_VERSION=1.3.2 && \
    export ZLIB_HASH=bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16 && \
    export ZLIB_DOWNLOAD_URL=https://github.com/madler/zlib/releases/download && \
    /tmp/cross-compiler/entrypoint /opt/_internal/build_scripts/build-zlib.sh

FROM build_base AS build_libpng
COPY --from=build_zlib /manylinux-buildfs /
COPY build_scripts/build-libpng.sh /opt/_internal/build_scripts/
RUN --mount=type=bind,from=static_clang,target=/tmp/cross-compiler,ro \
    export LIBPNG_VERSION=1.6.55 && \
    export LIBPNG_HASH=d925722864837ad5ae2a82070d4b2e0603dc72af44bd457c3962298258b8e82d && \
    export LIBPNG_DOWNLOAD_URL=https://download.sourceforge.net/libpng && \
    /tmp/cross-compiler/entrypoint /opt/_internal/build_scripts/build-libpng.sh

FROM build_base AS build_libtiff
COPY --from=build_libjpeg_turbo /manylinux-buildfs /
COPY --from=build_zlib /manylinux-buildfs /
COPY --from=build_libpng /manylinux-buildfs /
COPY build_scripts/build-libtiff.sh /opt/_internal/build_scripts/
RUN --mount=type=bind,from=static_clang,target=/tmp/cross-compiler,ro \
    export LIBTIFF_VERSION=4.7.1 && \
    export LIBTIFF_HASH=b92017489bdc1db3a4c97191aa4b75366673cb746de0dce5d7a749d5954681ba && \
    export LIBTIFF_DOWNLOAD_URL=https://download.osgeo.org/libtiff && \
    /tmp/cross-compiler/entrypoint /opt/_internal/build_scripts/build-libtiff.sh
```

---

## Verification Checklist

- [x] Downloaded all latest stable versions
- [x] Verified SHA256 hashes for all tarballs
- [x] Updated Containerfile with Phase 2 latest versions
- [x] Documented all version changes
- [ ] Build image successfully
- [ ] Run test suite
- [ ] Test Rust-based wheels
- [ ] Test lxml (major libxml2 update)
- [ ] Test Pillow (image library updates)
- [ ] Verify manylinux compliance
