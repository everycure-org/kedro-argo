import pytest

from kedro.pipeline import Pipeline, node
from kedro_argo.pipeline import FusedPipeline
from kedro_argo.framework.cli.cli import get_argo_dag

@pytest.fixture
def pipeline() -> Pipeline:
    return Pipeline(
        [
            node(
                func=lambda x: x,
                inputs="raw_data",
                outputs="data",
                tags=["preprocessing"],
                name="preprocess_fun",
            ),
            node(
                func=lambda x: x,
                inputs="data",
                outputs="model",
                tags=["training"],
                name="train_fun",
            ),
        ]
    )

@pytest.fixture
def fused_pipeline() -> Pipeline:
    return Pipeline(
        [
            node(
                func=lambda x: x,
                inputs="raw_data",
                outputs="data",
                tags=["preprocessing"],
                name="preprocess_fun",
            ),
            FusedPipeline(
                [
                    node(
                        func=lambda x: x,
                        inputs="data",
                        outputs="model",
                        tags=["training"],
                        name="train_fun",
                    ),
                    node(
                        func=lambda x: x,
                        inputs="model",
                        outputs="predictions",
                        tags=["predictions"],
                        name="create_predictions",
                    ),
                ],
                name="fused_modelling",
            ),
        ]
    )


@pytest.fixture
def fused_pipeline_complex() -> Pipeline:
    return Pipeline(
        [
            node(
                func=lambda x: x,
                inputs="raw_data",
                outputs="data",
                tags=["preprocessing"],
                name="preprocess_fun",
            ),
            node(
                func=lambda x: x,
                inputs="raw_customers",
                outputs="customers",
                tags=["preprocessing"],
                name="preprocess_customers",
            ),
            FusedPipeline(
                [
                    node(
                        func=lambda x: x,
                        inputs="data",
                        outputs="model",
                        tags=["training"],
                        name="train_fun",
                    ),
                    node(
                        func=lambda x, y: x,
                        inputs=["model", "customers"],
                        outputs="predictions",
                        tags=["predictions"],
                        name="create_predictions",
                    ),
                ],
                name="fused_modelling",
            ),
        ]
    )


def test_get_argo_dag(pipeline: Pipeline):

    # When generating the argo DAG
    argo_dag = get_argo_dag(pipeline)
    expected = {
        "preprocess_fun": { 
            "name": "preprocess-fun",
            "nodes": "preprocess_fun",
            "deps": [],
        },
        "train_fun": {
            "name": "train-fun",
            "nodes": "train_fun",
            "deps": ["preprocess-fun"],
        }
    }

    # Assert resulting argo dag is correct
    assert {key: task.to_dict() for key,task in argo_dag.items()} == expected


def test_get_argo_dag_fused(fused_pipeline: Pipeline):

    # When generating the argo DAG
    argo_dag = get_argo_dag(fused_pipeline)
    expected = {
        "preprocess_fun": { 
            "name": "preprocess-fun",
            "nodes": "preprocess_fun",
            "deps": [],
        },
        "fused_modelling": {
            "name": "fused-modelling",
            "nodes": "fused_modelling",
            "deps": ["preprocess-fun"],
        }
    }

    # Assert resulting argo dag is correct
    assert {key: task.to_dict() for key,task in argo_dag.items()} == expected
    

def test_get_argo_dag_fused_complex(fused_pipeline_complex: Pipeline):

    # When generating the argo DAG
    argo_dag = get_argo_dag(fused_pipeline_complex)
    expected = {
        "preprocess_fun": { 
            "name": "preprocess-fun",
            "nodes": "preprocess_fun",
            "deps": [],
        },
        "preprocess_customers": { 
            "name": "preprocess-customers",
            "nodes": "preprocess_customers",
            "deps": [],
        },
        "fused_modelling": {
            "name": "fused-modelling",
            "nodes": "fused_modelling",
            "deps": ["preprocess-customers", "preprocess-fun"],
        }
    }

    # Assert resulting argo dag is correct
    assert {key: task.to_dict() for key,task in argo_dag.items()} == expected
    