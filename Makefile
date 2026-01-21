docker_image = us-central1-docker.pkg.dev/mtrx-hub-dev-3of/matrix-images/fuse
TAG = latest
TARGET_PLATFORM ?= linux/amd64

docker_auth:
	gcloud auth configure-docker us-central1-docker.pkg.dev

docker_build:
	docker buildx build --progress=plain --platform $(TARGET_PLATFORM) -t $(docker_image) --load ./ && \
	docker tag $(docker_image) $(docker_image):${TAG}

docker_push: docker_build
	docker push $(docker_image):${TAG}