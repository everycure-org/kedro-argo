# argo-kedro

A Kedro plugin for running pipelines on Argo Workflows in Kubernetes clusters.

## Features

- ✅ Submit Kedro pipelines to Argo Workflows
- ✅ Fuse pipeline nodes for optimized execution
- ✅ Memory dataset management during fusing
- 🚧 Image building guidelines
- 🚧 Hardware configuration support
- 🚧 Custom template registration

## Installation

```bash
pip install argo-kedro
```

## Prerequisites

- Kubernetes cluster with Argo Workflows installed
- `kubeconfig` configured correctly
- Argo Workflows namespace set up

## Quick Start

### 1. Configure your Kedro project

Add Argo configuration to your Kedro project (e.g., in `conf/base/argo.yml`).

### 2. Use the CLI

```bash
# Submit pipeline to Argo
kedro argo submit

# Other commands
kedro argo --help
```

## Usage

- Ensure kubeconfig is set correctly.
- Ensure Argo installed correctly on cluster and namespace present.

## Project setup

- Distinguish new cloud environment for running remotely

## Current Assumptions

- For image building, we assume the user enters the path to a valid GAR repository, which the cluster is assumed to have permissions to
- We work with the `latest` tag only, as Argo ensures to apply `imagePullPolicy: Always` in that case

## Known Issues

- Installing both the k8s and gcfs libs may cause authentication issues
- Current workaround: `uv pip uninstall gcsfs`

## Development Roadmap

### Horizon 1
- [x] Package and deploy to pypi
- [x] Submitting to cluster
- [ ] Provide image building guidelines
    - [ ] Kedro MLFlow plugin shows nice way of consuming "config", argo.yml

### Horizon 2
- [ ] Hardware configuration

### Horizon 3 (making feature complete)
- [x] Fusing pipelines
- [x] Set memory datasets during fusing
- [ ] Allow registering custom templates, e.g., neo4j
- [ ] Allow environment variables

### Horizon 4 (Open sourcing)
- [ ] Complete feature set

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details
