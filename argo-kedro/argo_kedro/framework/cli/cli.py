import re
from pathlib import Path
from typing import Any, Dict, List, Iterable, Union
from logging import getLogger

import click
import yaml
from kubernetes import config
from kubernetes.dynamic import DynamicClient
from jinja2 import Environment, FileSystemLoader
from kedro.framework.cli.utils import CONTEXT_SETTINGS, KedroCliError
from kedro.framework.project import pipelines, settings
from kedro.framework.session import KedroSession
from kedro.framework.startup import bootstrap_project
from kedro.utils import find_kedro_project, is_kedro_project
from kedro.framework.cli.project import (
    ASYNC_ARG_HELP,
    CONF_SOURCE_HELP,
    FROM_INPUTS_HELP,
    FROM_NODES_HELP,
    LOAD_VERSION_HELP,
    NODE_ARG_HELP,
    PARAMS_ARG_HELP,
    PIPELINE_ARG_HELP,
    RUNNER_ARG_HELP,
    TAG_ARG_HELP,
    TO_NODES_HELP,
    TO_OUTPUTS_HELP,
    project_group,
)
from kedro.framework.project import pipelines as kedro_pipelines
from kedro.pipeline import Pipeline
from kedro.pipeline.node import Node
from kedro.runner.sequential_runner import SequentialRunner
from argo_kedro.runners.fuse_runner import FusedRunner

LOGGER = getLogger(__name__)
ARGO_TEMPLATES_DIR_PATH = Path(__file__).parent.parent.parent / "templates"


def render_jinja_template(
    src: Union[str, Path], **kwargs
) -> str:
    """This functions enable to copy a file and render the
    tags (identified by {{ my_tag }}) with the values provided in kwargs.

    Arguments:
        src {Union[str, Path]} -- The path to the template which should be rendered

    Returns:
        str -- A string that contains all the files with replaced tags.
    """
    src = Path(src)
    template_loader = FileSystemLoader(searchpath=src.parent.as_posix())
    template_env = Environment(loader=template_loader, keep_trailing_newline=True)
    template = template_env.get_template(src.name)
    return template.render(**kwargs)


def write_jinja_template(
    src: Union[str, Path], dst: Union[str, Path], **kwargs
) -> None:
    """Write a template file and replace tis jinja's tags
     (identified by {{ my_tag }}) with the values provided in kwargs.

    Arguments:
        src {Union[str, Path]} -- Path to the template which should be rendered
        dst {Union[str, Path]} -- Path where the rendered template should be saved
    """
    dst = Path(dst)
    parsed_template = render_jinja_template(src, **kwargs)
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

        session.run(
            pipeline_name=pipeline,
            tags=tags,
            runner=FusedRunner(pipeline_name=pipeline),
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
            # self.add_command(run) # TODO : IMPLEMENT THIS FUNCTION
        # else:
        #     self.add_command(new) # TODO : IMPLEMENT THIS FUNCTION

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
    """Use mlflow-specific commands inside kedro project."""
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

    # mlflow.yml is just a static file,
    # but the name of the experiment is set to be the same as the project
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
                is_cookiecutter=False,
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

@argo_commands.command(name="submit")
@click.option("--pipeline", "-p", type=str, default="__default__", help="Specify which pipeline to execute")
@click.option("--environment", "-e", type=str, default="base", help="Kedro environment to execute in")
@click.option("--image", type=str, required=True, help="Image to execute")
@click.pass_obj
def submit(
    ctx,
    pipeline: str,
    image: str,
    environment: str
):
    """Submit the pipeline to Argo."""
    LOGGER.info("Loading spec template..")

    loader = FileSystemLoader(searchpath=ARGO_TEMPLATES_DIR_PATH)
    template_env = Environment(loader=loader, trim_blocks=True, lstrip_blocks=True)
    template = template_env.get_template("argo_wf_spec.tmpl")

    pipeline_tasks = get_argo_dag(kedro_pipelines[pipeline])

    LOGGER.info("Rendering Argo spec...")

    project_path = find_kedro_project(Path.cwd()) or Path.cwd()
    bootstrap_project(project_path)
    with KedroSession.create(
        project_path=project_path,
        env=environment,
    ) as session:
        context = session.load_context()

        # Render the template
        rendered_template = template.render(
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
            namespace=namespace
        )
        
        workflow_name = response.metadata.name
        LOGGER.info(f"Workflow submitted successfully: {workflow_name}")
        LOGGER.info(f"View workflow at: https://argo.ai-platform.dev.everycure.org/workflows/{namespace}/{workflow_name}")
        
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
    dependecies to model relationships, Argo uses task dependencies."""

    def __init__(self, node: Node):
        self._node = node
        self._parents = []

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
        }


def get_argo_dag(pipeline: Pipeline) -> List[Dict[str, Any]]:
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
            task = ArgoTask(target_node)
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