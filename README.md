# User guide

> NOTE: This is a very early version of the plugin, and we aim to streamline this further going forward.

## Set up your Kedro project

Use the Kedro CLI to setup your project, i.e.,

```bash
kedro new
```

## Set up your venv

```bash
uv venv
uv pip install -r requirements.txt
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

```bash
uv add fsspec[gcs]
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

Start by defining the globals file for the base environment.

```yaml
# Definition for base/globals.yml for local storage
paths:
	base: data
```

Next, define the globals file for the cloud environment.

> The plugin adds a few environment variables to the container automatically, one of these is the `WORKFLOW_ID` which
> is a unique identifier of the workflow. This can be used as a unit of versioning as displayed below.

```yaml
# Definition for base/globals.yml for local storage
paths:
	base: gs://ai-platform-dev-everycure-storage/<your_project_name>/{oc.env:WORKFLOW_ID}
```

Finally, ensure the parametrized path is used, for example:

```yaml
preprocessed_companies:
  type: pandas.ParquetDataset
  # This ensures that local storage is used in the base, while cloud storage
  # is used while running on the cluster.
  filepath: ${globals:paths.base}/02_intermediate/preprocessed_companies.parquet
```

## Submitting to the cluster

### Ensure you have the correct kubeconfig set

Run the following CLI command to setup the cluster credentials.

```bash
gcloud container clusters get-credentials ai-platform-dev-gke-cluster --region us-central1 --project ec-ai-platform-dev
```

### Ensure all catalog entries are registered

This is a very early version of the plugin, which does _not_ support memory datasets. Ensure your pipeline does not use memory datasets, as this will lead to failures. We will be introducing a mechanism that will support this in the future.

### Create .dockerignore

Add a `.dockerignore` file with the contents below to avoid constant re-uploading of your venv.

```
.venv
```

### Execute pipeline

Run the following command to run on the cluster:

```
make submit
```

# Common errors

## Authentication errors while submitting to the cluster

Occasionally, the combination of the `fsspec[gcs]` and `kubernetes` dependencies give inconsistencies. A current solution is to pin the following dependency:

```
proto-plus==1.24.0.dev1
```

