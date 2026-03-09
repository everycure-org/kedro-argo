import subprocess
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from click.testing import CliRunner

from kedro.framework.project import pipelines as project_pipelines
from kedro.framework.session import KedroSession
from kedro.io import DataCatalog, MemoryDataset
from kedro.pipeline import Pipeline, Node as KedroNode
from argo_kedro.pipeline import FusedPipeline, Node
from argo_kedro.runners.fuse_runner import FusedRunner
from argo_kedro.framework.cli.cli import (
    get_argo_dag,
    get_failed_nodes,
    get_workflow,
    _get_workflow_image,
    resubmit,
    MachineType,
)

class TestGetFailedNodes:
    """Tests for the get_failed_nodes helper function."""

    def test_get_failed_nodes_with_failures(self):
        """Test extracting failed Pod nodes from a workflow."""
        workflow = {
            "status": {
                "phase": "Failed",
                "nodes": {
                    "workflow-abc-1": {
                        "phase": "Succeeded",
                        "type": "Pod",
                        "displayName": "preprocess-data",
                    },
                    "workflow-abc-2": {
                        "phase": "Failed",
                        "type": "Pod",
                        "displayName": "train-model",
                    },
                    "workflow-abc-3": {
                        "phase": "Error",
                        "type": "Pod",
                        "displayName": "evaluate-model",
                    },
                    "workflow-abc-dag": {
                        "phase": "Failed",
                        "type": "DAG",
                        "displayName": "pipeline",
                    },
                },
            }
        }
        failed = get_failed_nodes(workflow)
        assert sorted(failed) == ["evaluate-model", "train-model"]

    def test_get_failed_nodes_no_failures(self):
        """Test with a workflow that has no failed nodes."""
        workflow = {
            "status": {
                "phase": "Succeeded",
                "nodes": {
                    "workflow-abc-1": {
                        "phase": "Succeeded",
                        "type": "Pod",
                        "displayName": "preprocess-data",
                    },
                },
            }
        }
        failed = get_failed_nodes(workflow)
        assert failed == []

    def test_get_failed_nodes_empty_status(self):
        """Test with an empty status."""
        workflow = {"status": {}}
        failed = get_failed_nodes(workflow)
        assert failed == []

    def test_get_failed_nodes_no_status(self):
        """Test with no status at all."""
        workflow = {}
        failed = get_failed_nodes(workflow)
        assert failed == []

    def test_get_failed_nodes_uses_name_fallback(self):
        """Test fallback to 'name' when 'displayName' is missing."""
        workflow = {
            "status": {
                "nodes": {
                    "workflow-abc-1": {
                        "phase": "Failed",
                        "type": "Pod",
                        "name": "workflow-abc-1",
                    },
                },
            }
        }
        failed = get_failed_nodes(workflow)
        assert failed == ["workflow-abc-1"]

    def test_get_failed_nodes_ignores_non_pod_types(self):
        """Test that non-Pod types (DAG, Steps, etc.) are excluded even if failed."""
        workflow = {
            "status": {
                "nodes": {
                    "workflow-abc-dag": {
                        "phase": "Failed",
                        "type": "DAG",
                        "displayName": "pipeline",
                    },
                    "workflow-abc-steps": {
                        "phase": "Failed",
                        "type": "Steps",
                        "displayName": "steps",
                    },
                },
            }
        }
        failed = get_failed_nodes(workflow)
        assert failed == []


class TestGetWorkflowImage:
    """Tests for the _get_workflow_image helper function."""

    def test_extracts_image_from_kedro_template(self):
        workflow = {
            "spec": {
                "templates": [
                    {
                        "name": "kedro",
                        "container": {"image": "us-docker.pkg.dev/my-project/repo/my-image:abc123"},
                    },
                    {
                        "name": "pipeline",
                        "dag": {"tasks": []},
                    },
                ]
            }
        }
        assert _get_workflow_image(workflow) == "us-docker.pkg.dev/my-project/repo/my-image:abc123"

    def test_skips_busybox_and_alpine(self):
        workflow = {
            "spec": {
                "templates": [
                    {"name": "skip", "container": {"image": "busybox"}},
                    {"name": "init", "container": {"image": "alpine:3.18"}},
                    {"name": "kedro", "container": {"image": "registry.io/app:v2"}},
                ]
            }
        }
        assert _get_workflow_image(workflow) == "registry.io/app:v2"

    def test_returns_none_when_no_templates(self):
        assert _get_workflow_image({"spec": {}}) is None
        assert _get_workflow_image({}) is None

    def test_returns_none_when_only_dag_templates(self):
        workflow = {
            "spec": {
                "templates": [
                    {"name": "pipeline", "dag": {"tasks": []}},
                ]
            }
        }
        assert _get_workflow_image(workflow) is None

    def test_image_without_tag(self):
        """Image strings without a tag should still be returned."""
        workflow = {
            "spec": {
                "templates": [
                    {"name": "kedro", "container": {"image": "registry.io/app"}},
                ]
            }
        }
        assert _get_workflow_image(workflow) == "registry.io/app"

    def test_skips_templates_without_container(self):
        """Templates that only have scripts or resources should be skipped."""
        workflow = {
            "spec": {
                "templates": [
                    {"name": "script-step", "script": {"image": "python:3.11", "source": "print('hi')"}},
                    {"name": "kedro", "container": {"image": "myregistry/myapp:v1"}},
                ]
            }
        }
        assert _get_workflow_image(workflow) == "myregistry/myapp:v1"


class TestGetWorkflow:
    """Tests for the get_workflow helper function."""

    def test_get_workflow_calls_k8s_api(self):
        """get_workflow should call resource.get with the correct args."""
        mock_resource = MagicMock()
        mock_resource.get.return_value = {"metadata": {"name": "my-wf"}}

        mock_client = MagicMock()
        mock_client.resources.get.return_value = mock_resource

        result = get_workflow(mock_client, "my-ns", "my-wf")

        mock_client.resources.get.assert_called_once_with(
            api_version="argoproj.io/v1alpha1",
            kind="Workflow",
        )
        mock_resource.get.assert_called_once_with(name="my-wf", namespace="my-ns")
        assert result == {"metadata": {"name": "my-wf"}}

    def test_get_workflow_propagates_exceptions(self):
        """Errors from the K8s API should propagate."""
        mock_resource = MagicMock()
        mock_resource.get.side_effect = Exception("Not found")
        mock_client = MagicMock()
        mock_client.resources.get.return_value = mock_resource

        with pytest.raises(Exception, match="Not found"):
            get_workflow(mock_client, "ns", "missing-wf")


# ---------------------------------------------------------------------------
# Fixtures for resubmit command tests
# ---------------------------------------------------------------------------

def _make_failed_workflow(image="us-docker.pkg.dev/proj/repo/app:latest"):
    """Return a dict that looks like a failed Argo Workflow resource."""
    return MagicMock(
        **{
            "get.side_effect": lambda key, default=None: {
                "status": {
                    "phase": "Failed",
                    "nodes": {
                        "wf-abc-1": {"phase": "Succeeded", "type": "Pod", "displayName": "preprocess"},
                        "wf-abc-2": {"phase": "Failed", "type": "Pod", "displayName": "train-model"},
                    },
                },
                "spec": {
                    "templates": [
                        {"name": "kedro", "container": {"image": image}},
                        {"name": "pipeline", "dag": {"tasks": []}},
                    ]
                },
            }.get(key, default),
        }
    )


def _mock_kedro_context():
    """Return a mock KedroSession context with argo config."""
    ctx = MagicMock()
    ctx.argo.namespace = "argo-workflows"
    ctx.argo.deployment.image = "other-registry/other-image"
    ctx.argo.deployment.tag = "shouldnotbeused"
    ctx.argo.deployment.target_platform = "linux/amd64"
    ctx.argo.deployment.context = "../"
    return ctx


class TestResubmitCommand:
    """Tests for the resubmit Click command."""

    CLI_MODULE = "argo_kedro.framework.cli.cli"

    @pytest.fixture(autouse=True)
    def _patch_kedro(self, tmp_path):
        """Patch Kedro project discovery, bootstrap, and session."""
        self.mock_context = _mock_kedro_context()

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.load_context.return_value = self.mock_context

        patchers = [
            patch(f"{self.CLI_MODULE}.find_kedro_project", return_value=tmp_path),
            patch(f"{self.CLI_MODULE}.bootstrap_project"),
            patch(f"{self.CLI_MODULE}.KedroSession.create", return_value=mock_session),
            patch(f"{self.CLI_MODULE}.config.load_kube_config"),
            patch(f"{self.CLI_MODULE}.config.new_client_from_config"),
            patch(f"{self.CLI_MODULE}.DynamicClient"),
        ]
        self.mocks = [p.start() for p in patchers]
        self.mock_dynamic_client = self.mocks[-1].return_value  # DynamicClient()
        yield
        for p in patchers:
            p.stop()

    def _setup_workflow(self, workflow=None, image="us-docker.pkg.dev/proj/repo/app:latest"):
        """Configure the mock K8s client to return the given workflow."""
        wf = workflow or _make_failed_workflow(image)
        mock_resource = MagicMock()
        mock_resource.get.return_value = wf
        self.mock_dynamic_client.resources.get.return_value = mock_resource
        return wf

    # -- happy-path tests --------------------------------------------------

    @patch(f"argo_kedro.framework.cli.cli.subprocess.run")
    @patch(f"argo_kedro.framework.cli.cli.publish_image")
    def test_resubmit_with_rebuild(self, mock_publish, mock_run):
        """Full happy path: rebuild + argo retry."""
        self._setup_workflow(image="registry.io/myapp:v3")
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="retried", stderr="")

        runner = CliRunner()
        result = runner.invoke(resubmit, ["-w", "my-wf-abc"])

        assert result.exit_code == 0, result.output
        # Image should come from workflow, NOT from config
        mock_publish.assert_called_once()
        assert mock_publish.call_args.kwargs["full_image"] == "registry.io/myapp:v3"
        # argo retry should be called
        mock_run.assert_called_once()
        cmd = mock_run.call_args.args[0]
        assert cmd[:3] == ["argo", "retry", "my-wf-abc"]
        assert "--namespace" in cmd
        assert "argo-workflows" in cmd
        assert "retried successfully" in result.output

    @patch(f"argo_kedro.framework.cli.cli.subprocess.run")
    @patch(f"argo_kedro.framework.cli.cli.publish_image")
    def test_resubmit_no_rebuild(self, mock_publish, mock_run):
        """--no-rebuild skips image build."""
        self._setup_workflow()
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        runner = CliRunner()
        result = runner.invoke(resubmit, ["-w", "my-wf", "--no-rebuild"])

        assert result.exit_code == 0, result.output
        mock_publish.assert_not_called()
        mock_run.assert_called_once()

    @patch(f"argo_kedro.framework.cli.cli.subprocess.run")
    @patch(f"argo_kedro.framework.cli.cli.publish_image")
    def test_resubmit_shows_failed_nodes(self, mock_publish, mock_run):
        """The command should list the failed nodes."""
        self._setup_workflow()
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        runner = CliRunner()
        result = runner.invoke(resubmit, ["-w", "wf-123", "--no-rebuild"])

        assert "Failed nodes (1):" in result.output
        assert "train-model" in result.output

    @patch(f"argo_kedro.framework.cli.cli.subprocess.run")
    @patch(f"argo_kedro.framework.cli.cli.publish_image")
    def test_resubmit_prompts_for_name_when_missing(self, mock_publish, mock_run):
        """When --workflow-name is not given, the user is prompted."""
        self._setup_workflow()
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        runner = CliRunner()
        result = runner.invoke(resubmit, [], input="prompted-wf\n")

        assert result.exit_code == 0, result.output
        cmd = mock_run.call_args.args[0]
        assert "prompted-wf" in cmd

    # -- image extraction --------------------------------------------------

    @patch(f"argo_kedro.framework.cli.cli.subprocess.run")
    @patch(f"argo_kedro.framework.cli.cli.publish_image")
    def test_resubmit_uses_workflow_image_not_config(self, mock_publish, mock_run):
        """The image must come from the workflow, not from argo.yml / .env."""
        self._setup_workflow(image="workflow-registry.io/workflow-app:workflow-tag")
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        runner = CliRunner()
        result = runner.invoke(resubmit, ["-w", "wf-1"])

        assert result.exit_code == 0, result.output
        mock_publish.assert_called_once()
        assert mock_publish.call_args.kwargs["full_image"] == "workflow-registry.io/workflow-app:workflow-tag"

    def test_resubmit_fails_when_image_not_found(self):
        """If the workflow has no extractable image and --rebuild, error out."""
        wf = MagicMock()
        wf.get.side_effect = lambda key, default=None: {
            "status": {"phase": "Failed", "nodes": {}},
            "spec": {"templates": [{"name": "pipeline", "dag": {"tasks": []}}]},
        }.get(key, default)
        self._setup_workflow(workflow=wf)

        runner = CliRunner()
        result = runner.invoke(resubmit, ["-w", "wf-no-img"])

        assert result.exit_code != 0
        assert "Could not determine the container image" in result.output

    # -- error handling ----------------------------------------------------

    def test_resubmit_fails_on_workflow_not_found(self):
        """If the workflow doesn't exist, show a clear error."""
        mock_resource = MagicMock()
        mock_resource.get.side_effect = Exception("404 Not Found")
        self.mock_dynamic_client.resources.get.return_value = mock_resource

        runner = CliRunner()
        result = runner.invoke(resubmit, ["-w", "nonexistent"])

        assert result.exit_code != 0
        assert "Failed to fetch workflow" in result.output

    @patch(f"argo_kedro.framework.cli.cli.subprocess.run")
    @patch(f"argo_kedro.framework.cli.cli.publish_image")
    def test_resubmit_fails_when_argo_cli_missing(self, mock_publish, mock_run):
        """If argo CLI is not installed, show a helpful error."""
        self._setup_workflow()
        mock_run.side_effect = FileNotFoundError()

        runner = CliRunner()
        result = runner.invoke(resubmit, ["-w", "wf-1"])

        assert result.exit_code != 0
        assert "argo" in result.output and "not installed" in result.output

    @patch(f"argo_kedro.framework.cli.cli.subprocess.run")
    @patch(f"argo_kedro.framework.cli.cli.publish_image")
    def test_resubmit_fails_when_argo_retry_errors(self, mock_publish, mock_run):
        """If argo retry returns non-zero, surface the stderr."""
        self._setup_workflow()
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd="argo retry", stderr="workflow is not in a retry-able state"
        )

        runner = CliRunner()
        result = runner.invoke(resubmit, ["-w", "wf-1"])

        assert result.exit_code != 0
        assert "argo retry failed" in result.output

    # -- non-failed workflow -----------------------------------------------

    @patch(f"argo_kedro.framework.cli.cli.subprocess.run")
    @patch(f"argo_kedro.framework.cli.cli.publish_image")
    def test_resubmit_warns_on_non_failed_workflow(self, mock_publish, mock_run):
        """Succeeded workflows trigger a confirmation prompt."""
        wf = MagicMock()
        wf.get.side_effect = lambda key, default=None: {
            "status": {"phase": "Succeeded", "nodes": {}},
            "spec": {
                "templates": [
                    {"name": "kedro", "container": {"image": "reg/app:v1"}},
                ]
            },
        }.get(key, default)
        self._setup_workflow(workflow=wf)
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        runner = CliRunner()
        # User answers "yes" to the confirmation
        result = runner.invoke(resubmit, ["-w", "succeeded-wf"], input="y\n")

        assert result.exit_code == 0, result.output
        assert "Warning" in result.output
        mock_run.assert_called_once()  # retry still runs

    @patch(f"argo_kedro.framework.cli.cli.subprocess.run")
    @patch(f"argo_kedro.framework.cli.cli.publish_image")
    def test_resubmit_aborts_when_user_declines(self, mock_publish, mock_run):
        """User declines to retry a non-failed workflow."""
        wf = MagicMock()
        wf.get.side_effect = lambda key, default=None: {
            "status": {"phase": "Succeeded", "nodes": {}},
            "spec": {
                "templates": [
                    {"name": "kedro", "container": {"image": "reg/app:v1"}},
                ]
            },
        }.get(key, default)
        self._setup_workflow(workflow=wf)

        runner = CliRunner()
        result = runner.invoke(resubmit, ["-w", "succeeded-wf"], input="n\n")

        assert result.exit_code == 0
        mock_run.assert_not_called()
        mock_publish.assert_not_called()
