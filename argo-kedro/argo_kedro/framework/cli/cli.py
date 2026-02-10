import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Iterable, Union
from logging import getLogger

import click
import yaml
from kubernetes import config
from kubernetes.dynamic import DynamicClient
from jinja2 import Environment, FileSystemLoader
from kedro.framework.cli.utils import CONTEXT_SETTINGS
from kedro.framework.project import settings
from kedro.framework.session import KedroSession
from kedro.framework.startup import bootstrap_project
from kedro.utils import find_kedro_project, is_kedro_project
from kedro.framework.cli.project import TAG_ARG_HELP
from kedro.framework.project import pipelines as kedro_pipelines
from kedro.pipeline import Pipeline
from argo_kedro.runners.fuse_runner import FusedRunner
from argo_kedro.framework.hooks.argo_hook import MachineType
from argo_kedro.pipeline.node import Node

LOGGER = getLogger(__name__)
ARGO_TEMPLATES_DIR_PATH = Path(__file__).parent.parent.parent / "templates"


def render_jinja_template(
    src: Union[str, Path],
    trim_blocks: bool = False,
    lstrip_blocks: bool = False,
    keep_trailing_newline: bool = True,
    **kwargs
) -> str:
    """Render a Jinja2 template file with the provided values.

    Args:
        src: The path to the template file to render
        trim_blocks: If True, remove the first newline after a block
        lstrip_blocks: If True, strip leading spaces and tabs from the start of a line
        keep_trailing_newline: If True, preserve trailing newlines
        **kwargs: Variables to pass to the template for rendering

    Returns:
        A string containing the rendered template with replaced tags.
    """
    src = Path(src)
    template_loader = FileSystemLoader(searchpath=src.parent.as_posix())
    template_env = Environment(
        loader=template_loader,
        trim_blocks=trim_blocks,
        lstrip_blocks=lstrip_blocks,
        keep_trailing_newline=keep_trailing_newline,
    )
    template = template_env.get_template(src.name)
    return template.render(**kwargs)


def write_jinja_template(
    src: Union[str, Path],
    dst: Union[str, Path],
    trim_blocks: bool = False,
    lstrip_blocks: bool = False,
    keep_trailing_newline: bool = True,
    **kwargs
) -> None:
    """Write a rendered Jinja2 template to a file.

    Args:
        src: Path to the template file to render
        dst: Path where the rendered template should be saved
        trim_blocks: If True, remove the first newline after a block
        lstrip_blocks: If True, strip leading spaces and tabs from the start of a line
        keep_trailing_newline: If True, preserve trailing newlines
        **kwargs: Variables to pass to the template for rendering
    """
    dst = Path(dst)
    parsed_template = render_jinja_template(
        src,
        trim_blocks=trim_blocks,
        lstrip_blocks=lstrip_blocks,
        keep_trailing_newline=keep_trailing_newline,
        **kwargs
    )
    with open(dst, "w") as file_handler:
        file_handler.write(parsed_template)


@click.group(context_settings=CONTEXT_SETTINGS)
def cli():
    pass

@cli.command(name="run")
@click.option("--pipeline", "-p", type=str, default="__default__", help="Name of the pipeline to execute")
@click.option("--env", "-e", type=str, default=None, help="Kedro environment to run the pipeline in")
@click.option("--config", "-c", type=str, multiple=True, help="Extra config to pass to KedroContext")
@click.option("--params", type=str, multiple=True, help="Override parameters")
@click.option("--tags", "-t", type=str, multiple=True, help=TAG_ARG_HELP)
@click.option("--nodes", "-n", type=str, multiple=True, help="Run only nodes with specified names")
@click.option("--to-nodes", type=str, multiple=True, help="Run a sub-pipeline up to certain nodes")
@click.option("--from-nodes", type=str, multiple=True, help="Run a sub-pipeline starting from certain nodes")
@click.option("--from-inputs", type=str, multiple=True, help="Run a sub-pipeline starting from nodes that produce these inputs")
@click.option("--to-outputs", type=str, multiple=True, help="Run a sub-pipeline up to nodes that produce these outputs")
@click.option("--load-version", type=str, multiple=True, help="Specify a particular dataset version")
@click.option("--namespaces", type=str, multiple=True, help="Namespaces of the pipeline")
@click.pass_obj
def _run_command_impl(
    ctx,
    pipeline: str,
    env: str,
    config: tuple,
    params: tuple,
    tags: list[str],
    nodes: tuple,
    to_nodes: tuple,
    from_nodes: tuple,
    from_inputs: tuple,
    to_outputs: tuple,
    load_version: tuple,
    namespaces: Iterable[str],
):    
    """Run the pipeline with the FusedRunner."""

    LOGGER.warning(f"Using plugin entrypoint")
    
    load_versions = None
    if load_version:
        load_versions = {}
        for version_spec in load_version:
            if ":" in version_spec:
                dataset, version = version_spec.split(":", 1)
                load_versions[dataset] = version

    conf_source = getattr(ctx, "conf_source", None)
    env_value = env or getattr(ctx, "env", None)

    with KedroSession.create(
        env=env_value,
        conf_source=conf_source,
    ) as session:

        context = session.load_context()

        session.run(
            pipeline_name=pipeline,
            tags=tags,
            runner=FusedRunner(pipeline_name=pipeline, use_memory_datasets=context.argo.runner.use_memory_datasets),
            node_names=list(nodes) if nodes else None,
            from_nodes=list(from_nodes) if from_nodes else None,
            to_nodes=list(to_nodes) if to_nodes else None,
            from_inputs=list(from_inputs) if from_inputs else None,
            to_outputs=list(to_outputs) if to_outputs else None,
            load_versions=load_versions,
            namespaces=namespaces,
        )

class KedroClickGroup(click.Group):
    def reset_commands(self):
        self.commands = {}

        # add commands on the fly based on conditions
        if is_kedro_project(find_kedro_project(Path.cwd())):
            self.add_command(init)
            self.add_command(submit)

    def list_commands(self, ctx):
        self.reset_commands()
        commands_list = sorted(self.commands)
        return commands_list

    def get_command(self, ctx, cmd_name):
        self.reset_commands()
        return self.commands.get(cmd_name)

@click.group(name="argo")
def commands():
    pass

@commands.command(name="argo", cls=KedroClickGroup)
def argo_commands():
    """Use argo-specific commands inside kedro project."""
    pass  # pragma: no cover

@argo_commands.command()
@click.option(
    "--env",
    "-e",
    default="base",
    help="The name of the kedro environment where the 'argo.yml' should be created. Default to 'base'",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Update the template without any checks.",
)
@click.option(
    "--silent",
    "-s",
    is_flag=True,
    default=False,
    help="Should message be logged when files are modified?",
)
def init(env: str, force: bool, silent: bool):
    """Updates the template of a kedro project.
    Running this command is mandatory to use argo-kedro.
    This adds "conf/base/argo.yml": This is a configuration file
    used for run parametrization when calling "kedro run" command.
    """

    # get constants
    argo_yml = "argo.yml"
    project_path = find_kedro_project(Path.cwd()) or Path.cwd()
    project_metadata = bootstrap_project(project_path)
    argo_yml_path = project_path / settings.CONF_SOURCE / env / argo_yml

    if argo_yml_path.is_file() and not force:
        click.secho(
            click.style(
                f"A 'argo.yml' already exists at '{argo_yml_path}' You can use the ``--force`` option to override it.",
                fg="red",
            )
        )
    else:
        try:
            write_jinja_template(
                src=ARGO_TEMPLATES_DIR_PATH / argo_yml,
                dst=argo_yml_path,
                python_package=project_metadata.package_name,
            )
            if not silent:
                click.secho(
                    click.style(
                        f"'{settings.CONF_SOURCE}/{env}/{argo_yml}' successfully updated.",
                        fg="green",
                    )
                )
        except FileNotFoundError:
            click.secho(
                click.style(
                    f"No env '{env}' found. Please check this folder exists inside '{settings.CONF_SOURCE}' folder.",
                    fg="red",
                )
            )

def publish_image(image: str, tag: str, project_path: Path, platform: str = "linux/amd64", context: str = "./") -> str:
    """Build and push the Docker image.
    
    Args:
        image: The image name (without tag)
        tag: The image tag
        project_path: Path to the project root
        platform: Target platform for the image
        context: Docker build context directory (relative to project_path or absolute)
        
    Returns:
        The full image name with tag
    """
    full_image = f"{image}:{tag}"
    
    LOGGER.info(f"Building Docker image: {full_image}")
    
    # Build the image
    build_cmd = [
        "docker", "buildx", "build",
        "--progress=plain",
        "--platform", platform,
        "-t", image,
        "--load",
        context
    ]
    
    LOGGER.info(f"Running: {' '.join(build_cmd)}")
    result = subprocess.run(build_cmd, cwd=project_path)
    if result.returncode != 0:
        raise click.ClickException(f"Docker build failed with exit code {result.returncode}")
    
    # Tag the image
    tag_cmd = ["docker", "tag", image, full_image]
    LOGGER.info(f"Running: {' '.join(tag_cmd)}")
    result = subprocess.run(tag_cmd, cwd=project_path)
    if result.returncode != 0:
        raise click.ClickException(f"Docker tag failed with exit code {result.returncode}")
    
    # Push the image
    push_cmd = ["docker", "push", full_image]
    LOGGER.info(f"Running: {' '.join(push_cmd)}")
    result = subprocess.run(push_cmd, cwd=project_path)
    if result.returncode != 0:
        raise click.ClickException(f"Docker push failed with exit code {result.returncode}")
    
    click.secho(f"Successfully published image: {full_image}", fg="green")
    return full_image

@argo_commands.command(name="submit")
@click.option("--pipeline", "-p", type=str, default="__default__", help="Specify which pipeline to execute")
@click.option("--environment", "-e", type=str, default="cloud", help="Kedro environment to execute in")
@click.pass_obj
def submit(
    ctx,
    pipeline: str,
    environment: str
):
    """Submit the pipeline to Argo."""
    project_path = find_kedro_project(Path.cwd()) or Path.cwd()
    bootstrap_project(project_path)
    
    with KedroSession.create(
        project_path=project_path,
        env=environment,
    ) as session:
        context = session.load_context()
        
        # Build and push the image
        image = publish_image(
            image=context.argo.deployment.image,
            tag=context.argo.deployment.tag,
            project_path=project_path,
            platform=context.argo.deployment.target_platform,
            context=context.argo.deployment.context,
        )
        
        pipeline_tasks = get_argo_dag(
            kedro_pipelines[pipeline], 
            machine_types=context.argo.machine_types,
            default_machine_type=context.argo.default_machine_type
        )

        # Render the template
        LOGGER.info("Rendering Argo workflow spec...")
        rendered_template = render_jinja_template(
            src=ARGO_TEMPLATES_DIR_PATH / "argo_wf_spec.tmpl",
            trim_blocks=True,
            lstrip_blocks=True,
            pipeline_tasks=[task.to_dict() for task in pipeline_tasks.values()],
            pipeline_name=pipeline,
            image=image,
            namespace=context.argo.namespace,
            environment=environment
        )

        # Load as yaml
        yaml_data = yaml.safe_load(rendered_template)
        yaml_without_anchors = yaml.dump(yaml_data, sort_keys=False, default_flow_style=False)
        save_argo_template(
            yaml_without_anchors,
        )

        # Use kubeconfig to submit to kubernetes
        config.load_kube_config()
        client = DynamicClient(config.new_client_from_config())

        resource = client.resources.get(
            api_version=yaml_data["apiVersion"],
            kind=yaml_data["kind"],
        )

        response = resource.create(
            body=yaml_data,
            namespace=context.argo.namespace
        )
        
        workflow_name = response.metadata.name
        LOGGER.info(f"Workflow submitted successfully: {workflow_name}")
        LOGGER.info(f"View workflow at: https://argo.ai-platform.dev.everycure.org/workflows/{context.argo.namespace}/{workflow_name}")
        
        return workflow_name


def save_argo_template(argo_template: str) -> str:
    file_path = Path("templates") / "argo-workflow-template.yml"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w") as f:
        f.write(argo_template)
    return str(file_path)


class ArgoTask:
    """Class to model an Argo task.

    Argo's operating model slightly differs from Kedro's, i.e., while Kedro uses dataset
    dependencies to model relationships, Argo uses task dependencies."""

    def __init__(self, node: Node, machine_type: MachineType):
        self._node = node
        self._parents = []
        self._machine_type = machine_type

    @property
    def node(self):
        return self._node

    def add_parents(self, nodes: List[Node]):
        self._parents.extend(nodes)

    def to_dict(self):
        return {
            "name": clean_name(self._node.name),
            "nodes": self._node.name,
            "deps": [clean_name(parent.name) for parent in sorted(self._parents)],
            "mem": self._machine_type.mem,
            "cpu": self._machine_type.cpu,
            "num_gpu": self._machine_type.num_gpu,
        }


def get_argo_dag(
    pipeline: Pipeline, 
    machine_types: dict[str, MachineType],
    default_machine_type: str,
) -> List[Dict[str, Any]]:
    """Function to convert the Kedro pipeline into Argo Tasks. The function
    iterates the nodes of the pipeline and generates Argo tasks with dependencies.
    These dependencies are inferred based on the input and output datasets for
    each node.

    NOTE: This function is now agnostic to the fact that nodes might be fused. The nodes
    returned as part of the pipeline may optionally contain FusedNodes, which have correct
    inputs and outputs for the perspective of the Argo Task.
    """
    tasks = {}

    # The `grouped_nodes` property returns the nodes list, in a toplogical order,
    # allowing us to easily translate the Kedro DAG to an Argo WF.
    for group in pipeline.grouped_nodes:
        for target_node in group:
            try:
                task = ArgoTask(target_node, machine_types[target_node.machine_type] if isinstance(target_node, Node) and target_node.machine_type is not None else machine_types[default_machine_type])
            except KeyError as e:
                LOGGER.error(f"Machine type not found for node `{target_node.name}`")
                raise KeyError(f"Machine type `{target_node.machine_type}` not found for node `{target_node.name}`")
            
            task.add_parents(
                [
                    parent.node
                    for parent in tasks.values()
                    if set(clean_dependencies(target_node.inputs)) & set(clean_dependencies(parent.node.outputs))
                ]
            )

            tasks[target_node.name] = task

    return tasks


def clean_name(name: str) -> str:
    """Function to clean the node name.

    Args:
        name: name of the node
    Returns:
        Clean node name, according to Argo's requirements
    """
    return re.sub(r"[\W_]+", "-", name).strip("-")


def clean_dependencies(elements) -> List[str]:
    """Function to clean node dependencies.

    Operates by removing `params:` from the list and dismissing
    the transcoding operator.
    """
    return [el.split("@")[0] for el in elements if not el.startswith("params:")]