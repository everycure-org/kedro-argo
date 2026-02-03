import pytest

from kedro.pipeline import Pipeline, node
from argo_kedro.pipeline.fused_pipeline import FusedPipeline, FusedNode

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


def test_fused_node_inputs(pipeline: Pipeline):

    # Wrap pipeline in FusedNode
    fused_node = FusedNode(pipeline.nodes, name="fused_node")

    # Assert that the fused node inputs are the pure inputs of the pipeline, i.e.,
    # all inputs not produced as part of intermediate nodes.
    assert set(fused_node.inputs) == set(["raw_data"])


def test_fused_pipeline_nodes(pipeline: Pipeline):

    # Wrap pipeline in FusedPipeline
    fused_pipeline = FusedPipeline(pipeline.nodes, name="fused_pipeline")

    # Assert that the fused pipeline nodes are the same as the pipeline nodes
    assert len(fused_pipeline.nodes) == 1
    assert isinstance(fused_pipeline.nodes[0], FusedNode)