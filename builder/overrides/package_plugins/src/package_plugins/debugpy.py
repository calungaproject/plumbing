"""debugpy fromager override plugin.

PyPI's debugpy wheel ships a compiled
``pydevd_attach_to_process/attach_linux_amd64.so``, built in upstream CI. The
sdist carries only its source (``linux_and_mac/attach.cpp``) and upstream's
``compile_linux.sh``, so a build from source produces a wheel without it and
``debugpy --pid <pid>`` fails outright with::

    RuntimeError: Could not find .so for attach to process.

``get_target_filename()`` in ``add_code_to_python_process.py`` looks for the
``.so`` as a sibling of itself, so compiling it into the unpacked source before
the wheel is built is enough: debugpy's own ``setup.py`` already collects the
vendored tree off disk and whitelists ``_linux_amd64.so`` for
``linux-x86_64``, which means no patch and no setup.py change are needed.
"""

import logging
import pathlib
import platform

from fromager import context, external_commands, sources
from packaging.requirements import Requirement
from packaging.version import Version

logger = logging.getLogger(__name__)

# Paths relative to the unpacked sdist root.
_ATTACH_DIR = pathlib.Path(
    "src/debugpy/_vendored/pydevd/pydevd_attach_to_process"
)
_COMPILE_SCRIPT = _ATTACH_DIR / "linux_and_mac" / "compile_linux.sh"
_SO_NAME = "attach_linux_amd64.so"


def _compile_attach_so(source_root_dir: pathlib.Path) -> None:
    """Build attach_linux_amd64.so in place, using upstream's own compile line."""
    machine = platform.machine()
    if machine != "x86_64":
        # Upstream ships no attach .so for any other Linux architecture --
        # their own wheel has only the amd64 one -- so there is nothing to
        # match and compile_linux.sh would name the output attach_linux_.so.
        logger.info(
            "debugpy: architecture is %s, not x86_64; upstream ships no "
            "attach .so for it, skipping",
            machine,
        )
        return

    script = source_root_dir / _COMPILE_SCRIPT
    target = source_root_dir / _ATTACH_DIR / _SO_NAME
    if not script.exists():
        raise FileNotFoundError(
            f"debugpy: expected upstream compile script at {script}"
        )

    # The script has CRLF line endings in the sdist, so `bash compile_linux.sh`
    # dies with "set: - : invalid option". Strip the carriage returns and feed
    # the body to bash instead of rewriting the file, which would leave our
    # wheel's copy of the script differing from PyPI's. $0 is set to the real
    # script path so its own `SRC="$(dirname "$0")/.."` still resolves.
    body = script.read_text().replace("\r\n", "\n")
    external_commands.run(
        ["bash", "-c", body, str(script)],
        cwd=str(source_root_dir),
    )

    if not target.exists():
        raise FileNotFoundError(
            f"debugpy: {script.name} exited cleanly but did not produce {target}"
        )
    logger.info(
        "debugpy: compiled %s (%d bytes)", target.name, target.stat().st_size
    )


def prepare_source(
    ctx: context.WorkContext,
    req: Requirement,
    source_filename: pathlib.Path,
    version: Version,
) -> tuple[pathlib.Path, bool]:
    """Unpack the sdist as usual, then compile the attach-to-process helper."""
    source_root_dir, is_new = sources.default_prepare_source(
        ctx=ctx,
        req=req,
        source_filename=source_filename,
        version=version,
    )
    # Unconditional, not just when is_new: a reused source tree that somehow
    # lacks the .so would otherwise build a wheel without it, which is the
    # failure this plugin exists to prevent. The compile takes under a second.
    _compile_attach_so(source_root_dir)
    return source_root_dir, is_new
