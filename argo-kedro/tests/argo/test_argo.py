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
    TemplateConfig,
)

@pytest.fixture
def machine_types() -> dict[str, MachineType]:
    return {
        "n1-standard-4": MachineType(mem=16, cpu=4, num_gpu=0),
        "n1-standard-8": MachineType(mem=16, cpu=8, num_gpu=0, emph_storage=100),
        "gpu-node": MachineType(mem=32, cpu=8, num_gpu=1),
    }


@pytest.fixture
def template_config() -> dict[str, MachineType]:
    return TemplateConfig()


@pytest.fixture
def default_machine_type() -> str:
    return "n1-standard-4"

@pytest.fixture
def pipeline() -> Pipeline:
    return Pipeline(
        [
            Node(
                func=lambda x: x,
                inputs="raw_data",
                outputs="data",
                tags=["preprocessing"],
                name="preprocess_fun",
            ),
            Node(
                func=lambda x: x,
                inputs="data",
                outputs="model",
                tags=["training"],
                name="train_fun",
                machine_type="n1-standard-8",
                template="custom_template",
            ),
        ]
    )

@pytest.fixture
def fused_pipeline() -> Pipeline:
    return Pipeline(
        [
            Node(
                func=lambda x: x,
                inputs="raw_data",
                outputs="data",
                tags=["preprocessing"],
                name="preprocess_fun",
                machine_type="gpu-node",
            ),
            FusedPipeline(
                [
                    KedroNode(
                        func=lambda x: x,
                        inputs="data",
                        outputs="model",
                        tags=["training"],
                        name="train_fun",
                    ),
                    KedroNode(
                        func=lambda x: x,
                        inputs="model",
                        outputs="predictions",
                        tags=["predictions"],
                        name="create_predictions",
                    ),
                ],
                name="fused_modelling",
                machine_type="n1-standard-8",
            ),
        ]
    )


def test_get_argo_dag(pipeline: Pipeline, machine_types: dict[str, MachineType], default_machine_type: str, template_config: TemplateConfig):

    # When generating the argo DAG
    argo_dag = get_argo_dag(pipeline, machine_types, default_machine_type, template_config)
    expected = {
        "preprocess_fun": { 
            "name": "preprocess-fun",
            "nodes": "preprocess_fun",
            "deps": [],
            "mem": 16,
            "cpu": 4,
            "num_gpu": 0,
            "template": "kedro",
            "emph_storage": 0,
        },
        "train_fun": {
            "name": "train-fun",
            "nodes": "train_fun",
            "deps": ["preprocess-fun"],
            "mem": 16,
            "cpu": 8,
            "num_gpu": 0,
            "template": "custom_template",
            "emph_storage": 100,
        }
    }

    # Assert resulting argo dag is correct
    assert {key: task.to_dict() for key,task in argo_dag.items()} == expected


def test_get_argo_dag_fused(fused_pipeline: Pipeline, machine_types: dict[str, MachineType], default_machine_type: str, template_config: TemplateConfig):

    # When generating the argo DAG
    argo_dag = get_argo_dag(fused_pipeline, machine_types, default_machine_type, template_config)
    expected = {
        "preprocess_fun": { 
            "name": "preprocess-fun",
            "nodes": "preprocess_fun",
            "deps": [],
            "mem": 32,
            "cpu": 8,
            "num_gpu": 1,
            "template": "kedro",
            "emph_storage": 0,
        },
        "fused_modelling": {
            "name": "fused-modelling",
            "nodes": "fused_modelling",
            "deps": ["preprocess-fun"],
            "mem": 16,
            "cpu": 8,
            "num_gpu": 0,   
            "template": "kedro",
            "emph_storage": 100,
        }
    }

    # Assert resulting argo dag is correct
    assert {key: task.to_dict() for key,task in argo_dag.items()} == expected