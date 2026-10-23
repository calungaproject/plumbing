# plumbing utils scripts

## `pulp-upload`

`pulp-upload` uploads Python distributions from `FILES_DIR` to the configured Pulp Python repository using `pulp-cli`. Each package is uploaded with its adjacent `.attestation` file.

`pulp-upload` resolves the Python distributions associated with `PULP_REPOSITORY` and prints their simple index URLs. If `PULP_DISTRIBUTION_BASE_PATH` is set, it must match one of those distributions and only that index URL is printed:

`${PULP_BASE_URL}${PULP_API_ROOT}pypi/${PULP_DOMAIN}/${PULP_DISTRIBUTION_BASE_PATH}/simple/`

`PULP_REPOSITORY` is the backend repository identity used for discovery, version checks, and uploads. `PULP_API_ROOT` and `PULP_DOMAIN` configure the Pulp CLI API endpoint, and `TWINE_USERNAME` / `TWINE_PASSWORD` provide the existing Pulp credentials.
