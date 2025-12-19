from kedro.io import DataCatalog
from kedro.pipeline import Pipeline
from kedro.io.memory_dataset import MemoryDataset
from kedro.runner.sequential_runner import SequentialRunner
from pluggy import PluginManager

from kedro_argo.pipeline.fused_pipeline import FusedNode
class FusedRunner(SequentialRunner):
    """Fused runner is an extension of the SequentialRunner that
    essentially unpacks the FusedNode back to the contained nodes for
    execution."""

    def _run(
        self,
        pipeline: Pipeline,
        catalog: DataCatalog,
        hook_manager: PluginManager,
        session_id: str | None = None,
    ) -> None:
        
        nodes = pipeline.nodes

        # Use memory datasets for intermediate nodes
        # FUTURE: Expose flag?
        for node in nodes:
            if isinstance(node, FusedNode):
                pipeline = Pipeline(node._nodes)
                for dataset in pipeline.datasets().difference(pipeline.inputs().union(pipeline.outputs())):
                    catalog._datasets[dataset] = MemoryDataset()
            

        # Invoke super runner
        super()._run(
            Pipeline([Pipeline(node._nodes) if isinstance(node, FusedNode) else node for node in nodes]),
            catalog,
            hook_manager,
            session_id,
        )
