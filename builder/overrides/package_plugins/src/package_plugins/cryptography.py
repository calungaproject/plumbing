"""cryptography fromager override plugin.

The index repository's ``overrides/settings/cryptography.yaml`` -- not this
repository's ``overrides/settings.yaml`` -- sets ``OPENSSL_DIR`` and
``OPENSSL_STATIC`` so the providers end up inside ``_rust.abi3.so``, the way
the official PyPI wheels are built. See ``build-openssl-static.sh`` for why the
dynamic path ships a wheel with six dead ciphers.

That default is OpenSSL 4.x, which cryptography < 47 cannot use. Those releases
vendor ``openssl-sys`` < 0.9.114, whose build script rejects anything newer
than 3 and aborts::

    thread 'main' panicked at .../openssl-sys/build/main.rs:472:5:
    This crate is only compatible with OpenSSL (version 1.0.2 through 1.1.1,
    or 3), or LibreSSL 3.5 through 4.2.x, but a different version of OpenSSL
    was found. The build is now aborting due to this version mismatch.

so the wheel never builds. This plugin redirects those releases to the static
3.x prefix and leaves everything from 47.0.0 on alone.

Why a plugin and not settings: fromager keys ``env:`` on package name and
variant only -- there is no version-conditional form in any release from 0.81.0
through 0.98.0 -- and the only version-keyed construct is the patch directory.
``update_extra_environ`` is the one hook that sees the resolved version, and
``packagesettings/_hooks.py`` is byte-identical across that whole range.

This is not a hypothetical. Any install requirement in the graph can pin an
older cryptography: ``snowflake-connector-python==3.15.0`` resolves
``pyOpenSSL<26`` -> 25.3.0 -> ``cryptography<47`` and dies here. The index
serves no wheel in ``[45.0.7, 47)`` to download instead of building, so the
wheel cache cannot route around it, and a constraints file pinning a version in
that range needs this redirect to make that version buildable at all.
"""

import logging
import pathlib

from fromager import build_environment, context
from packaging.requirements import Requirement
from packaging.version import Version

logger = logging.getLogger(__name__)

# openssl-sys gained OpenSSL 4.x support in 0.9.114. cryptography 46.0.7 locks
# 0.9.110 and 47.0.0 locks 0.9.114, which makes 47 the exact cutoff -- measured
# from the Cargo.lock in each sdist, not inferred from the release notes.
_FIRST_OPENSSL4_CAPABLE = Version("47")

# Laid down by build-openssl-static.sh as a symlink to the real
# static-openssl-<major>.<minor> prefix, so this does not track the minor.
_STATIC_OPENSSL_3 = "/opt/_internal/static-openssl-3"


def update_extra_environ(
    *,
    ctx: context.WorkContext,
    req: Requirement,
    version: Version | None,
    sdist_root_dir: pathlib.Path,
    extra_environ: dict[str, str],
    build_env: build_environment.BuildEnvironment,
) -> None:
    """Point cryptography < 47 at the static OpenSSL 3.x prefix."""
    if version is None:
        # fromager calls this without a version in some paths. Leaving the
        # settings value alone keeps the current behaviour.
        logger.debug("cryptography: no version available, leaving OPENSSL_DIR as set")
        return

    if version >= _FIRST_OPENSSL4_CAPABLE:
        return

    if "OPENSSL_DIR" not in extra_environ:
        # Nothing set OPENSSL_DIR, so this build is not on the static path at
        # all -- it links the shared OpenSSL, which is already 3.x and which
        # openssl-sys accepts. Setting OPENSSL_DIR here would switch it to a
        # static link as a side effect, which is a bigger change than this
        # plugin is for.
        logger.warning(
            "cryptography %s: OPENSSL_DIR is not set, so the index's "
            "overrides/settings/cryptography.yaml is not in effect; leaving "
            "the build on the shared OpenSSL instead of %s",
            version,
            _STATIC_OPENSSL_3,
        )
        return

    previous = extra_environ["OPENSSL_DIR"]
    if previous == _STATIC_OPENSSL_3:
        return

    extra_environ["OPENSSL_DIR"] = _STATIC_OPENSSL_3
    logger.info(
        "cryptography %s: < %s vendors openssl-sys that rejects OpenSSL 4, "
        "redirecting OPENSSL_DIR from %s to %s",
        version,
        _FIRST_OPENSSL4_CAPABLE,
        previous,
        _STATIC_OPENSSL_3,
    )
