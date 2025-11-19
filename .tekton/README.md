# CI Structure

## Tekton

This directory defines the different build Pipelines for each of the Konflux components defined in
this repository.

The `*-pull-request.yaml` and `*-push.yaml` files are
[Tekton PipelineRuns](https://tekton.dev/docs/pipelines/pipelineruns/#overview). A `PipelineRun`
describes the parameters for executing a `Pipeline`. As the name implies, the `*-pull-request.yaml`
files are triggered for pull requests and the `*-push.yaml` files are triggered when commits are
pushed to the `main` branch. The `pipelinesascode.tekton.dev/on-cel-expression` annotation on each
of those files defines this behavior. The name of the files themselves are merely conventions.

A `PipelineRun` can embed a `Pipeline` definition. However, this often creates unnecessary
duplication. We often want to run the same `Pipeline` definition for both pull request and push
events, for example. Instead, the different `Pipelines` are defined in their own files,
`*-pipeline.yaml`. The `PipelineRun` files _reference_ the `Pipeline` files. See the Konflux
[docs](https://konflux-ci.dev/docs/patterns/centralize-pipeline-definitions/) for more details on
this pattern.

A `Pipeline` consists of various `Tasks`. The definition of these `Tasks` could be embedded in the
`Pipeline` definition itself, but that can become quite unruly to maintain. We choose to use `Tasks`
by reference instead. There are different types of references, the one we use is the [bundles
resolver](https://tekton.dev/docs/pipelines/bundle-resolver/). This allows us to package a `Task` as
a [Tekton Bundle](https://tekton.dev/docs/pipelines/tekton-bundle-contracts/) (an OCI artifact) and
reference the `Task` from the `Pipeline` via an image reference.

`build-pipeline.yaml` is used for building _traditional_ container images via a Containerfile. These
are images that can be executed with podman or docker. The [builder](/builder/) image is one of
those.

`bundle-build-pipeline.yaml` is used for building a Tekton bundle. This `Pipeline` produces an OCI
artifact that contains Task and/or Pipeline definitions.

## Konflux Components

In Konflux, there are various `Components` that point to this git repository. As such, in Konflux's
terminology, this is considered a monorepo.

There is a dependency between the `Components`. For example, the builder image is used by the
build-python-wheels task. A change in the builder image requires not only building a new image, but
also building a new Tekton bundle for that `Task` that uses the new builder image.

The `Components` use [nudges](https://konflux-ci.dev/docs/building/component-nudges/#what-is-nudged)
to keep these dependencies up to date. If all is working as expected, Konflux should
generate pull requests to these `Component` dependencies up to date. In the example above, after
a new builder image is built, a pull request should be automatically created to update the `Task`
definition.
