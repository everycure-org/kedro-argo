# What is argo-kedro

`argo-kedro` is a [kedro-plugin](https://kedro.org/) for executing Kedro pipelines on [Argo Workflows](https://argoproj.github.io/workflows/). It's core functionalities are:

- __Workflow construction__: `argo-kedro` constructs an [Argo Workflow](https://argo-workflows.readthedocs.io/en/latest/workflow-templates/) manifest from your Kedro pipeline for execution on your cluster. This ensures that the Kedro pipeline definition remains the single source of truth.

- __Defining compute resources__: `argo-kedro` exposes a custom `Node` type that can be used to control the compute resouces available to the node.

- __Node fusing__: To maximize parallelisation, `argo-kedro` executes each Kedro node in a dedicated Argo task. The plugin exposes a `FusedPipeline` object that can be used to co-locate nodes for execution on a single Argo task.

- __Custom and init templates__: Register custom templates, either to customize the task in which your Kedro nodes runs, or to execute _before_ the pipeline runs. The former unlocks spinning up auxiliary services for the duration of you Kedro node, e.g., an emphemeral Neo4j sidecar that can be used to run graph algorihms. The latter allows for bootstrapping external systems, e.g.., creating an MLFlow run for the pipeline.

## Table of contents

- [How do I use argo-kedro?](#how-do-i-install-argo-kedro)
  - [Set up your Kedro project](#set-up-your-kedro-project)
  - [Set up your venv](#set-up-your-venv)
  - [Install the plugin](#install-the-plugin)
  - [Setting up your cloud environment](#setting-up-your-cloud-environment)
  - [Submitting to the cluster](#submitting-to-the-cluster)
- [Advanced configuration](#advanced)
  - [Configuring machines types](#configuring-machines-types)
  - [GPU support](#gpu-support)
  - [Fusing nodes for execution](#fusing-nodes-for-execution)
  - [Using cluster Secrets](#using-cluster-secrets)
  - [Custom templates](#custom-templates)
  - [Init templates](#init-templates)
- [Known issues](#known-issues)
- [Common errors](#common-errors)

# How do I install argo-kedro?

## Set up your Kedro project

Use the Kedro CLI to setup your project, i.e.,

```bash
kedro new
```

## Set up your venv

```bash
uv sync
```

## Install the plugin

```bash
uv add argo-kedro
```

Next, initialise the plugin, this will create a `argo.yml` file that will house components of the argo configuration. Moreover, the plugin will prompt for the creation of baseline `Dockerfile` and `.dockerignore` files.

```bash
uv run kedro argo init
```

Validate the files, and make any changes required.

## Setting up your cloud environment

Argo Workflows executes pipelines in a parallelized fashion, i.e., on different compute instances. It's therefore important that data exchanged between nodes is materialized in remote storage, as local data storage is not shared among these machines. Let's start by installing the `gcsfs` package.

> NOTE: The split between the `base` and `cloud` environment enables development workflows where local data storage is used when iterating locally, while the cluster uses Google Cloud storage.

```bash
uv add "fsspec[gcs]"
```

### Registering the globals file

Kedro allows customizing variables based on the environment, which unlocks local data storage for testing, while leveraging Cloud Storage for running on the cluster. First, enable the use of the globals in the `settings.py` file. To do so, replace the `CONFIG_LOADER_ARGS` setting with the contents below:

```python
# Add the following import on top of the file
from omegaconf.resolvers import oc

CONFIG_LOADER_ARGS = {
    "base_env": "base",
    "default_run_env": "local",
    "merge_strategy": {"parameters": "soft", "globals": "soft"},
    "config_patterns": {
        "globals": ["globals*", "globals*/**", "**/globals*"],
        "parameters": [
            "parameters*",
            "parameters*/**",
            "**/parameters*",
            "**/parameters*/**",
        ],
    },
    "custom_resolvers": {
        "oc.env": oc.env,
    }
}
```

### Parametrizing the base path

Create a new file in `conf/base` folder called `globals.yml`. Start by defining the globals file for the base environment.

```yaml
# Definition for conf/base/globals.yml for local storage
paths:
    base: data
```

Next, create the `globals.yml` file for the cloud env in `conf/cloud` folder (if the folder doesn't exist, please create it), then define the globals file for the cloud environment with the following:

```yaml
# Definition for conf/cloud/globals.yml for cloud storage
paths:
    base: gs://<your_bucket_name>/<your_project_name>/${oc.env:WORKFLOW_ID, dummy}
```

> **Important** Ensure to replace **<your_bucket_name>** **<your_project_name>** with bucket and subdirectory respectively.

> The plugin adds a few environment variables to the container automatically, one of these is the `WORKFLOW_ID` which
> is a unique identifier of the workflow. This can be used as a unit of versioning as displayed below.

Finally, ensure the parametrized path is used, this should be done in the `conf/base/catalog.yml` file. For example:

```yaml
preprocessed_companies:
  type: pandas.ParquetDataset
  # This ensures that local storage is used in the base, while cloud storage
  # is used while running on the cluster.
  filepath: ${globals:paths.base}/02_intermediate/preprocessed_companies.parquet
```

> **IMPORTANT**: Make sure you replace `data/` string in the `conf/base/catalog.yml` file with `${globals:paths.base}/` as kedro isn't aware of the Cloud storage. This change would allow Kedro to switch between `local` and `cloud` env easily.

## Submitting to the cluster

### Ensure you have the correct kubeconfig set

Run the following CLI command to setup the cluster credentials.

```bash
gcloud container clusters get-credentials $CLUSTER_NAME --region us-central1 --project $PROJECT
```

### Ensure all catalog entries are registered

This is a very early version of the plugin, which does _not_ support memory datasets. Ensure your pipeline does not use memory datasets, as this will lead to failures. We will be introducing a mechanism that will support this in the future.

### Execute pipeline

Run the following command to run on the cluster:

```bash
uv run kedro argo submit
```

## Retrying a failed workload

If a pipeline fails, instead of submitting a new pipeline run, you could simply resubmit the failed workflow by running the following command:

```bash
uv run kedro argo resubmit
```

> **Note:** This command overrides the Docker image name and tag specified in the Argo configuration, because resubmitting requires that the workflow's Docker image and tag remain unchanged. No additional configuration is required on your part.

When using `resubmit`, you can optionally supply a `--workflow-name` argument to select which existing workflow run to retry; it does not set the name of a new workflow.

# Advanced

## Configuring machines types

The `argo.yml` file defines the possible machine typess that can be used by nodes in the pipeline, the platform team will share a list of valid machine types.


```yaml
# ...
# argo.yml

machine_types:
  default:
    mem: 16
    cpu: 4
    num_gpu: 0

default_machine_type: default
```

By default, the `default_machine_type` is used for all nodes of the pipeline, if you wish to configure the machine type, import the plugin's `Node` extension.

```python
# NOTE: Import from the plugin, this is a drop in replacement!
from argo_kedro.pipeline import Node

def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            Node(
                func=preprocess_companies,
                inputs="companies",
                outputs="preprocessed_companies",
                name="preprocess_companies_node",
                machine_type="n1-standard-4", # NOTE: enter a valid machine type from the configuration here
            ),
            ...
         ]
    )
```

## GPU support

The template Dockerfile comes with built-in support for running GPU workloads on Nvidia GPUs.

To run a `pipeline` on GPU, you would need to configure the `pipeline` machine type to a `g2` instance type. Currently supported GPU machine types are:

| Machine Type   | CPU | Memory | GPU | GPU memory |
|----------------|-----|--------|------|-----------|
| g2-standard-4  | 4   | 16     | 1    | 24        |
| g2-standard-8  | 8   | 32     | 1    | 24        |
| g2-standard-12 | 12  | 48     | 1    | 24        |
| g2-standard-16 | 16  | 64     | 1    | 24        |
| g2-standard-24 | 24  | 96     | 2    | 48        |
| g2-standard-32 | 32  | 128    | 1    | 24        |
| g2-standard-48 | 48  | 192    | 4    | 96        |
| g2-standard-96 | 96  | 384    | 8    | 192       |

To use the following machine type, you would need to modify the `pipeline` code as follows:

```python
# NOTE: Import from the plugin, this is a drop in replacement!
from argo_kedro.pipeline import Node

def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            Node(
                func=preprocess_companies,
                inputs="companies",
                outputs="preprocessed_companies",
                name="preprocess_companies_node",
                machine_type="g2-standard-4", # NOTE: enter a valid machine type from the above mentioned list.
            ),
            ...
         ]
    )
```

## Fusing nodes for execution

### Why fusing?

To run a Kedro pipeline on Argo, the question of how to map Kedro nodes to Argo tasks arises. There are two immediately obvious, albeit extreme, directions:

1. Single Argo task for _entire_ pipeline
   - Pros:
      - Simple setup, Argo task invokes `kedro run` for entire pipeline
   - Cons:
      - Limited options for leveraging parallelization
      - Entire pipeline has to run with single hardware configuration
         - May be very expensive for pipelines requiring GPUs in some steps
1. Argo task for _each_ node in the pipeline
   - Pros:
      - Maximize parallel processing capabilities
      - Allow for different hardware configuration per node
   - Cons:
      - Scheduling overhead for very small Kedro nodes
      - Complex DAG in Argo Workflows

For our use-case, a pipeline with hundreds of nodes, we want to enable fusing sets of related<sup>2</sup> nodes for execution on _single_ Argo task. This avoids scheduling overhead while still supporting heterogeneous hardware configurations within the pipeline.

<sup>2</sup> Related here is used in the broad sense of the word, i.e., they may have similar hardware needs, are highly coupled, or all rely on an external service.

### The `FusedPipeline` object

The `FusedPipeline` is an extension of Kedro's `Pipeline` object, that guarantees that the nodes contained within it are executed on the same Argo task. See the following code example:

```python
from kedro.pipeline import Pipeline
from argo_kedro.pipeline import FusedPipeline, Node

from .nodes import create_model_input_table, preprocess_companies, preprocess_shuttles


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            FusedPipeline(
                nodes=[
                    Node(
                        func=preprocess_companies,
                        inputs="companies",
                        outputs="preprocessed_companies",
                        name="preprocess_companies_node",
                    ),
                    Node(
                        func=preprocess_shuttles,
                        inputs="shuttles",
                        outputs="preprocessed_shuttles",
                        name="preprocess_shuttles_node",
                    ),
                ],
                name="preprocess_data_fused",
                machine_type="n1-standard-1"
            ),
            Node(
                func=create_model_input_table,
                inputs=["preprocessed_shuttles", "preprocessed_companies", "reviews"],
                outputs="model_input_table",
                name="create_model_input_table_node",
            ),
        ]
    )
```

The code snippet above wraps the `preprocess_companies_node` and `preprocess_shuttles_node` nodes together for execution on the same machine. Similar to the plugins' `Node` object, the `FusedPipeline` accepts a `machine_type` argument that allows for customizing the machine type to use.

> Given that the nodes within the `FusedPipeline` now execute on the same machine, the plugin performs a small optimization step to reduce IO. Specifically, each intermediate, i,.e., non-output dataset within the `FusedPipeline` is transformed into a `MemoryDataset`. This allows for Kedro to keep these datasets in memory, without having to materialize them to disk. The behaviour can be toggled by `runner.use_memory_datasets` in `argo.yml`.

## Using cluster Secrets

Workflows are allowed to consume secrets provided by the cluster. Secrets can be mounted using the `template` section of the `argo.yml` file.

```yaml
# argo.yml

...

template:
  environment:
    # The configuration below mounts the `secret.TOKEN` 
    # to the `TOKEN` environment variable.
    - name: TOKEN
      secret_ref:
        name: secret
        key: TOKEN
```

This ensures that the pods running the workflow nodes have access to the secret, next use the `oc.env` resolver to pull the secret in the globals, catalog or parameters, as follows:

```yml
# base/globals.yml

token: ${oc.env:TOKEN}
```

## Custom templates

> This is an experimental capability of the plugin.

The plugin allows for customizing the workflow manifest through the `templates` section in the `argo.yml` file. A first use-case that comes to mind is customizing the Argo task that executes a specific Kedro node. For instance, to spin up an auxiliary service for the duration of the node.

```yaml
# argo.py
template:
  templates:
    - name: neo4j
      container:
        name: kedro
        command: ["/bin/sh", "-c"]
        env:
          - name: NEO4J_HOST
            value: "bolt://127.0.0.1:7687"
        args: |
          echo "Setting up temporary directories..."
          mkdir -p /data/tmp /data/spark-temp /data/spark-warehouse /data/checkpoints
          echo "Waiting for Neo4j to be ready..."
          until curl -s http://localhost:7474 > /dev/null; do
            echo "Waiting..."
            sleep 5
          done
          echo "Neo4j is ready. Starting main application..."
          kedro run -p "{{inputs.parameters.pipeline}}" -e "{{inputs.parameters.environment}}" -n "{{inputs.parameters.kedro_nodes}}"
      sidecars:
        - name: neo4j
          image: neo4j:5.21.0-enterprise
```

```python
# NOTE: Import from the plugin, this is a drop in replacement!
from argo_kedro.pipeline import Node

def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            Node(
                func=run_neo4j_graph_algortim,
                inputs=["nodes", "edges"],
                outputs="output",
                name="run_neo4j_graph_algorithm",
                template="neo4j"
            ),
        ]
    )
```


## Init templates

> This is an experimental capability of the plugin.

```yaml
template:

  templates:
    - name: init-mlflow-run
      container:
        name: init-mlflow-run
        command: ["python", "-c"]
        args: |
          import os
          import mlflow

          mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
          mlflow.set_experiment(os.environ["MLFLOW_EXPERIMENT_NAME"])
          run = mlflow.start_run(run_name=os.environ["WORKFLOW_ID"])
          with open("/tmp/mlflow_run_id", "w", encoding="utf-8") as f:
              f.write(run.info.run_id)
      outputs:
        parameters:
          - name: mlflow_run_id
            path: /tmp/mlflow_run_id

    init_templates: ["init-mlflow-run"]
```

A template can optionally be listed as an `init_templates`. This has the following effect:

1. The template is ran _before_ the tasks that represent the Kedro pipeline
2. All template outputs are passed to the tasks of the pipeline, and mounted as environment variables.

# Known issues

## Default pipeline with fusing for sub-pipelines

Kedro handles the `__default__` pipeline through auto-detection, given it's current implementation of the `sum` operator, the Fusing is ignored if the _full_ pipeline is wrapped in a `FusedPipeline` object. The current work-around is to use the `sum_pipelines` function from the package to build the default pipeline, i.e.,

```python
from kedro.framework.project import find_pipelines
from kedro.pipeline import Pipeline

from argo_kedro.pipeline import sum_pipelines


def register_pipelines() -> dict[str, Pipeline]:
    """Register the project's pipelines.

    Returns:
        A mapping from pipeline names to ``Pipeline`` objects.
    """
    pipelines = find_pipelines()
    pipelines["__default__"] = sum_pipelines(pipelines.values())
    return pipelines

```

## Kedro run with node target within fusing boundary

The current implementation of the fusing algorithm does not allow invocations of `kedro run` with a target node within the fuse boundary. The current work-around is to target the fused node in it's entirety. 

# Common errors

## Authentication errors while submitting to the cluster

Occasionally, the combination of the `fsspec[gcs]` and `kubernetes` dependencies give inconsistencies. A current solution is to pin the following dependency:

```
proto-plus==1.24.0.dev1
```

## Dataset saving errors

The Google Cloud filesystem implementation sometimes seems to result in some issues with Kedro. Resulting in `VersionedDataset` errors, even when versioning is disabled.

```
DatasetError: Cannot save versioned dataset '...' to 
'...' because a file with 
the same name already exists in the directory. This is likely because versioning
was enabled on a dataset already saved previously.
```

To fix the issue, pin the version of the following library:

```
gcsfs==2024.3.1
```

---

## Brand and Trademark Notice

**Important**: The "Every Cure" name, logo, and related trademarks are the exclusive property of
Every Cure. Contributors and users of this open-source project are not authorized to use the Every
Cure brand, logo, or trademarks in any way that suggests endorsement, affiliation, or sponsorship
without explicit written permission from Every Cure.

This project is open source and available under the terms of its license, but the Every Cure brand
and trademarks remain protected. Please respect these intellectual property rights.

