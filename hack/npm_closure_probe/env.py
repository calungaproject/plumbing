"""Probe environment: PATH, Pulp/Quay defaults, image ref helpers."""

from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

_NPM_NAME_RE = re.compile(
    r"^(?:@[a-z0-9-~][a-z0-9-._~]*/)?[a-z0-9-~][a-z0-9-._~]*$",
    re.IGNORECASE,
)
_NPM_VERSION_RE = re.compile(r"^[0-9A-Za-z.+~-]+$")


def validate_npm_name(name: str) -> str:
    if not name or not _NPM_NAME_RE.match(name):
        sys.exit(f"ERROR: invalid npm package name: {name!r}")
    return name


def validate_npm_version(version: str) -> str:
    if not version or not _NPM_VERSION_RE.match(version):
        sys.exit(f"ERROR: invalid npm version: {version!r}")
    return version


def _validate_executable_path(path: str | Path) -> Path:
    """Ensure path is a single executable file (argv-safe, no shell)."""
    resolved = Path(path).expanduser().resolve()
    if "\0" in str(resolved) or "\n" in str(resolved):
        sys.exit(f"ERROR: invalid executable path: {path!r}")
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        sys.exit(f"ERROR: executable not found: {resolved}")
    return resolved


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _strip_image_base(prefix: str) -> str:
    base = prefix.split("@", 1)[0]
    if ":" in base.rsplit("/", 1)[-1]:
        base = base.rsplit(":", 1)[0]
    return base


def compliance_tag(name: str, version: str) -> str:
    if name.startswith("@"):
        return f"{name.lstrip('@').replace('/', '-')}-{version}"
    return f"{name}-{version}"


@dataclass
class ProbeEnv:
    root: Path = field(default_factory=repo_root)
    pulp_base_url: str = "https://packages.redhat.com"
    pulp_api_root: str = "/api/"
    pulp_domain: str = "public-trusted-libraries"
    pulp_repository: str = "npm-registry"
    tl_npm_registry_url: str = (
        "https://packages.redhat.com/api/pulp-content/public-trusted-libraries/javascript"
    )
    upstream_registry: str = "https://registry.npmjs.org"
    compliance_image_prefix: str = ""
    snapshot_image_prefix: str = ""
    closure_index_image: str = ""
    pulp_username: str = ""
    pulp_password: str = ""
    snapshot_artifact_type: str = "application/vnd.npm.packages"
    compliance_artifact_type: str = "application/vnd.npm.tl-compliance+json"
    path_entries: list[str] = field(default_factory=list)
    bash_executable: str = ""

    @classmethod
    def from_environ(cls) -> ProbeEnv:
        env = cls(
            pulp_base_url=os.environ.get("PULP_BASE_URL", cls.pulp_base_url),
            pulp_api_root=os.environ.get("PULP_API_ROOT", cls.pulp_api_root),
            pulp_domain=os.environ.get("PULP_DOMAIN", cls.pulp_domain),
            pulp_repository=os.environ.get("PULP_REPOSITORY", cls.pulp_repository),
            tl_npm_registry_url=os.environ.get(
                "TL_NPM_REGISTRY_URL", cls.tl_npm_registry_url
            ),
            upstream_registry=os.environ.get(
                "NPM_UPSTREAM_REGISTRY",
                os.environ.get("UPSTREAM_REGISTRY", cls.upstream_registry),
            ),
            compliance_image_prefix=os.environ.get("COMPLIANCE_IMAGE_PREFIX", ""),
            snapshot_image_prefix=os.environ.get("SNAPSHOT_IMAGE_PREFIX", ""),
            closure_index_image=os.environ.get("CLOSURE_INDEX_IMAGE", ""),
            pulp_username=os.environ.get("PULP_USERNAME", ""),
            pulp_password=os.environ.get("PULP_PASSWORD", ""),
            snapshot_artifact_type=os.environ.get(
                "SNAPSHOT_ARTIFACT_TYPE", cls.snapshot_artifact_type
            ),
            compliance_artifact_type=os.environ.get(
                "COMPLIANCE_ARTIFACT_TYPE", cls.compliance_artifact_type
            ),
        )
        env.setup()
        return env

    def setup(self) -> None:
        utils = self.root / "utils" / "scripts"
        builder = self.root / "npm-builder" / "scripts"
        self.path_entries = []
        bash_dir = _bash_bin_dir()
        if bash_dir:
            self.path_entries.append(bash_dir)
            self.bash_executable = str(Path(bash_dir) / "bash")
        for entry in _preferred_path_prefixes():
            if entry not in self.path_entries:
                self.path_entries.append(entry)
        self.path_entries.extend([str(utils), str(builder)])
        if self.compliance_image_prefix and not self.closure_index_image:
            base = _strip_image_base(self.compliance_image_prefix)
            self.closure_index_image = f"{base}/npm-closure-index:latest"

    def resolve_bash(self) -> str:
        if self.bash_executable and _bash_major_version(Path(self.bash_executable)) >= 4:
            return self.bash_executable
        bash = _find_modern_bash()
        if not bash:
            sys.exit(
                "ERROR: bash 4+ required (assess-npm-compliance uses mapfile).\n"
                "macOS /bin/bash is 3.2 — install a newer bash and retry:\n"
                "  brew install bash\n"
                "Then ensure /opt/homebrew/bin is on PATH, or set:\n"
                "  export NPM_PROBE_BASH=/opt/homebrew/bin/bash"
            )
        self.bash_executable = bash
        bash_dir = str(Path(bash).parent)
        if bash_dir not in self.path_entries:
            self.path_entries.insert(0, bash_dir)
        return bash

    def as_subprocess_env(self) -> dict[str, str]:
        merged = os.environ.copy()
        merged["PATH"] = os.pathsep.join(self.path_entries + [merged.get("PATH", "")])
        merged["PULP_BASE_URL"] = self.pulp_base_url
        merged["PULP_API_ROOT"] = self.pulp_api_root
        merged["PULP_DOMAIN"] = self.pulp_domain
        merged["PULP_REPOSITORY"] = self.pulp_repository
        merged["TL_NPM_REGISTRY_URL"] = self.tl_npm_registry_url
        merged["UPSTREAM_REGISTRY"] = self.upstream_registry
        merged["TL_SKIP_COMPLIANCE_SIDECAR"] = os.environ.get(
            "TL_SKIP_COMPLIANCE_SIDECAR", "1"
        )
        if not os.environ.get("TL_REGISTRY_RETRIES"):
            merged["TL_REGISTRY_RETRIES"] = "5"
        if not os.environ.get("TL_REGISTRY_TIMEOUT"):
            merged["TL_REGISTRY_TIMEOUT"] = "60"
        if self.compliance_image_prefix:
            merged["COMPLIANCE_IMAGE_PREFIX"] = self.compliance_image_prefix
        if self.snapshot_image_prefix:
            merged["SNAPSHOT_IMAGE_PREFIX"] = self.snapshot_image_prefix
        if self.closure_index_image:
            merged["CLOSURE_INDEX_IMAGE"] = self.closure_index_image
        if self.pulp_username:
            merged["PULP_USERNAME"] = self.pulp_username
        if self.pulp_password:
            merged["PULP_PASSWORD"] = self.pulp_password
        return merged

    def compliance_image_for(self, name: str, version: str) -> str:
        base = _strip_image_base(self.compliance_image_prefix)
        return f"{base}:{compliance_tag(name, version)}"

    def snapshot_image_for(self, name: str, version: str) -> str:
        base = _strip_image_base(self.snapshot_image_prefix)
        return f"{base}:{compliance_tag(name, version)}"

    def require_pulp_creds(self) -> None:
        if not self.pulp_username or not self.pulp_password:
            sys.exit("ERROR: PULP_USERNAME and PULP_PASSWORD are required")

    def require_compliance_prefix(self) -> None:
        if not self.compliance_image_prefix:
            sys.exit(
                "ERROR: COMPLIANCE_IMAGE_PREFIX is required\n"
                "  export COMPLIANCE_IMAGE_PREFIX='quay.io/<org>/npm-compliance'"
            )
        if not self.closure_index_image:
            base = _strip_image_base(self.compliance_image_prefix)
            self.closure_index_image = f"{base}/npm-closure-index:latest"

    def require_snapshot_prefix(self) -> None:
        if not self.snapshot_image_prefix:
            sys.exit(
                "ERROR: SNAPSHOT_IMAGE_PREFIX is required\n"
                "  export SNAPSHOT_IMAGE_PREFIX='quay.io/<org>/npm-snapshot'"
            )

    def require_quay_env(self) -> None:
        self.require_compliance_prefix()
        self.require_snapshot_prefix()

    def assert_npm_repository(self) -> None:
        if self.pulp_repository == "main":
            sys.exit(
                "ERROR: PULP_REPOSITORY=main is the python wheels repo; use npm-registry."
            )

    def script_path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)


def _bash_major_version(bash_path: Path) -> int:
    import subprocess

    bash = _validate_executable_path(bash_path)
    try:
        out = subprocess.check_output(  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use
            [str(bash), "--version"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    match = re.search(r"version\s+(\d+)", out)
    if not match:
        return 0
    return int(match.group(1))


def _bash_candidate_paths() -> list[Path]:
    explicit = os.environ.get("NPM_PROBE_BASH", "").strip()
    if explicit:
        return [Path(explicit)]
    return [
        Path("/opt/homebrew/opt/bash/bin/bash"),
        Path("/usr/local/opt/bash/bin/bash"),
        Path("/opt/homebrew/bin/bash"),
        Path("/usr/local/bin/bash"),
    ]


def _find_modern_bash() -> str | None:
    for candidate in _bash_candidate_paths():
        if candidate.is_file() and os.access(candidate, os.X_OK):
            if _bash_major_version(candidate) >= 4:
                return str(candidate)
    fallback = shutil.which("bash")
    if fallback and _bash_major_version(Path(fallback)) >= 4:
        return fallback
    return None


def _bash_bin_dir() -> str | None:
    bash = _find_modern_bash()
    if not bash:
        return None
    return str(Path(bash).parent)


def _preferred_path_prefixes() -> list[str]:
    """GNU coreutils gnubin on macOS (readlink -f, sha256sum)."""
    prefixes: list[str] = []
    for p in _macos_coreutils_paths():
        if (Path(p) / "sha256sum").exists() and (Path(p) / "readlink").exists():
            prefixes.append(p)
            break
    return prefixes


def _macos_coreutils_paths() -> list[str]:
    paths = [
        "/opt/homebrew/opt/coreutils/libexec/gnubin",
        "/usr/local/opt/coreutils/libexec/gnubin",
    ]
    brew = shutil.which("brew")
    if brew:
        try:
            import subprocess

            brew_bin = _validate_executable_path(brew)
            prefix = subprocess.check_output(  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use
                [str(brew_bin), "--prefix", "coreutils"],
                text=True,
            ).strip()
            paths.append(f"{prefix}/libexec/gnubin")
        except (subprocess.CalledProcessError, OSError):
            pass
    return paths


def ensure_modern_bash(probe_env: ProbeEnv) -> None:
    """Production assess scripts require bash 4+ (mapfile)."""
    probe_env.resolve_bash()


def ensure_gnu_coreutils(probe_env: ProbeEnv | None = None) -> None:
    """npm-pulp-upload needs GNU readlink -f (macOS ships BSD readlink)."""
    import subprocess

    if shutil.which("readlink"):
        try:
            if subprocess.run(  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use
                ["readlink", "-f", "/"],
                capture_output=True,
                check=False,
            ).returncode == 0:
                return
        except OSError:
            pass
    for prefix in _macos_coreutils_paths():
        if (Path(prefix) / "readlink").exists():
            if probe_env is not None and prefix not in probe_env.path_entries:
                probe_env.path_entries.insert(0, prefix)
            os.environ["PATH"] = prefix + os.pathsep + os.environ.get("PATH", "")
            return
    sys.exit(
        "ERROR: GNU coreutils required (readlink -f, sha256sum). "
        "On macOS: brew install coreutils"
    )


def require_commands(*names: str) -> None:
    for name in names:
        if not shutil.which(name):
            sys.exit(f"ERROR: required command not found: {name}")
