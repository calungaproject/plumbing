"""faiss-cpu fromager override plugin.

Before v1.14.2, PyPI wheels were built by https://github.com/faiss-wheels/faiss-wheels
using a custom build strategy. This plugin reproduces that strategy exactly to
preserve binary compatibility with the published wheels.

From v1.14.2 onward, https://github.com/facebookresearch/faiss publishes wheels
directly via scikit-build-core; that path is handled by standard PEP-517.

Build strategy by version:

  < 1.14.2 (faiss-wheels/faiss-wheels era):
    1. cmake FAISS_ENABLE_PYTHON=OFF + FAISS_OPT_LEVEL=avx512 (Linux x86_64)
    2. cmake --install -> local prefix (libfaiss.a)
    3. cmake FAISS_ENABLE_PYTHON=ON -> _swigfaiss.so linked against libfaiss.a
    4. PEP-517 wheel from cmake output dir
    5. Retag py3-none-any -> linux_x86_64 -> auditwheel -> manylinux_2_*_x86_64

  >= 1.14.2 (facebookresearch/faiss upstream era):
    scikit-build-core pyproject.toml -> standard PEP-517, no custom cmake.

"""

import functools
import logging
import multiprocessing
import pathlib
import platform as _platform
import sys
from collections.abc import Iterable

from fromager import build_environment, context, wheels
from fromager.dependencies import default_get_build_backend_dependencies
from packaging.requirements import Requirement
from packaging.version import Version

logger = logging.getLogger(__name__)

_OPENBLAS_PREFIX = "/opt/_internal/openblas-0"
_KYAMAGU_CXXFLAGS = "-fvisibility=hidden -fdata-sections -ffunction-sections"
_SCIKIT_BUILD_CORE_MIN = Version("1.14.2")


@functools.cache
def _uses_scikit_build_core(sdist_root_dir: pathlib.Path) -> bool:
    pyproject = sdist_root_dir / "pyproject.toml"
    if not pyproject.exists():
        return False
    return "scikit_build_core" in pyproject.read_text()


def _faiss_opt_level() -> str:
    return "avx512" if _platform.machine() == "x86_64" else "generic"


def _retag_wheel(
    wheel_path: pathlib.Path,
    build_env: build_environment.BuildEnvironment,
) -> pathlib.Path:
    py_ver = f"cp{sys.version_info.major}{sys.version_info.minor}"
    machine = _platform.machine()
    logger.info(
        "faiss-cpu: retagging %s -> %s-%s-linux_%s",
        wheel_path.name, py_ver, py_ver, machine,
    )
    build_env.run(
        [
            str(build_env.python), "-m", "wheel", "tags",
            "--python-tag", py_ver,
            "--abi-tag", py_ver,
            "--platform-tag", f"linux_{machine}",
            "--remove",
            str(wheel_path),
        ],
        cwd=str(wheel_path.parent),
    )
    pattern = f"faiss_cpu-*-{py_ver}-{py_ver}-linux_{machine}.whl"
    found = list(wheel_path.parent.glob(pattern))
    if not found:
        msg = f"Retagged wheel not found in {wheel_path.parent} (pattern: {pattern})"
        raise RuntimeError(msg)
    logger.info("faiss-cpu: retagged -> %s", found[0].name)
    return found[0]


def get_build_backend_dependencies(  # noqa: PLR0913
    ctx: context.WorkContext,
    req: Requirement,
    sdist_root_dir: pathlib.Path,
    build_dir: pathlib.Path,
    extra_environ: dict,
    build_env: build_environment.BuildEnvironment,
) -> Iterable[str]:
    """Return build backend deps; skip setup.py interrogation for legacy builds."""
    if _uses_scikit_build_core(sdist_root_dir):
        logger.info("faiss-cpu: scikit-build-core detected, using default deps")
        return default_get_build_backend_dependencies(
            ctx=ctx, req=req, sdist_root_dir=sdist_root_dir,
            build_dir=build_dir, extra_environ=extra_environ, build_env=build_env,
        )
    logger.info("faiss-cpu: legacy kyamagu build, declaring numpy + wheel")
    return ["numpy", "wheel"]


def build_wheel(  # noqa: PLR0913
    ctx: context.WorkContext,
    build_env: build_environment.BuildEnvironment,
    extra_environ: dict,
    req: Requirement,
    sdist_root_dir: pathlib.Path,
    version: Version,
    build_dir: pathlib.Path,
) -> pathlib.Path:
    """Build faiss-cpu wheel following the kyamagu/faiss-wheels process."""
    if version >= _SCIKIT_BUILD_CORE_MIN:
        logger.info("faiss-cpu %s: scikit-build-core, default PEP-517", version)
        return wheels.default_build_wheel(
            ctx=ctx, build_env=build_env, extra_environ=extra_environ,
            req=req, sdist_root_dir=sdist_root_dir,
            version=version, build_dir=build_dir,
        )

    faiss_prefix = sdist_root_dir / "_faiss_install"
    cmake_build = sdist_root_dir / "_cmake_build"
    _max = ctx.settings.max_jobs
    jobs = max(1, _max if _max is not None else multiprocessing.cpu_count())
    opt_level = _faiss_opt_level()

    logger.info(
        "faiss-cpu: cmake PYTHON=OFF FAISS_OPT_LEVEL=%s -j%d", opt_level, jobs,
    )
    build_env.run(
        [
            "cmake", str(sdist_root_dir), "-B", str(cmake_build),
            "-DFAISS_ENABLE_GPU=OFF",
            "-DFAISS_ENABLE_PYTHON=OFF",
            "-DBUILD_TESTING=OFF",
            f"-DFAISS_OPT_LEVEL={opt_level}",
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_CXX_FLAGS={_KYAMAGU_CXXFLAGS}",
            f"-DCMAKE_PREFIX_PATH={_OPENBLAS_PREFIX}",
            f"-DCMAKE_INSTALL_PREFIX={faiss_prefix}",
        ],
        cwd=str(sdist_root_dir),
        extra_environ=extra_environ,
    )
    build_env.run(
        ["cmake", "--build", str(cmake_build), f"-j{jobs}"],
        extra_environ=extra_environ,
    )
    build_env.run(
        ["cmake", "--install", str(cmake_build)],
        extra_environ=extra_environ,
    )

    cmake_python_build = sdist_root_dir / "_cmake_python_build"
    logger.info(
        "faiss-cpu: cmake PYTHON=ON FAISS_OPT_LEVEL=%s -j%d", opt_level, jobs,
    )
    build_env.run(
        [
            "cmake", str(sdist_root_dir), "-B", str(cmake_python_build),
            "-DFAISS_ENABLE_GPU=OFF",
            "-DFAISS_ENABLE_PYTHON=ON",
            "-DBUILD_TESTING=OFF",
            f"-DFAISS_OPT_LEVEL={opt_level}",
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_PREFIX_PATH={faiss_prefix};{_OPENBLAS_PREFIX}",
            "-DSWIG_EXECUTABLE=/usr/local/bin/swig",
            f"-DPython_EXECUTABLE={build_env.python}",
        ],
        cwd=str(sdist_root_dir),
        extra_environ=extra_environ,
    )
    build_env.run(
        [
            "cmake", "--build", str(cmake_python_build),
            "--target", "swigfaiss", f"-j{jobs}",
        ],
        extra_environ=extra_environ,
    )

    cmake_python_dir = cmake_python_build / "faiss" / "python"
    logger.info("faiss-cpu: PEP-517 wheel from %s", cmake_python_dir)
    wheel_path = wheels.pep517_build_wheel(
        ctx=ctx,
        build_env=build_env,
        extra_environ=extra_environ,
        req=req,
        sdist_root_dir=sdist_root_dir,
        version=version,
        build_dir=cmake_python_dir,
    )
    return _retag_wheel(wheel_path, build_env)
