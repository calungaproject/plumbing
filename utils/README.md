# plumbing utils scripts

## `pulp-upload`

`pulp-upload` uploads Python distributions from `FILES_DIR` using `twine`.

The upload URL uses `PULP_DISTRIBUTION_BASE_PATH` when it is set; otherwise it uses `PULP_REPOSITORY` as the distribution path:

`${PULP_BASE_URL}${PULP_API_ROOT}pypi/${PULP_DOMAIN}/${PULP_DISTRIBUTION_BASE_PATH}/simple/`

`PULP_REPOSITORY` remains the backend repository identity used for discovery and version checks.
