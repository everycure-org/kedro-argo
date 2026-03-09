from typing import List, Optional
from pydantic import BaseModel, Field


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
    dockerfile: str = "Dockerfile"

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
