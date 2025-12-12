from kedro.pipeline import Node, Pipeline
from kedro_argo.runners.fuse_runner import FusedPipeline

from .nodes import create_model_input_table, preprocess_companies, preprocess_shuttles


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        FusedPipeline(
            [
                Node(
                    func=preprocess_companies,
                    inputs="companies",
                    outputs="preprocessed_companies",
                    name="preprocess_companies_node",
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
