
import os
import re
from logging import Logger, getLogger
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Union, List, Optional

from kedro.config import MissingConfigException
from kedro.framework.context import KedroContext
from kedro.framework.hooks import hook_impl
from kedro.framework.startup import _get_project_metadata
from kedro.io import CatalogProtocol, DataCatalog
from kedro.pipeline import Pipeline
from kedro.pipeline.node import Node
from omegaconf import OmegaConf

from pydantic import BaseModel, Field


def _load_dotenv(project_path: Path) -> None:
    """Load .env file from the project root into os.environ (if it exists).

    Supports lines of the form KEY=VALUE (with optional quoting).
    Lines starting with # and blank lines are skipped.
    """
    env_file = project_path / ".env"
    if not env_file.is_file():
        return
    with env_file.open() as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            os.environ.setdefault(key, value)


_UNSET = object()


def _oc_env_resolver(key: str, default: Any = _UNSET) -> str:
    """Custom resolver that replicates the built-in ``oc.env`` behaviour.

    Kedro's OmegaConfigLoader clears the built-in ``oc.env`` resolver,
    so we re-register it ourselves.
    """
    value = os.environ.get(key)
    if value is not None:
        return value
    if default is not _UNSET:
        return default
    raise KeyError(f"Environment variable '{key}' is not set and no default was provided")


class RunnerConfig(BaseModel):
    use_memory_datasets: bool = False

class MachineType(BaseModel):
    mem: int
    cpu: int
    num_gpu: int

class DeploymentConfig(BaseModel):
    image: str
    tag: str = "latest"
    target_platform: str = "linux/amd64"
    context: str = "./"

class SecretRef(BaseModel):
    name: str
    key: str

class EnvironmentRef(BaseModel):

    name: str
    secret_ref: SecretRef

class TemplateConfig(BaseModel):

    environment: List[EnvironmentRef] = Field(default=[])

class ArgoConfig(BaseModel):
    namespace: str
    deployment: DeploymentConfig
    machine_types: dict[str, MachineType]
    default_machine_type: str
    runner: RunnerConfig
    template: Optional[TemplateConfig] = Field(default=TemplateConfig())


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
        # Load .env file from the project root so that oc.env resolvers can
        # pick up values such as DOCKER_IMAGE / DOCKER_TAG.
        _load_dotenv(context.project_path)

        # Kedro's OmegaConfigLoader clears the built-in oc.env resolver.
        # Re-register it so that argo.yml (and other configs) can use
        # ${oc.env:VAR_NAME, default} interpolations.
        if not OmegaConf.has_resolver("oc.env"):
            OmegaConf.register_new_resolver("oc.env", _oc_env_resolver)

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
