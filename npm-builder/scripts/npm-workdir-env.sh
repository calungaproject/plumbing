# npm-builder factory workdir layout — source from factory scripts; do not execute directly.
# Tekton sets WORKDIR_ROOT (default /var/workdir). Other paths are derived from it.

npm_workdir_init() {
    WORKDIR_ROOT="${WORKDIR_ROOT:-/var/workdir}"
    SOURCE_ROOT="${SOURCE_ROOT:-${WORKDIR_ROOT}/source}"
    WORK_ROOT="${WORK_ROOT:-${WORKDIR_ROOT}/work}"
    OUTPUT_ROOT="${OUTPUT_ROOT:-${WORKDIR_ROOT}/output}"
    ARTIFACT_ROOT="${ARTIFACT_ROOT:-${WORKDIR_ROOT}/artifact}"
    BUILT_LIST="${BUILT_LIST:-${WORKDIR_ROOT}/built/list.txt}"

    # Local dev: no trusted-artifact checkout — use repo root + .npm-factory scratch dirs.
    if [[ ! -d "${SOURCE_ROOT}" && -d "${PWD}/packages" ]]; then
        SOURCE_ROOT="${PWD}"
        WORKDIR_ROOT="${PWD}/.npm-factory"
        WORK_ROOT="${WORKDIR_ROOT}/work"
        OUTPUT_ROOT="${WORKDIR_ROOT}/output"
        ARTIFACT_ROOT="${WORKDIR_ROOT}/artifact"
        BUILT_LIST="${WORKDIR_ROOT}/built/list.txt"
    fi

    export WORKDIR_ROOT SOURCE_ROOT WORK_ROOT OUTPUT_ROOT ARTIFACT_ROOT BUILT_LIST
}
