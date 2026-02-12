import pytest

from kedro.pipeline import Pipeline, Node as KedroNode
from argo_kedro.pipeline import FusedPipeline, Node
from argo_kedro.framework.cli.cli import get_argo_dag, MachineType

@pytest.fixture
def machine_types() -> dict[str, MachineType]:
    return {
        "default": MachineType(mem=16, cpu=2, num_gpu=0),
        "n1-standard-4": MachineType(mem=16, cpu=4, num_gpu=0),
        "n1-standard-8": MachineType(mem=16, cpu=8, num_gpu=0),
        "gpu-node": MachineType(mem=32, cpu=8, num_gpu=1),
    }

@pytest.fixture
def default_machine_type() -> str:
    return "default"

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
                machine_type="n1-standard-4",
            ),
            Node(
                func=lambda x: x,
                inputs="data",
                outputs="model",
                tags=["training"],
                name="train_fun",
                machine_type="n1-standard-8",
            ),
        ]
    )

@pytest.fixture
def fused_pipeline() -> Pipeline:
    return Pipeline(
        [
            KedroNode(
                func=lambda x: x,
                inputs="raw_data",
                outputs="data",
                tags=["preprocessing"],
                name="preprocess_fun",
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


@pytest.fixture
def fused_pipeline_complex() -> Pipeline:
    return Pipeline(
        [
            KedroNode(
                func=lambda x: x,
                inputs="raw_data",
                outputs="data",
                tags=["preprocessing"],
                name="preprocess_fun",
            ),
            KedroNode(
                func=lambda x: x,
                inputs="raw_customers",
                outputs="customers",
                tags=["preprocessing"],
                name="preprocess_customers",
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
                        func=lambda x, y: x,
                        inputs=["model", "customers"],
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


def test_get_argo_dag(pipeline: Pipeline, machine_types: dict[str, MachineType], default_machine_type: str):

    # When generating the argo DAG
    argo_dag = get_argo_dag(pipeline, machine_types, default_machine_type)
    expected = {
        "preprocess_fun": { 
            "name": "preprocess-fun",
            "nodes": "preprocess_fun",
            "deps": [],
            "mem": 16,
            "cpu": 4,
            "num_gpu": 0,
        },
        "train_fun": {
            "name": "train-fun",
            "nodes": "train_fun",
            "deps": ["preprocess-fun"],
            "mem": 16,
            "cpu": 8,
            "num_gpu": 0,
        }
    }

    # Assert resulting argo dag is correct
    assert {key: task.to_dict() for key,task in argo_dag.items()} == expected


def test_get_argo_dag_fused(fused_pipeline: Pipeline, machine_types: dict[str, MachineType], default_machine_type: str):

    # When generating the argo DAG
    argo_dag = get_argo_dag(fused_pipeline, machine_types, default_machine_type)
    expected = {
        "preprocess_fun": { 
            "name": "preprocess-fun",
            "nodes": "preprocess_fun",
            "deps": [],
            "mem": 16,
            "cpu": 2,
            "num_gpu": 0,
        },
        "fused_modelling": {
            "name": "fused-modelling",
            "nodes": "fused_modelling",
            "deps": ["preprocess-fun"],
            "mem": 16,
            "cpu": 8,
            "num_gpu": 0,
        }
    }

    # Assert resulting argo dag is correct
    assert {key: task.to_dict() for key,task in argo_dag.items()} == expected
    

def test_get_argo_dag_fused_complex(fused_pipeline_complex: Pipeline, machine_types: dict[str, MachineType], default_machine_type: str):

    # When generating the argo DAG
    argo_dag = get_argo_dag(fused_pipeline_complex, machine_types, default_machine_type)
    expected = {
        "preprocess_fun": { 
            "name": "preprocess-fun",
            "nodes": "preprocess_fun",
            "deps": [],
            "mem": 16,
            "cpu": 2,
            "num_gpu": 0,
        },
        "preprocess_customers": { 
            "name": "preprocess-customers",
            "nodes": "preprocess_customers",
            "deps": [],
            "mem": 16,
            "cpu": 2,
            "num_gpu": 0,
        },
        "fused_modelling": {
            "name": "fused-modelling",
            "nodes": "fused_modelling",
            "deps": ["preprocess-customers", "preprocess-fun"],
            "mem": 16,
            "cpu": 8,
            "num_gpu": 0,
        }
    }

    # Assert resulting argo dag is correct
    assert {key: task.to_dict() for key,task in argo_dag.items()} == expected


def test_get_argo_dag_gpu(machine_types: dict[str, MachineType], default_machine_type: str):
    """Test that tasks with num_gpu > 0 get the kedro-gpu template."""
    pipeline = Pipeline(
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
                machine_type="gpu-node",
            ),
        ]
    )

    argo_dag = get_argo_dag(pipeline, machine_types, default_machine_type)
    expected = {
        "preprocess_fun": {
            "name": "preprocess-fun",
            "nodes": "preprocess_fun",
            "deps": [],
            "mem": 16,
            "cpu": 2,
            "num_gpu": 0,
        },
        "train_fun": {
            "name": "train-fun",
            "nodes": "train_fun",
            "deps": ["preprocess-fun"],
            "mem": 32,
            "cpu": 8,
            "num_gpu": 1,
        }
    }

    assert {key: task.to_dict() for key, task in argo_dag.items()} == expected
    