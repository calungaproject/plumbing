# plumbing utils scripts

## `pulp-upload`

`pulp-upload` uploads Python distributions from `FILES_DIR` to the configured Pulp Python repository using `pulp-cli`. Each package is uploaded with its adjacent `.attestation` file.

The printed index URL uses `PULP_DISTRIBUTION_BASE_PATH` when it is set; otherwise it uses `PULP_REPOSITORY` as the distribution path:

`${PULP_BASE_URL}${PULP_API_ROOT}pypi/${PULP_DOMAIN}/${PULP_DISTRIBUTION_BASE_PATH}/simple/`

`PULP_REPOSITORY` is the backend repository identity used for discovery, version checks, and uploads. `PULP_API_ROOT` and `PULP_DOMAIN` configure the Pulp CLI API endpoint, and `PULP_USERNAME` / `PULP_PASSWORD` provide the Pulp credentials.
