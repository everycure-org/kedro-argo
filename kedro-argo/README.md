# Usage

- Ensure kubeconfig is set correctly
- Ensure Argo installed correctly on cluster and namespace present

# Project setup

- Distinguish new cloud environment for running remotely

# Ideas

## Horizon 1

- [ ] Package and deploy to pypi
- [x] Submitting to cluster
- [ ] Provide image buiding guiderails 
    - [ ] Kedro MLFlow plugin shows nice way of consuming "config", argo.yml

Assumptions:

- For the image building, we assume the user enters the path to a valid GAR repository, which the cluster is assumed to have permissions to. 
- We work with the `latest` tag only, as Argo ensures to apply `imagePullPolicy: Always` in that case

Current issue:

- It seems like installing both the k8s and gcfs libs give authentication issues
- current workaround: `uv pip uninstall gcsfs`

## Horizon 2

- [ ] Hardware configuration

## Horizon 3 (making feature complete)

- [x] Fusing pipelines
- [x] Set memory datasets during fusing
- [ ] Allow registering custom templates, e.g., neo4j
- [ ] Allow environment variables

## Horizon 4 (Open sourcing)

- [ ] Support any 