from logging import Logger, getLogger
from typing import List, Optional

from omegaconf import OmegaConf
from kedro.config import MissingConfigException
from kedro.framework.context import KedroContext
from kedro.framework.hooks import hook_impl

from argo_kedro.config.resolvers import random
from argo_kedro.config import ArgoConfig

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

        if not OmegaConf.has_resolver("ka.random_name"):
            OmegaConf.register_new_resolver(
                "ka.random", random, use_cache=True
            )

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
