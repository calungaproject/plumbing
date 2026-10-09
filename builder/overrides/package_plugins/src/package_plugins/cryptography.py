"""cryptography fromager override plugin.

The index repository's ``overrides/settings/cryptography.yaml`` -- not this
repository's ``overrides/settings.yaml`` -- sets ``OPENSSL_DIR`` and
``OPENSSL_STATIC`` so the providers end up inside ``_rust.abi3.so``, the way
the official PyPI wheels are built. See ``build-openssl-static.sh`` for why the
dynamic path ships a wheel with six dead ciphers.

That default is OpenSSL 4.x, which cryptography < 47 cannot use: those
releases vendor ``openssl-sys`` < 0.9.114, whose build script aborts on
anything newer than 3. This plugin redirects them to the static 3.x prefix
and leaves 47.0.0 and later alone.

``update_extra_environ`` is used because it is the only hook that sees the
resolved version; fromager keys ``env:`` on package name and variant alone.
"""

import logging
import pathlib

from fromager import build_environment, context
from packaging.requirements import Requirement
from packaging.version import Version

logger = logging.getLogger(__name__)

# openssl-sys gained OpenSSL 4.x support in 0.9.114; cryptography 46.0.7 locks
# 0.9.110 and 47.0.0 locks 0.9.114, which makes 47 the cutoff.
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
        # Nothing set OPENSSL_DIR, so this build links the shared OpenSSL,
        # which is already 3.x and which openssl-sys accepts.
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
