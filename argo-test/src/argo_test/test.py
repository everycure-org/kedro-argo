import os
import mlflow
from pathlib import Path

from kedro.framework.session import KedroSession
from kedro.utils import find_kedro_project
from kedro.framework.startup import bootstrap_project

project_path = find_kedro_project(Path.cwd()) or Path.cwd()
bootstrap_project(project_path)

with KedroSession.create(
    project_path=project_path,
    env="base"
) as session:

    context = session.load_context()
    experiment = context.mlflow.tracking.experiment.name

mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
mlflow.set_experiment(experiment)
run = mlflow.start_run(run_name=os.getenv("WORKFLOW_ID", "dummy"))
with open("/tmp/mlflow_run_id", "w", encoding="utf-8") as f:
    f.write(run.info.run_id)

