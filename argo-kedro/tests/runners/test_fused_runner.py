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
                        func=lambda x, y: y,
                        inputs=["raw_data", "data"],
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
                    KedroNode(
                        func=lambda x: x,
                        inputs=["model"],
                        outputs="report",
                        tags=["predictions"],
                        name="create_report",
                    ),
                ],
                name="fused_modelling",
                machine_type="n1-standard-8",
            ),
        ]
    )


@pytest.mark.parametrize("use_memory_datasets", [False, True])
def test_run_fused_runner(monkeypatch: pytest.MonkeyPatch, fused_pipeline_complex: Pipeline, use_memory_datasets: bool):
    
    # Given a pipeline and data catalog
    monkeypatch.setitem(project_pipelines, "fused_pipeline_complex", fused_pipeline_complex)
    catalog = DataCatalog(
        {
            "raw_data": MemoryDataset(pd.DataFrame({"raw_data": [1, 2]})),
            "raw_customers": MemoryDataset(pd.DataFrame({"raw_customers": ["a", "b"]})),
        }
    )

    runner = FusedRunner(
        pipeline_name="fused_pipeline_complex",
        use_memory_datasets=use_memory_datasets,
    )

    # When running the pipeline
    runner.run(
        pipeline=fused_pipeline_complex,
        catalog=catalog,
    )


    # Then results materialized correctly
    expected_predictions = pd.DataFrame({"raw_data": [1, 2]})
    pd.testing.assert_frame_equal(catalog.load("predictions"), expected_predictions)