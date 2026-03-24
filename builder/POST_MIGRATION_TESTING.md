# Post-Migration Testing and Fixes

**Date**: 2026-03-20
**Image**: `plumbing-builder:ubi8-latest`

## Full Package Test Results

Tested all 300 packages from `packages.txt` using `build-wheels` in the UBI8 image.

**Results**: 275/300 packages produced fully correct wheels (91.7%). Of the 25 failures, 7 were caused by the libyaml linking issue (Bug 4), 3 were genuine failures, and 15 were upstream issues (OpenTelemetry pre-release versions).

### Actual failures (3 packages)

1. **pillow** - Could not find JPEG library. Root cause: pkgconfig symlink bug in `build-libjpeg-turbo.sh`. Fixed (see below).
2. **html5lib** - `ModuleNotFoundError: No module named 'pkg_resources'`. html5lib 1.1 uses legacy setuptools patterns that require `pkg_resources`, which is not installed in modern pip/setuptools. This is an upstream package issue, not a builder issue.
3. **opentelemetry-\*** (15 packages) - All fail with "ignoring pre-release versions". Every OpenTelemetry instrumentation/SDK package on PyPI only has beta versions (e.g. 0.61b0). fromager ignores pre-release versions by default. Not a builder issue.

### Silent degradation (7 packages)

**pyyaml, awscli, bandit, dask, flask-appbuilder, pulp-cli, yamllint** — All 7 packages depend on PyYAML, which built without its C extension (`_yaml`) due to the libyaml linking issue (see Bug 4 below). The builds exited 0 but produced degraded wheels containing a pure-Python PyYAML fallback. These were initially misclassified as "false positives" caused by a test script exit code capture bug, but re-testing confirmed all 7 were affected by the same root cause.

## Bugs Found and Fixed

### Bug 1: pkgconfig symlink creation in build-libjpeg-turbo.sh

**Symptom**: Pillow fails with `RequiredDependencyException: jpeg`

**Root cause**: The script used a loop over `${PREFIX}/lib/pkgconfig/*.pc` to create symlinks, but this path doesn't exist during the build — files are at `/manylinux-buildfs${PREFIX}/lib/pkgconfig/`. The glob matched nothing, so no symlinks were created.

**Fix**: Replace the loop with unconditional `ln -s` commands, matching the working pattern in `build-libyaml.sh`.

### Bug 2: Same pkgconfig symlink bug in build-openblas.sh

**Symptom**: openblas.pc not accessible via pkg-config (numpy happened to build anyway via fallback detection).

**Root cause**: Conditional check `if [ -f "${PREFIX}/lib/pkgconfig/openblas.pc" ]` checked the wrong path (host filesystem instead of `/manylinux-buildfs`).

**Fix**: Remove the conditional, create the symlink unconditionally.

### Bug 3: Source-built libraries not registered with ldconfig

**Symptom**: After fixing the pkgconfig bug, pillow compiled successfully but auditwheel repair failed with `Cannot repair wheel, because required library "libjpeg.so.62" could not be located`.

**Root cause**: The final Containerfile stage copied library files from `/manylinux-rootfs` but never ran `ldconfig`, so the runtime linker didn't know about libraries in `/opt/_internal/*/lib/`. The paths also weren't listed in `/etc/ld.so.conf.d/`.

**Fix**: Added library paths to `/etc/ld.so.conf.d/00-manylinux.conf` and ran `ldconfig`. Later improved to use dynamic discovery (`find /opt/_internal -name '*.so' -printf '%h\n' | sort -u`) instead of hardcoded paths.

### Bug 4: PyYAML built without C extension (silent degradation)

**Symptom**: auditwheel warning: `This does not look like a platform wheel, no ELF executable or shared library file found in the wheel archive`. The wheel contained only pure-Python `.py` files, no `_yaml.cpython-312-x86_64-linux-gnu.so`.

**Root cause**: PyYAML's `setup.py` does not use pkg-config. It searches for `yaml.h` in standard include paths (`/usr/include`, `/usr/local/include`). Our source-built libyaml installed headers to `/opt/_internal/libyaml-0.2/include/`, which is not in the standard search path. Without finding the headers, PyYAML silently falls back to a pure-Python build.

**Fix**: Added a `RUN` block in the final Containerfile stage that creates symlinks from `/opt/_internal/*/include/*` to `/usr/local/include/` and `/opt/_internal/*/lib/lib*.so` to `/usr/local/lib/`. This makes all source-built library headers and shared libraries discoverable by build systems that don't use pkg-config.

**Verification**: After fix, pyyaml wheel contains `_yaml.cpython-312-x86_64-linux-gnu.so` (~2.1MB) and auditwheel successfully bundles `libyaml-0.so.2`.

## Improvements Applied

1. **Dynamic library path discovery** — Replaced hardcoded version-specific paths in `ld.so.conf.d` with `find`-based discovery. Prevents breakage when library versions are bumped.
2. **Merged buildfs stage** — Consolidated 12 COPY commands into 2 using a `merged_buildfs` intermediate stage based on `scratch`. Reduces layer count.
3. **Test coverage for source-built libraries** — Added pkg-config and ldconfig verification for all 6 source-built libraries to `tests/run_tests.sh`.

## Key Lesson

When adding source-built libraries to a manylinux container image, four integration points must all work:

1. **pkg-config** — Symlink the `.pc` file to `/usr/local/lib/pkgconfig/` so build systems can find headers and linker flags.
2. **ldconfig** — Register the library directory in `/etc/ld.so.conf.d/` and run `ldconfig` so the runtime linker and auditwheel can find `.so` files.
3. **buildfs vs rootfs** — Copy headers and pkgconfig to buildfs (for compilation), shared libraries to rootfs (for runtime). Both must be present in the final image for wheel building.
4. **Standard path symlinks** — Some build systems (e.g. PyYAML's `setup.py`) don't use pkg-config and instead look for headers/libraries in `/usr/local/include` and `/usr/local/lib`. Symlinks from these standard paths to the actual install locations are needed.

Missing any one of these causes failures at different stages (configure, compile, auditwheel repair) with different error messages, making debugging non-obvious. Point 4 is particularly insidious because the build may succeed silently without the C extension.
