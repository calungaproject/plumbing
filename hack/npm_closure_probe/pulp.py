"""Pulp upload via production npm-pulp-upload (with probe reuse-if-exists)."""

from __future__ import annotations

import base64
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .env import ProbeEnv, ensure_gnu_coreutils, require_commands
from .runner import run_pipeline_script


def _query_base(probe_env: ProbeEnv) -> str:
    root = probe_env.pulp_api_root.rstrip("/") + "/"
    return f"{probe_env.pulp_base_url}{root}pulp/{probe_env.pulp_domain}/api/v3/"


def _auth_header(probe_env: ProbeEnv) -> dict[str, str]:
    token = base64.b64encode(
        f"{probe_env.pulp_username}:{probe_env.pulp_password}".encode()
    ).decode()
    return {"Authorization": f"Basic {token}"}


def _pulp_get(probe_env: ProbeEnv, url: str) -> dict:
    req = urllib.request.Request(url, headers=_auth_header(probe_env))
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        sys.exit(f"Pulp GET failed ({exc.code}): {body}")


def _pulp_post_json(probe_env: ProbeEnv, url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    headers = {**_auth_header(probe_env), "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        sys.exit(f"Pulp POST failed ({exc.code}): {body}")


def _repository_latest_version(probe_env: ProbeEnv) -> str | None:
    query = _query_base(probe_env)
    repo = _pulp_get(
        probe_env,
        query
        + "repositories/npm/npm/?"
        + urllib.parse.urlencode({"name": probe_env.pulp_repository}),
    )
    results = repo.get("results") or []
    if not results:
        return None
    return results[0]["latest_version_href"]


def _get_package_content_row(
    probe_env: ProbeEnv,
    name: str,
    version: str,
    *,
    strict: bool = False,
) -> dict | None:
    repo_ver = _repository_latest_version(probe_env)
    if not repo_ver:
        if strict:
            sys.exit(f"ERROR: repository {probe_env.pulp_repository} not found")
        return None
    query = _query_base(probe_env)
    content = _pulp_get(
        probe_env,
        query
        + "content/npm/packages/?"
        + urllib.parse.urlencode(
            {"name": name, "repository_version": repo_ver, "limit": 100}
        ),
    )
    matches = [
        row
        for row in content.get("results", [])
        if row.get("name") == name and row.get("version") == version
    ]
    if len(matches) != 1:
        if strict:
            sys.exit(f"expected one content row for {name}@{version}, got {len(matches)}")
        return None
    return matches[0]


def find_pulp_href(probe_env: ProbeEnv, name: str, version: str) -> str:
    row = _get_package_content_row(probe_env, name, version, strict=True)
    assert row is not None
    return row["pulp_href"]


def _apply_compliance_label(
    probe_env: ProbeEnv, content_href: str, level: str, current: str
) -> None:
    if not level or current == level:
        if level and current == level:
            print(f"  Label tl.compliance_level={level} already set")
        return
    url = probe_env.pulp_base_url + content_href + "set_label/"
    print(f"  Setting tl.compliance_level={level} on {content_href}")
    _pulp_post_json(
        probe_env,
        url,
        {"key": "tl.compliance_level", "value": level},
    )


def _reuse_existing(
    probe_env: ProbeEnv, name: str, version: str, level: str
) -> str | None:
    row = _get_package_content_row(probe_env, name, version, strict=False)
    if not row:
        return None
    href = row.get("pulp_href") or ""
    current = (row.get("pulp_labels") or {}).get("tl.compliance_level", "")
    print("=== reuse existing Pulp content ===")
    print(f"  {name}@{version} already in {probe_env.pulp_repository}")
    print(f"  pulp_href: {href}")
    _apply_compliance_label(probe_env, href, level, current)
    return href


def upload_to_pulp(
    probe_env: ProbeEnv,
    tgz: Path,
    sidecar: Path,
    level: str,
    *,
    reuse_if_exists: bool = True,
) -> str:
    require_commands("sha256sum")
    ensure_gnu_coreutils(probe_env)
    probe_env.require_pulp_creds()
    upload_script = probe_env.script_path("utils", "scripts", "npm-pulp-upload")
    if not upload_script.is_file():
        sys.exit(f"ERROR: npm-pulp-upload not found: {upload_script}")

    with tarfile.open(tgz, "r:gz") as tf:
        pkg_json = json.loads(tf.extractfile("package/package.json").read().decode())
    name = pkg_json["name"]
    version = pkg_json["version"]

    print()
    print("=== Step 2: Pulp upload (npm-pulp-upload) ===")
    if reuse_if_exists:
        href = _reuse_existing(probe_env, name, version, level)
        if href:
            print()
            print("=== verify pulp_href ===")
            print(f"pulp_href={href}")
            return href
        print(f"Package not in {probe_env.pulp_repository} yet; uploading...")

    with tempfile.TemporaryDirectory(prefix="npm-pulp-upload.") as workdir_str:
        workdir = Path(workdir_str)
        secret_dir = workdir / "secret"
        files_dir = workdir / "files"
        secret_dir.mkdir()
        files_dir.mkdir()
        (secret_dir / "username").write_text(probe_env.pulp_username)
        (secret_dir / "password").write_text(probe_env.pulp_password)
        shutil.copy2(tgz, files_dir / tgz.name)
        shutil.copy2(sidecar, files_dir / sidecar.name)

        run_pipeline_script(
            probe_env,
            upload_script,
            extra_env={
                "FILES_DIR": str(files_dir),
                "SECRET_DIR": str(secret_dir),
                "PULP_FILE_REPOSITORY": probe_env.as_subprocess_env().get(
                    "PULP_FILE_REPOSITORY", ""
                ),
            },
        )

    href = find_pulp_href(probe_env, name, version)
    print()
    print("=== verify pulp_href ===")
    print(f"pulp_href={href}")
    return href
