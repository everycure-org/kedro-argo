integration-test:
	uv run kedro argo init --force
	uv run kedro argo submit -d --workflow-name=test-workflow
	argo lint templates/argo-workflow-template.yml --offline