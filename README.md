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

## Ensure you have the correct kubeconfig set

Run the following CLI command to setup the cluster credentials.

```bash
gcloud container clusters get-credentials ai-platform-dev-gke-cluster --region us-central1 --project ec-ai-platform-dev
```

## Building your image

> This part is a temporarily solution only, it will be absorbed by the plugin going forward. For now, you will have to build your own container for executing on the cluster.

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
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY . .
RUN uv sync --frozen
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
  kedro submit --image $(docker_image)
```

Run the following command to run on the cluster:

```
make submit
```


