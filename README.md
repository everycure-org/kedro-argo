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

## Setting up your cloud environment

Our cluster infrastructure executes pipelines in a parallelized fashion, i.e., on different machines. It's therefore important that data exchanges between nodes is materialized in Cloud Storage, as local data storage is not shared among these machines. Let's start by installing the `gcsfs` package.

```bash
uv add fsspec[gcs]
```

### Registering the globals file

Kedro allows customizing variables based on the environment, which unlocks local data storage for testing, while leveraging Cloud Storage for running on the cluster. First, enable the use of the globals in the `settings.py` file. To do so, replace the `CONFIG_LOADER_ARGS` setting with the contents below:

```python
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

```yaml
# Definition for base/globals.yml for local storage
paths:
	base: gs://ai-platform-dev-everycure-storage/<your_project_name>
```

Finally, ensure the parametrized path is used, for example:

```
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

### Ensure you have a Dockerfile

The Dockerfile bundles all dependencies you need for running on the cluster. An example Dockerfile can be found below.

```Dockerfile
ARG IMAGE=ubuntu:24.04
FROM $IMAGE AS build

ENV UV_LINK_MODE=copy
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    curl && \
    update-ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV UV_LINK_MODE=copy
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

COPY --from=ghcr.io/astral-sh/uv:0.6.9 /uv /uvx /bin/

COPY pyproject.toml .
COPY uv.lock .
RUN uv sync --frozen --no-install-project
ENV PATH=/app/.venv/bin:$PATH

COPY . .

RUN uv sync --frozen
```

### Create .dockerignore

Add a `.dockerignore` file with the contents below to avoid constant re-uploading of your venv.

```
.venv
```

### Execute pipeline

Finally, build and push the image to the `ai-platform-registry` so the cluster has permissions to access the container. Add the following `Makefile` to the repository. Replace `your-project-name` with the name of your project.

``` 
docker_image = us-central1-docker.pkg.dev/ec-ai-platform-dev/ai-platform-images/your-project-name
TAG = latest
TARGET_PLATFORM ?= linux/amd64

docker_auth:
	gcloud auth configure-docker us-central1-docker.pkg.dev

docker_build:
	docker buildx build --progress=plain --platform $(TARGET_PLATFORM) -t $(docker_image) --load ./ && \
	docker tag $(docker_image) $(docker_image):${TAG}

docker_push: docker_auth docker_build
	docker push $(docker_image):${TAG}

submit: docker_push
	uv run kedro submit --image $(docker_image) --namespace argo-workflows --environment cloud
```

Run the following command to run on the cluster:

```
make submit
```


