# User guide

> NOTE: This is a very early version of the plugin, and we aim to streamline this further going forward.

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

## Initialize the plugin

Next, initialise the plugin, this will create a `argo.yml` file that will house components of the argo configuration. Moreover, the plugin will prompt for the creation of baseline `Dockerfile` and `.dockerignore` files.

```bash
uv run kedro argo init
```

Validate the files, and make any changes required.

## Setting up your cloud environment

Our cluster infrastructure executes pipelines in a parallelized fashion, i.e., on different machines. It's therefore important that data exchanges between nodes is materialized in Cloud Storage, as local data storage is not shared among these machines. Let's start by installing the `gcsfs` package.

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
    base: gs://ai-platform-dev-everycure-storage/<your_project_name>/{oc.env:WORKFLOW_ID, dummy}
```

> **Important** Ensure to replace **<your_project_name>** with your project name.

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
gcloud container clusters get-credentials ai-platform-dev-gke-cluster --region us-central1 --project ec-ai-platform-dev
```

### Ensure all catalog entries are registered

This is a very early version of the plugin, which does _not_ support memory datasets. Ensure your pipeline does not use memory datasets, as this will lead to failures. We will be introducing a mechanism that will support this in the future.

### Execute pipeline

Run the following command to run on the cluster:

```
uv run kedro argo submit
```

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

## Fusing nodes for execution

By default, the resulting Argo Workflow runs each node on a dedicated machine. Often we would like to co-locate multiple nodes for execution on the same machine, this is where the `FusePipeline` comes in.

The `FusePipeline` is an extension of Kedro's `Pipeline` object, that guarantees that the nodes contained within it are executed on the same machine. See the following code example:

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

Workflows are allowed to consuming secrets provided by the cluster. Secrets can be mounted using the `template` section of the `argo.yml` file.

```yaml
# argo.yml

...

template:
  environment:
    # The configuration below mounts the `matrix_secrets.OPENAI_API_KEY` 
    # to the `OPENAI_API_TOKEN` environment variable.
    - name: OPENAI_API_TOKEN
      secret_ref:
        name: matrix_secrets
        key: OPENAI_API_KEY
```

This ensures that the underlying machine has access to the secret, next use the `oc.env` resolver to pull the secret in the globals, catalog or parameters, as follows:

```yml
# base/globals.yml

openai_token: ${oc.env:OPENAI_API_TOKEN}
```

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

## No space left on device 

If you receive the error `No space left on device (os error 28)` after running `uv run kedro argo submit`, it may be because Docker has used up all allocated  hard drive space on your machine. 

You can delete unused Docker files to clear up space with the command `docker system prune -a`. 