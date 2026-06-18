"""One-shot migration: rename USA -> DAL across both demo projects and add
the parallel-task demo cases (Local Assembly, TID Report, NDD Report) to
npde_demo.json.

Run with: python scripts/migrate_usa_to_dal.py
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gantt_builder import api
from gantt_builder.models import Dependency, Task


def rename_usa_to_dal(project) -> None:
    if "USA" in project.settings.holidays:
        project.settings.holidays["DAL"] = project.settings.holidays.pop("USA")
    if "USA" in project.settings.work_weeks:
        project.settings.work_weeks["DAL"] = project.settings.work_weeks.pop("USA")
    for t in project.tasks:
        if t.completion_location == "USA":
            t.completion_location = "DAL"


def migrate_small_demo():
    path = ROOT / "examples" / "small_demo.json"
    project = api.load_project(path)
    rename_usa_to_dal(project)
    api.set_project_baseline(project, overwrite=True)
    api.save_project(project, path)
    print(f"small_demo: USA->DAL rename + re-baseline ({len(project.tasks)} tasks)")


def add_parallel_tasks(project) -> None:
    """Add Local Assembly, TID Report, NDD Report and wire their successors."""
    new_tasks = [
        Task(
            id="TASK-011", name="Local Assembly", completion_location="DAL",
            calendar_mode="working_days", cycle_time_days=3,
            dependencies=[Dependency(id="TASK-003")],
        ),
        Task(
            id="TASK-012", name="TID Report", completion_location="DAL",
            calendar_mode="working_days", cycle_time_days=1,
            dependencies=[Dependency(id="TASK-007")],
        ),
        Task(
            id="TASK-013", name="NDD Report", completion_location="DAL",
            calendar_mode="working_days", cycle_time_days=1,
            dependencies=[Dependency(id="TASK-007")],
        ),
    ]
    project.tasks.extend(new_tasks)

    project.task_by_id("TASK-005").dependencies.append(Dependency(id="TASK-011"))
    project.task_by_id("TASK-009").dependencies.append(Dependency(id="TASK-012"))
    project.task_by_id("TASK-009").dependencies.append(Dependency(id="TASK-013"))

    project.settings.next_task_id = 14


def migrate_npde_demo():
    path = ROOT / "examples" / "npde_demo.json"
    project = api.load_project(path)
    rename_usa_to_dal(project)
    add_parallel_tasks(project)
    api.set_project_baseline(project, overwrite=True)
    api.save_project(project, path)
    print(f"npde_demo: USA->DAL + 3 new tasks + re-baseline ({len(project.tasks)} tasks)")


def verify_both():
    for name in ("small_demo", "npde_demo"):
        path = ROOT / "examples" / f"{name}.json"
        project = api.load_project(path)
        api.validate_project(project)
        schedule = api.schedule_project(project)
        print(f"  {name}: {len(project.tasks)} tasks, validated, schedule clean")


if __name__ == "__main__":
    migrate_small_demo()
    migrate_npde_demo()
    print()
    print("Verifying:")
    verify_both()
