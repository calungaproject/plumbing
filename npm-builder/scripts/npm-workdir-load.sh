#!/usr/bin/env bash
# Resolve npm-workdir-env.sh and initialize factory path variables.
set -euo pipefail

_npm_builder_env_file() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
    if [[ -f "${script_dir}/npm-workdir-env.sh" ]]; then
        echo "${script_dir}/npm-workdir-env.sh"
        return 0
    fi
    if [[ -f "${NPM_BUILDER_LIB:-/usr/local/lib/npm-builder}/npm-workdir-env.sh" ]]; then
        echo "${NPM_BUILDER_LIB:-/usr/local/lib/npm-builder}/npm-workdir-env.sh"
        return 0
    fi
    echo "npm-workdir-env.sh not found" >&2
    return 1
}

# shellcheck source=npm-workdir-env.sh
source "$(_npm_builder_env_file)"
npm_workdir_init
