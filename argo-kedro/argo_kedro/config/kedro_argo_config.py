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
    secret_ref: SecretRef | None = None
    value: str | None = None

class TemplateOutputRef(BaseModel):
    name: str
    path: str

class TemplateOutputsPathsRef(BaseModel):
    name: str
    outputs: List[TemplateOutputRef]

class TemplateOutputsRef(BaseModel):
    parameters: List[TemplateOutputRef]

class TemplateContainerRef(BaseModel):
    name: str
    command: List[str]
    args: str

class TemplateRef(BaseModel):
    name: str
    container: TemplateContainerRef
    outputs: TemplateOutputsRef

class TemplateConfig(BaseModel):

    templates: List[TemplateRef] = Field(default=[])
    environment: List[EnvironmentRef] = Field(default=[])
    init_templates: List[str] = Field(default=[])

class ArgoConfig(BaseModel):
    namespace: str
    deployment: DeploymentConfig
    machine_types: dict[str, MachineType]
    default_machine_type: str
    runner: RunnerConfig
    template: Optional[TemplateConfig] = Field(default=TemplateConfig())
