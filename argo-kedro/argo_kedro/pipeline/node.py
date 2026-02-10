from kedro.pipeline import Node as KedroNode
from typing import Callable, Iterable

class Node(KedroNode):
    """ArgoNode is an extension of the Kedro node class, aimed at allowing
    the node to be allocated to a specific machine type.
    """
    def __init__(
        self,
        func: Callable,
        inputs: str | list[str] | dict[str, str] | None,
        outputs: str | list[str] | dict[str, str] | None,
        *,
        name: str | None = None,
        machine_type: str | None = None,
        tags: str | Iterable[str] | None = None,
        confirms: str | list[str] | None = None,
        namespace: str | None = None,
    ):

        super().__init__(func, inputs, outputs, name=name, tags=tags, confirms=confirms, namespace=namespace)
        self._machine_type = machine_type

    @property
    def machine_type(self) -> str:
        return self._machine_type