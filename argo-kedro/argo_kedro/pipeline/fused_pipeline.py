from typing import Iterable, List
from kedro.pipeline import Pipeline
from functools import cached_property
from argo_kedro.pipeline.node import Node
from kedro.pipeline.node import Node as KedroNode

class FusedNode(Node):
    """FusedNode is an extension of Kedro's internal node. The FusedNode
    wraps a set of nodes, and correctly sets it's `inputs` and `outputs`
    allowing it to act as a single unit for execution.
    """

    def __init__(
        self, 
        nodes: List[KedroNode], 
        name: str, 
        machine_type: str | None = None,
        template: str | None = None
    ):
        self._nodes = nodes
        self._name = name
        self._namespace = None
        self._inputs = set()
        self._outputs = set()
        self._confirms = []
        self._func = lambda: None
        self._tags = set()
        self._machine_type = machine_type
        self._template = template

        for node in nodes:
            self._inputs.update(node.inputs)
            self._outputs.update(node.outputs)
            self._tags.update(node._tags)

        # NOTE: Exclude ouputs made as part of the intermediate nodes
        self._inputs -= self._outputs
        self._inputs = list(self._inputs)
        self._outputs = list(self._outputs)
        self._tags = list(self._tags)

    @cached_property
    def inputs(self) -> list[str]:
        return self._inputs

    @property
    def machine_type(self) -> str:
        return self._machine_type

    @property
    def template(self) -> str:
        return self._template

    @cached_property
    def outputs(self) -> list[str]:
        return self._outputs

class FusedPipeline(Pipeline):
    """Fused pipeline allows for wrapping nodes for execution by the underlying
    pipeline execution framework.

    This is needed, as Kedro immediately translates a pipeline to a list of nodes
    to execute, where any pipeline structure is flatmapped. The FusedPipeline produces
    a _single_ FusedNode that contains the wrapped nodes."""

    def __init__(
        self,
        nodes: Iterable[KedroNode | Pipeline],
        name: str,
        *,
        tags: str | Iterable[str] | None = None,
        machine_type: str | None = None,
        template: str | None = None
    ):
        self._name = name
        self._machine_type = machine_type
        self._template = template
        super().__init__(nodes, tags=tags)

    @property
    def nodes(self) -> list[KedroNode]:
        return [FusedNode(self._nodes, name=self._name, machine_type=self._machine_type, template=self._template)]

    @cached_property
    def grouped_nodes(self) -> list[list[KedroNode]]:
        """Return a list of the pipeline nodes in topologically ordered groups.
        
        For FusedPipeline, since we only have a single FusedNode, we return
        it as a single group.
        """
        return [[FusedNode(self._nodes, name=self._name, machine_type=self._machine_type, template=self._template)]]