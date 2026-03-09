import re
import subprocess
from pathlib import Path
from typing import Any, Iterable, Union

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
from argo_kedro.config.resolvers import random
from argo_kedro.config.kedro_argo_config import ArgoConfig, MachineType, TemplateConfig
from argo_kedro.pipeline.node import Node

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


def copy_file(src: Union[str, Path], dst: Union[str, Path]) -> None:
    """Copy a file from source to destination.

    Args:
        src: Path to the source file to copy
        dst: Path where the file should be copied to
    """
    src = Path(src)
    dst = Path(dst)
    
    with open(src, "r") as src_file:
        content = src_file.read()
    
    with open(dst, "w") as dst_file:
        dst_file.write(content)


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

    click.echo("Using plugin entrypoint")
    
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
            self.add_command(resubmit)

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
    
    # Prompt user about Dockerfile
    dockerfile_path = project_path / "Dockerfile"
    if dockerfile_path.is_file() and not force:
        if not silent:
            click.secho(
                click.style(
                    f"A 'Dockerfile' already exists at '{dockerfile_path}'. You can use the ``--force`` option to override it.",
                    fg="yellow",
                )
            )
    else:
        if force or click.confirm("Do you want to add a Dockerfile to the project root?"):
            try:
                dockerfile_template_path = ARGO_TEMPLATES_DIR_PATH / "Dockerfile"
                if dockerfile_template_path.is_file():
                    copy_file(dockerfile_template_path, dockerfile_path)
                    if not silent:
                        click.secho(
                            click.style(
                                f"'Dockerfile' successfully added to project root.",
                                fg="green",
                            )
                        )
                else:
                    click.secho(
                        click.style(
                            f"Dockerfile template not found at '{dockerfile_template_path}'.",
                            fg="red",
                        )
                    )
            except Exception as e:
                click.secho(
                    click.style(
                        f"Error creating Dockerfile: {str(e)}",
                        fg="red",
                    )
                )
    
    # Prompt user about .dockerignore
    dockerignore_path = project_path / ".dockerignore"
    if dockerignore_path.is_file() and not force:
        if not silent:
            click.secho(
                click.style(
                    f"A '.dockerignore' already exists at '{dockerignore_path}'. You can use the ``--force`` option to override it.",
                    fg="yellow",
                )
            )
    else:
        if force or click.confirm("Do you want to add a .dockerignore to the project root?"):
            try:
                dockerignore_template_path = ARGO_TEMPLATES_DIR_PATH / ".dockerignore"
                if dockerignore_template_path.is_file():
                    copy_file(dockerignore_template_path, dockerignore_path)
                    if not silent:
                        click.secho(
                            click.style(
                                f"'.dockerignore' successfully added to project root.",
                                fg="green",
                            )
                        )
                else:
                    click.secho(
                        click.style(
                            f".dockerignore template not found at '{dockerignore_template_path}'.",
                            fg="red",
                        )
                    )
            except Exception as e:
                click.secho(
                    click.style(
                        f"Error creating .dockerignore: {str(e)}",
                        fg="red",
                    )
                )

def publish_image(full_image: str, project_path: Path, platform: str, context: str, dockerfile: str) -> str:
    """Build and push the Docker image.
    
    Args:
        full_image: The full image name with tag (e.g., "myimage:latest")
        project_path: Path to the project root
        platform: Target platform for the image
        context: Docker build context directory (relative to project_path or absolute)
        dockerfile: The name of the Dockerfile to use
    Returns:
        The full image name with tag
    """
    click.echo(f"Building Docker image: {full_image}")

    # Resolve the Dockerfile path — always use the one in the project root
    dockerfile_path = project_path / dockerfile
    
    # Build the image
    build_cmd = [
        "docker", "buildx", "build",
        "--progress=plain",
        "--platform", platform,
        "-f", str(dockerfile_path),
        "-t", full_image,
        "--load",
        context
    ]
    
    click.echo(f"Running: {' '.join(build_cmd)}")
    result = subprocess.run(build_cmd, cwd=project_path)
    if result.returncode != 0:
        raise click.ClickException(f"Docker build failed with exit code {result.returncode}")
    
    # Push the image
    push_cmd = ["docker", "push", full_image]
    click.echo(f"Running: {' '.join(push_cmd)}")
    result = subprocess.run(push_cmd, cwd=project_path)
    if result.returncode != 0:
        raise click.ClickException(f"Docker push failed with exit code {result.returncode}")
    
    click.secho(f"Successfully published image: {full_image}", fg="green")
    return full_image

@argo_commands.command(name="submit")
@click.option("--pipeline", "-p", type=str, default="__default__", help="Specify which pipeline to execute")
@click.option("--environment", "-e", type=str, default="cloud", help="Kedro environment to execute in")
@click.option("--dry_run", "-d", is_flag=True, default=False, help="Dry run submit")
@click.option("--workflow-name", "-w", type=str, default="workflow", help="Custom Argo workflow name")
@click.pass_obj
def submit(
    ctx,
    pipeline: str,
    environment: str,
    dry_run: bool,
    workflow_name: str
):
    """Submit the pipeline to Argo."""
    project_path = find_kedro_project(Path.cwd()) or Path.cwd()
    bootstrap_project(project_path)
    
    with KedroSession.create(
        project_path=project_path,
        env="base", # NOTE: Currently using the base env to avoid cloud related catalog issues
    ) as session:
        context = session.load_context()
        
        # Build and push the image
        image = f"{context.argo.deployment.image}:{context.argo.deployment.tag}"
        if not dry_run:
            publish_image(
                full_image=image,
                project_path=project_path,
                platform=context.argo.deployment.target_platform,
                context=context.argo.deployment.context,
                dockerfile=context.argo.deployment.dockerfile,
            )
        
        pipeline_tasks = get_argo_dag(
            kedro_pipelines[pipeline], 
            machine_types=context.argo.machine_types,
            default_machine_type=context.argo.default_machine_type
        )

        # Render the template
        click.echo("Rendering Argo workflow spec...")
        rendered_template = render_jinja_template(
            src=ARGO_TEMPLATES_DIR_PATH / "argo_wf_spec.tmpl",
            trim_blocks=True,
            lstrip_blocks=True,
            pipeline_tasks=[task.to_dict() for task in pipeline_tasks.values()],
            template=context.argo.template if context.argo.template else TemplateConfig(),
            pipeline_name=pipeline,
            image=image,
            namespace=context.argo.namespace,
            environment=environment,
            workflow_name=workflow_name,
            random=random()
        )

        # Load as yaml
        yaml_data = yaml.safe_load(rendered_template)
        yaml_without_anchors = yaml.dump(yaml_data, sort_keys=False, default_flow_style=False)
        save_argo_template(
            yaml_without_anchors,
        )

        if not dry_run:
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
            click.echo(f"Workflow submitted successfully: {workflow_name}")
            click.echo(f"View workflow at: https://argo.ai-platform.dev.everycure.org/workflows/{context.argo.namespace}/{workflow_name}")


def save_argo_template(argo_template: str) -> str:
    file_path = Path("templates") / "argo-workflow-template.yml"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w") as f:
        f.write(argo_template)
    return str(file_path)


def get_workflow(client: DynamicClient, namespace: str, workflow_name: str) -> Any:
    """Fetch an Argo workflow by name.

    Args:
        client: Kubernetes dynamic client
        namespace: Namespace where the workflow lives
        workflow_name: Name of the workflow to fetch

    Returns:
        The workflow resource object
    """
    resource = client.resources.get(
        api_version="argoproj.io/v1alpha1",
        kind="Workflow",
    )
    return resource.get(name=workflow_name, namespace=namespace)


def get_failed_nodes(workflow: Any) -> list[str]:
    """Extract the names of failed nodes from an Argo workflow.

    Args:
        workflow: The Argo workflow resource object

    Returns:
        List of failed node display names
    """
    failed_nodes = []
    nodes = workflow.get("status", {}).get("nodes", {})
    for node_id, node_info in nodes.items():
        phase = node_info.get("phase", "")
        node_type = node_info.get("type", "")
        if phase in ("Failed", "Error") and node_type == "Pod":
            display_name = node_info.get("displayName", node_info.get("name", node_id))
            failed_nodes.append(display_name)
    return failed_nodes


def _get_workflow_image(workflow: Any) -> str | None:
    """Extract the container image from a workflow's spec templates.

    Prefers the image defined on the ``kedro`` template (the main
    workload), and falls back to the first non-trivial utility image
    (i.e. not ``busybox`` or ``alpine``) if that template is missing
    or does not define an image.

    Returns:
        The full ``image:tag`` string, or ``None`` if not found.
    """
    templates = workflow.get("spec", {}).get("templates", []) or []

    # First, try to get the image from the dedicated ``kedro`` template.
    for tmpl in templates:
        if tmpl.get("name") == "kedro":
            container = tmpl.get("container") or {}
            image = container.get("image")
            if image:
                return image
            # If the kedro template exists but has no image, stop searching
            # for kedro and fall back to the heuristic below.
            break

    # Fallback: keep the existing heuristic of picking the first
    # non-busybox/alpine image from any container template.
    for tmpl in templates:
        container = tmpl.get("container") or {}
        image = container.get("image")
        if not image:
            continue
        base_image = image.split(":", 1)[0]
        if base_image not in ("busybox", "alpine"):
            return image
    return None


@argo_commands.command(name="resubmit")
@click.option("--workflow-name", "-w", type=str, default=None, help="Name of the failed Argo workflow to resubmit")
@click.option("--environment", "-e", type=str, default="cloud", help="Kedro environment to execute in")
@click.option("--rebuild/--no-rebuild", default=True, help="Rebuild and push the Docker image before resubmitting")
def resubmit(
    workflow_name: str | None,
    environment: str,
    rebuild: bool,
):
    """Rebuild the image and retry a failed Argo workflow.

    This command optionally rebuilds and pushes the Docker image, then
    uses ``argo retry`` to re-run only the failed/errored nodes of the
    workflow.  Already-succeeded nodes are skipped.
    """
    project_path = find_kedro_project(Path.cwd()) or Path.cwd()
    bootstrap_project(project_path)

    with KedroSession.create(
        project_path=project_path,
        env=environment,
    ) as session:
        context = session.load_context()
        namespace = context.argo.namespace

        # Connect to the cluster
        config.load_kube_config()
        client = DynamicClient(config.new_client_from_config())

        # Prompt for workflow name if not provided
        if not workflow_name:
            workflow_name = click.prompt("Enter the workflow name to retry")

        # Fetch the workflow
        click.echo(f"\nFetching workflow: {workflow_name}")
        try:
            workflow = get_workflow(client, namespace, workflow_name)
        except Exception as e:
            raise click.ClickException(f"Failed to fetch workflow '{workflow_name}': {e}")

        workflow_phase = workflow.get("status", {}).get("phase", "Unknown")
        if workflow_phase not in ("Failed", "Error"):
            click.secho(
                f"Warning: workflow '{workflow_name}' has phase '{workflow_phase}', not 'Failed' or 'Error'.",
                fg="yellow",
            )
            if not click.confirm("Do you still want to retry this workflow?"):
                return

        # Show failed nodes
        failed_nodes = get_failed_nodes(workflow)
        if failed_nodes:
            click.echo(f"\nFailed nodes ({len(failed_nodes)}):")
            for node_name in failed_nodes:
                click.echo(f"  - {node_name}")
        else:
            click.echo("\nNo individual failed nodes detected (workflow-level failure).")

        # Rebuild image if requested — always use the image from the
        # workflow spec so it matches what the retried pods will pull,
        # regardless of what the current .env / config says.
        if rebuild:
            image = _get_workflow_image(workflow)
            if not image:
                raise click.ClickException(
                    "Could not determine the container image from the workflow spec. "
                    "Please rebuild manually and retry with --no-rebuild."
                )
            click.echo(f"\nRebuilding image (from workflow): {image}")
            publish_image(
                full_image=image,
                project_path=project_path,
                platform=context.argo.deployment.target_platform,
                context=context.argo.deployment.context,
                dockerfile=context.argo.deployment.dockerfile,
            )

        # Retry the workflow using the Argo CLI.
        # `argo retry` resets failed/errored nodes and re-runs them (and
        # their downstream dependents) while skipping already-succeeded
        # nodes.  Because the workflow uses imagePullPolicy: Always, the
        # freshly-pushed image will be pulled automatically.
        click.echo(f"\nRetrying workflow: {workflow_name}")
        cmd = [
            "argo", "retry", workflow_name,
            "--namespace", namespace,
            "--restart-successful=false",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            click.secho(f"\nWorkflow retried successfully: {workflow_name}", fg="green")
            click.echo(
                f"View workflow at: https://argo.ai-platform.dev.everycure.org"
                f"/workflows/{namespace}/{workflow_name}"
            )
            if result.stdout.strip():
                click.echo(result.stdout.strip())
        except FileNotFoundError:
            raise click.ClickException(
                "The 'argo' CLI is not installed or not on PATH. "
                "Install it from https://github.com/argoproj/argo-workflows/releases"
            )
        except subprocess.CalledProcessError as e:
            raise click.ClickException(f"argo retry failed: {e.stderr.strip()}")


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

    def add_parents(self, nodes: list[Node]):
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
) -> dict[str, ArgoTask]:
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
                click.echo(f"Machine type not found for node `{target_node.name}`", err=True)
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


def clean_dependencies(elements) -> list[str]:
    """Function to clean node dependencies.

    Operates by removing `params:` from the list and dismissing
    the transcoding operator.
    """
    return [el.split("@")[0] for el in elements if not el.startswith("params:")]