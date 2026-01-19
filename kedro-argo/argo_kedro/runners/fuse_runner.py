from kedro.io import DataCatalog
from kedro.framework.project import pipelines
from kedro.pipeline import Pipeline
from kedro.io.memory_dataset import MemoryDataset
from kedro.runner.sequential_runner import SequentialRunner
from pluggy import PluginManager

from kedro_argo.pipeline.fused_pipeline import FusedNode

import os
import re
from pathlib import Path
from typing import Any, Dict, List
from logging import getLogger

import click
import yaml
from kubernetes import config
from kubernetes.dynamic import DynamicClient
from jinja2 import Environment, FileSystemLoader
from kedro.framework.project import pipelines as kedro_pipelines
from kedro.framework.cli.utils import find_run_command
from kedro.pipeline import Pipeline
from kedro.pipeline.node import Node

LOGGER = getLogger(__name__)
ARGO_TEMPLATES_DIR_PATH = Path(__file__).parent.parent.parent / "templates"


class FusedRunner(SequentialRunner):
    """Fused runner is an extension of the SequentialRunner that
    essentially unpacks the FusedNode back to the contained nodes for
    execution."""

    def __init__(
        self,
        is_async: bool = False,
        pipeline_name: str | None = None,
    ):
        """Instantiates the runner class.

        The runner requires access to the pipeline name under execution to correctly handle
        node fusing, as each node during parallell execution is wrapped as a single unit. To
        properly fuse, the runner needs to know the pipeline execution boundary.

        Args:
            is_async: If True, the node inputs and outputs are loaded and saved
                asynchronously with threads. Defaults to False.
            pipeline_name: Name of the pipeline to run.
        """
        self._is_async = is_async
        self._pipeline_name = pipeline_name

    def _run(
        self,
        pipeline: Pipeline,
        catalog: DataCatalog,
        hook_manager: PluginManager,
        session_id: str | None = None,
    ) -> None:
        nodes = pipeline.nodes

        LOGGER.warning(f"Running pipeline: {self._pipeline_name}")

        for node in nodes:
            if isinstance(node, FusedNode):
                pipeline = Pipeline(node._nodes)

                outputs = pipeline.outputs()
                for dataset in pipeline.datasets():

                    found = False
                    for pipeline_node in pipelines[self._pipeline_name].nodes:
                        if node.name != pipeline_node.name:
                            if dataset in pipeline_node.inputs:
                                found = True
                                break

                    if found:
                        print(f"{dataset} found as input to other pipeline node")
                        outputs.append(dataset)

                for dataset in pipeline.datasets().difference(pipeline.inputs().union(outputs)):
                    catalog._datasets[dataset] = MemoryDataset()

        # Invoke super runner
        super()._run(
            Pipeline([Pipeline(node._nodes) if isinstance(node, FusedNode) else node for node in nodes]),
            catalog,
            hook_manager,
            session_id,
        )
