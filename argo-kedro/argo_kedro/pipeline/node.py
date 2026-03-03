from typing import Any, Callable, Iterable

from kedro.pipeline import Node as KedroNode

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

    def _copy(self, **overwrite_params: Any) -> "Node":
        """Copy node while preserving Argo-specific metadata.

        Kedro's default ``Node._copy`` returns a base Kedro Node, which would
        drop the ``machine_type`` attribute used by argo-kedro.
        """
        params = {
            "func": self._func,
            "inputs": self._inputs,
            "outputs": self._outputs,
            "name": self._name,
            "namespace": self._namespace,
            "tags": self._tags,
            "confirms": self._confirms,
            "machine_type": self._machine_type,
        }
        params.update(overwrite_params)
        return Node(**params)