from kedro.pipeline import Node, Pipeline
from argo_kedro.pipeline import FusedPipeline, ArgoNode

from .nodes import create_model_input_table, preprocess_companies, preprocess_shuttles


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        FusedPipeline(
            [
                ArgoNode(
                    func=preprocess_companies,
                    inputs="companies",
                    outputs="preprocessed_companies",
                    name="preprocess_companies_node",
                    machine_type="n1-standard-4"
                ),
                Node(
                    func=preprocess_shuttles,
                    inputs="shuttles",
                    outputs="preprocessed_shuttles",
                    name="preprocess_shuttles_node",
                ),
                Node(
                    func=create_model_input_table,
                    inputs=["preprocessed_shuttles", "preprocessed_companies", "reviews"],
                    outputs="model_input_table",
                    name="create_model_input_table_node",
                ),
            ],
            name="data_processing_fused"
        )
    )
