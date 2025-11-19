# Calunga Plumbing

The repository provides a containerized solution for building Python wheels from source
distributions using [Fromager](https://github.com/python-wheel-build/fromager). This is designed to
work within trusted build environments and can be used as part of larger CI/CD pipelines.

## Images

### Builder Image

The [builder](./builder) directory contains everything needed to build a container image that can:

- Resolve dependencies automatically using Fromager
- Build Python wheels from source distributions
- Handle CA trust configuration for enterprise environments
- Output both wheels and source distributions

## Utils Image

The [utils](./utils) directory is the source for the calunga utils image. This image is used for
various purposes, including releasing content to a pulp repository.

## CI

[Konflux](https://konflux-ci.dev/) is used as the CI system to build the different software
artifacts produced by this repository. See the [.tekton](/.tekton) directory for more information.
