# AlmaLinux to UBI8 + Source Build Migration - Implementation Status

**Date:** 2026-03-20
**Status:** Implementation Complete - Ready for Testing

## Overview

This document tracks the implementation of the migration from AlmaLinux 8 to UBI8, along with migrating multiple libraries from package manager installation to source compilation.

## Completed Phases

### ✅ Phase 1: UBI8 Base Migration

**Changes Made:**
- Updated base image from `amd64/almalinux:8` to `registry.access.redhat.com/ubi8/ubi@sha256:28a85f76ad1ea0a46a81a934b02fff48d75541f77777be403d48b6bb99a363ad`
- Added `--setopt install_weak_deps=0` flag to all dnf install commands in `build_utils.sh`
- Added `--setopt install_weak_deps=0` flag to final stage dnf install in Containerfile
- Created backup: `Containerfile.almalinux`

**Files Modified:**
- `Containerfile` (line 2: base image)
- `build_scripts/build_utils.sh` (line 94: dnf install flags)
- `Containerfile` (dnf install command with weak deps flag)

**Risk Level:** LOW
**Testing Required:** Build image and run `tests/run_tests.sh`

---

### ✅ Phase 2: High-Priority Source Builds

**Libraries Added:**
1. **Rust 1.84.0 + Cargo** ⚠️ CRITICAL
   - Script: `build_scripts/build-rust.sh`
   - Method: rustup installation
   - Hash: `4acc9acc76d5079515b46346a485974457b5a79893cfb01112423c89aeb5aa10` (x86_64)
   - Wrappers created for `rustc`, `cargo`, `rustup` in `/usr/local/bin`

2. **libjpeg-turbo 3.0.1**
   - Script: `build_scripts/build-libjpeg-turbo.sh`
   - Method: CMake build
   - Hash: `22429507714ae147b3acacd299e82099fce5d9f456882fc28e252e4579ba2a75`
   - Used by: Pillow, scikit-image, matplotlib

3. **libyaml 0.2.5**
   - Script: `build_scripts/build-libyaml.sh`
   - Method: autoconf
   - Hash: `c642ae9b75fee120b2d96c712538bd2cf283228d2337df2cf2988e3c02678ef4`
   - Used by: PyYAML

4. **libxml2 2.12.5**
   - Script: `build_scripts/build-libxml2.sh`
   - Method: autoconf
   - Hash: `a972796696afd38073e0f59c283c3a2f5a560b5268b4babc391b286166526b21`
   - Used by: lxml

5. **libxslt 1.1.39**
   - Script: `build_scripts/build-libxslt.sh`
   - Method: autoconf (depends on libxml2)
   - Hash: `2a20ad621148339b0759c4d4e96719362dee64c9a096dbba625ba053846349f0`
   - Used by: lxml

**Containerfile Changes:**
- Added 5 new build stages after `build_zstd`
- Updated `build_cpython312` to include these libraries
- Updated final stage to copy runtime artifacts
- Removed from dnf install: `rust`, `cargo`, `libjpeg-turbo-devel`, `libyaml-devel`, `libxml2-devel`, `libxslt-devel`

**Risk Level:** MEDIUM
**Testing Required:** Build Pillow, PyYAML, lxml wheels; verify Rust-based packages (cryptography, ruff)

---

### ✅ Phase 3: Complex Numeric Libraries (Prepared, Not Added to Containerfile)

**Libraries Prepared:**
1. **OpenBLAS 0.3.26**
   - Script: `build_scripts/build-openblas.sh`
   - Method: Makefile with DYNAMIC_ARCH
   - Hash: `4e6e4f5cb14c209262e33e6816d70221a2fe49eb69eaf0a06f065598ac602c68`
   - Used by: numpy, scipy, scikit-learn
   - Architecture-aware: HASWELL (x86_64), ARMV8 (aarch64), PRESCOTT (i686)

2. **libffi 3.4.6**
   - Script: `build_scripts/build-libffi.sh`
   - Method: autoconf
   - Hash: `b0dea9df23c863a7a50e825440f3ebffabd65df1497108e5d437747843895a4e`
   - Used by: cffi, ctypes extensions

**Status:** Build scripts created and made executable, but NOT yet added to Containerfile
**Risk Level:** MEDIUM-HIGH (architecture-specific tuning for OpenBLAS)
**Next Steps:** Add build stages to Containerfile, remove `openblas-devel` and `libffi-devel` from dnf install

---

### ✅ Phase 4: Compression & Utilities (Prepared, Not Added to Containerfile)

**Libraries Prepared:**
1. **zlib 1.3.1**
   - Script: `build_scripts/build-zlib.sh`
   - Method: configure + make
   - Hash: `9a93b2b7dfdac77ceba5a558a580e74667dd6fede4585b91eefb60f03b72df23`
   - Download: GitHub mirror (madler/zlib)

2. **bzip2 1.0.8**
   - Script: `build_scripts/build-bzip2.sh`
   - Method: Makefile (custom pkgconfig created)
   - Hash: `ab5a03176ee106d3f0fa90e381da478ddae405918153cca248e682cd0c4a2269`
   - Special: Manually creates pkgconfig file

3. **libpng 1.6.44**
   - Script: `build_scripts/build-libpng.sh`
   - Method: autoconf
   - Hash: `60c4da1d5b7f0aa8d158da48e8f8afa9773c1c8baa5d21974df61f1886b8ce8e`
   - Used by: Pillow, matplotlib

4. **libtiff 4.6.0**
   - Script: `build_scripts/build-libtiff.sh`
   - Method: CMake (tools/tests/docs disabled)
   - Hash: `e178649607d1e22b51cf361dd20a3753f244f022eefab1f2f218fc62ebaf87d2`
   - Used by: Pillow, scikit-image

**Status:** Build scripts created and made executable, but NOT yet added to Containerfile
**Risk Level:** LOW
**Next Steps:** Add build stages to Containerfile, update runtime package removal

---

## Current State Summary

### Fully Implemented (Ready to Build)
- ✅ Phase 1: UBI8 base migration
- ✅ Phase 2: Rust, libjpeg-turbo, libyaml, libxml2, libxslt

### Scripts Created (Not Yet in Containerfile)
- 🔧 Phase 3: OpenBLAS, libffi
- 🔧 Phase 4: zlib, bzip2, libpng, libtiff

### Remaining dnf Packages to Migrate
Currently still installed via dnf:
- `libffi-devel` (Phase 3)
- `openssl-devel` (already built from source in build_cpython stage)
- `openblas-devel` (Phase 3)
- `perl-IPC-Cmd` (system dependency, keep)

---

## Build Scripts Created

### Phase 2 (Active)
- ✅ `build_scripts/build-rust.sh`
- ✅ `build_scripts/build-libjpeg-turbo.sh`
- ✅ `build_scripts/build-libyaml.sh`
- ✅ `build_scripts/build-libxml2.sh`
- ✅ `build_scripts/build-libxslt.sh`

### Phase 3 (Prepared)
- ✅ `build_scripts/build-openblas.sh`
- ✅ `build_scripts/build-libffi.sh`

### Phase 4 (Prepared)
- ✅ `build_scripts/build-zlib.sh`
- ✅ `build_scripts/build-bzip2.sh`
- ✅ `build_scripts/build-libpng.sh`
- ✅ `build_scripts/build-libtiff.sh`

All scripts are executable and follow the established patterns.

---

## Testing Plan

### Phase 1 + 2 Testing (Current)

**Build Image:**
```bash
podman build -t plumbing-builder:ubi8-phase2 -f Containerfile .
```

**Run Test Suite:**
```bash
podman run --rm plumbing-builder:ubi8-phase2 /opt/_internal/tests/run_tests.sh
```

**Verify Rust Installation:**
```bash
podman run --rm plumbing-builder:ubi8-phase2 rustc --version
podman run --rm plumbing-builder:ubi8-phase2 cargo --version
```

**Test Critical Wheels:**
```bash
# Test Rust-based packages
podman run --rm -v $(pwd):/work plumbing-builder:ubi8-phase2 \
  build-wheels cryptography==41.0.7

podman run --rm -v $(pwd):/work plumbing-builder:ubi8-phase2 \
  build-wheels ruff==0.1.9

# Test image libraries
podman run --rm -v $(pwd):/work plumbing-builder:ubi8-phase2 \
  build-wheels Pillow==10.1.0

# Test YAML
podman run --rm -v $(pwd):/work plumbing-builder:ubi8-phase2 \
  build-wheels PyYAML==6.0.1

# Test XML
podman run --rm -v $(pwd):/work plumbing-builder:ubi8-phase2 \
  build-wheels lxml==5.0.0
```

**Verify manylinux Compliance:**
```bash
podman run --rm -v $(pwd)/wheels:/wheels plumbing-builder:ubi8-phase2 \
  bash -c "cd /wheels && auditwheel show *.whl"
```

### Phase 3 Testing (After Adding to Containerfile)

**Test Numeric Wheels:**
```bash
podman run --rm -v $(pwd):/work plumbing-builder:ubi8-phase3 \
  build-wheels numpy==1.26.2

podman run --rm -v $(pwd):/work plumbing-builder:ubi8-phase3 \
  build-wheels scipy==1.11.4
```

### Phase 4 Testing (After Adding to Containerfile)

**Verify Compression Libraries:**
```bash
podman run --rm plumbing-builder:ubi8-phase4 \
  bash -c "python3.12 -c 'import zlib, bz2; print(\"OK\")'"
```

---

## Known Issues / Notes

### Rust Architecture Support
- Current hash is for x86_64 only
- For multi-arch builds, need architecture-specific hashes for rustup-init
- Alternative: Download rustup-init without hash verification (not recommended)

### OpenBLAS Tuning
- Uses `DYNAMIC_ARCH=1` for runtime CPU detection
- Specific targets set for known architectures
- May need tuning for optimal performance

### zlib Download URL
- Primary zlib.net URL returned 404
- Using GitHub mirror: github.com/madler/zlib
- Consider using official source if available

### Build Time Impact
- Phase 2 adds ~5-10 minutes to build time (especially Rust)
- Phase 3 adds ~3-5 minutes (OpenBLAS is large)
- Phase 4 adds ~2-3 minutes
- Total additional build time: ~10-18 minutes

---

## Rollback Plan

If issues are encountered:

1. **Rollback to AlmaLinux:**
   ```bash
   cp Containerfile.almalinux Containerfile
   git checkout build_scripts/build_utils.sh
   ```

2. **Rollback Specific Phase:**
   - Remove build stages from Containerfile
   - Re-add dnf packages
   - Delete corresponding build scripts

3. **Git Rollback:**
   ```bash
   git diff HEAD Containerfile
   git checkout Containerfile
   ```

---

## Next Steps

1. **Test Phase 1 + 2:** Build image and run comprehensive tests
2. **Add Phase 3 to Containerfile:** If Phase 2 tests pass
3. **Add Phase 4 to Containerfile:** If Phase 3 tests pass
4. **Performance Benchmarking:** Compare build times and wheel sizes
5. **Documentation:** Update main README with migration notes
6. **CI/CD Integration:** Update build pipelines if necessary

---

## Success Criteria

- [ ] Image builds successfully on UBI8
- [ ] All Python versions compile correctly
- [ ] Test suite passes (`tests/run_tests.sh`)
- [ ] Rust-based wheels build (cryptography, ruff)
- [ ] Image libraries work (Pillow with JPEG, PNG, TIFF)
- [ ] YAML/XML libraries work (PyYAML, lxml)
- [ ] Numeric libraries work (numpy, scipy) - Phase 3
- [ ] manylinux_2_28 compliance maintained
- [ ] Image size remains reasonable
- [ ] Build time acceptable

---

## References

- UBI8 Image: `registry.access.redhat.com/ubi8/ubi@sha256:28a85f76ad1ea0a46a81a934b02fff48d75541f77777be403d48b6bb99a363ad`
- Migration Plan: See original plan document
- Example UBI9: `examples/Containerfile.ubi9`
- Example UBI10: `examples/Containerfile.ubi10`
