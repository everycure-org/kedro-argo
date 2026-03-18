from typing import List, Optional
from pydantic import BaseModel, Field


class RunnerConfig(BaseModel):

    use_memory_datasets: bool = False

class MachineType(BaseModel):
    mem: int
    cpu: int
    num_gpu: int
    emph_storage: int = Field(default=10)

class DeploymentConfig(BaseModel):
    image: str
    tag: str = "latest"
    target_platform: str = "linux/amd64"
    context: str = "./"
    dockerfile: str = "Dockerfile"

class SecretRef(BaseModel):
    name: str
    key: str
    path: str | None = None

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
    parameters: List[TemplateOutputRef] = Field(default=[])

class TemplateContainerRef(BaseModel):
    name: str
    command: List[str]
    env: List[EnvironmentRef] = Field(default=[])
    args: str

class VolumeMountRef(BaseModel):
    name: str
    mount_path: str
    read_only: bool = True

class TemplateSidecarRef(BaseModel):
    image: str
    name: str
    env: List[EnvironmentRef] = Field(default=[])
    volume_mounts: List[VolumeMountRef] = Field(default=[])

class VolumeRef(BaseModel):
    name: str
    secret_ref: SecretRef

class TemplateRef(BaseModel):
    name: str
    container: TemplateContainerRef
    outputs: TemplateOutputsRef = Field(default=TemplateOutputsRef())
    sidecars: List[TemplateSidecarRef] = Field(default=[])
    volumes: List[VolumeRef] = Field(default=[])

class TemplateConfig(BaseModel):

    templates: List[TemplateRef] = Field(default=[])
    environment: List[EnvironmentRef] = Field(default=[])
    init_templates: List[str] = Field(default=[])
    emph_storage_mount_path: str = Field(default="/data")
    default_template: str = Field(default="kedro")

class ArgoConfig(BaseModel):
    namespace: str
    deployment: DeploymentConfig
    machine_types: dict[str, MachineType]
    default_machine_type: str
    runner: RunnerConfig
    template: Optional[TemplateConfig] = Field(default=TemplateConfig())
