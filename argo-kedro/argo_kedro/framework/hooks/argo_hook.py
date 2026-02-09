
import os
import re
from logging import Logger, getLogger
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Union

from kedro.config import MissingConfigException
from kedro.framework.context import KedroContext
from kedro.framework.hooks import hook_impl
from kedro.framework.startup import _get_project_metadata
from kedro.io import CatalogProtocol, DataCatalog
from kedro.pipeline import Pipeline
from kedro.pipeline.node import Node
from omegaconf import OmegaConf


from pydantic import BaseModel


class RunnerConfig(BaseModel):
    use_memory_datasets: bool = False

class MachineType(BaseModel):
    mem: int
    cpu: int
    num_gpu: int

class ArgoConfig(BaseModel):
    namespace: str
    machine_types: dict[str, MachineType]
    default_machine_type: str
    runner: RunnerConfig


class ArgoHook:
    @property
    def _logger(self) -> Logger:
        return getLogger(__name__)

    @hook_impl
    def after_context_created(
        self,
        context: KedroContext,
    ) -> None:
        """Hooks to be invoked after a `KedroContext` is created. This is the earliest
        hook triggered within a Kedro run. The `KedroContext` stores useful information
        such as `credentials`, `config_loader` and `env`.
        Args:
            context: The context that was created.
        """
        try:
            if "argo" not in context.config_loader.config_patterns.keys():
                context.config_loader.config_patterns.update(
                    {"argo": ["argo*", "argo*/**", "**/argo*"]}
                )
            conf_argo_yml = context.config_loader["argo"]
        except MissingConfigException:
            self._logger.warning(
                "No 'argo.yml' config file found in environment. Default configuration will be used. Use ``kedro argo init`` command in CLI to customize the configuration."
            )
            # we create an empty dict to have the same behaviour when the argo.yml
            # is commented out. In this situation there is no MissingConfigException
            # but we got an empty dict
            conf_argo_yml = {}

        conf_argo_yml = ArgoConfig.model_validate(conf_argo_yml)
        context.__setattr__("argo", conf_argo_yml)

argo_hook = ArgoHook()
