import re

from kedro.pipeline import Pipeline

from argo_kedro.config.kedro_argo_config import MachineType, TemplateConfig
from argo_kedro.pipeline.node import Node


class ArgoTask:
    """Model a translated Argo task."""

    def __init__(self, node: Node, machine_type: MachineType, template: str):
        self._node = node
        self._parents = []
        self._machine_type = machine_type
        self._template = template

    @property
    def name(self):
        return clean_name(self._node.name)

    @property
    def node(self):
        return self._node

    @property
    def machine_type(self) -> MachineType:
        return self._machine_type

    @property
    def template(self) -> str:
        return self._template

    @property
    def deps(self) -> list[str]:
        return [clean_name(parent.name) for parent in sorted(self._parents)],

    def add_parents(self, nodes: list[Node]):
        self._parents.extend(nodes)


def get_argo_dag(
    pipeline: Pipeline,
    machine_types: dict[str, MachineType],
    default_machine_type: str,
    template_config: TemplateConfig,
) -> dict[str, ArgoTask]:
    """Convert a Kedro pipeline to Argo tasks with DAG dependencies."""
    tasks: dict[str, ArgoTask] = {}

    # `grouped_nodes` is topologically sorted, which maps naturally
    # to Argo task dependency resolution.
    for group in pipeline.grouped_nodes:
        for target_node in group:
            machine_type_name = (
                target_node.machine_type
                if isinstance(target_node, Node) and target_node.machine_type is not None
                else default_machine_type
            )

            try:
                task = ArgoTask(
                    target_node, 
                    machine_types[machine_type_name],
                    # TODO: Check if this template is defined
                    target_node.template if isinstance(target_node, Node) and target_node.template is not None else template_config.default_template
                )
            except KeyError as error:
                raise KeyError(
                    f"Machine type `{machine_type_name}` not found for node `{target_node.name}`"
                ) from error

            task.add_parents(
                [
                    parent.node
                    for parent in tasks.values()
                    if set(clean_dependencies(target_node.inputs))
                    & set(clean_dependencies(parent.node.outputs))
                ]
            )

            tasks[target_node.name] = task

    return tasks


def clean_name(name: str) -> str:
    """Clean node names to satisfy Argo naming requirements."""
    return re.sub(r"[\W_]+", "-", name).strip("-")


def clean_dependencies(elements) -> list[str]:
    """Normalize dependencies by removing params and transcoding suffixes."""
    return [el.split("@")[0] for el in elements if not el.startswith("params:")]
