IMAGE := us-central1-docker.pkg.dev/mtrx-hub-dev-3of/matrix-images/fuse:latest
NAMESPACE := argo-workflows

submit:
	uv run kedro submit --image ${IMAGE} --namespace ${NAMESPACE} --environment cloud -p data_processing