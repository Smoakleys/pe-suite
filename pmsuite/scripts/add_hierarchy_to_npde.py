"""Add parent/child hierarchy to npde_demo.json for visual inspection.

Creates three parent groupings:
  1. "Post-Fab Processing" parent over Assembly (TASK-004) + Local Assembly (TASK-011)
  2. "Final Documentation" parent over Datasheet (TASK-008), TID (TASK-012), NDD (TASK-013)
  3. Break Wafer fab (TASK-003) into two sub-lots to show nested children
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gantt_builder import api
from gantt_builder.editing import add_task, update_task

path = ROOT / "examples" / "npde_demo.json"
project = api.load_project(path)

# 1. "Post-Fab Processing" parent over TASK-004 (Assembly) and TASK-011 (Local Assembly)
parent1 = add_task(
    project,
    name="Post-Fab Processing",
    completion_location="DAL",
    calendar_mode="working_days",
    cycle_time_days=None,
    manual_start_date=None,
)
update_task(project, "TASK-004", parent_id=parent1.id)
update_task(project, "TASK-011", parent_id=parent1.id)
print(f"Created {parent1.id} 'Post-Fab Processing' with children TASK-004, TASK-011")

# 2. "Final Documentation" parent over TASK-008, TASK-012, TASK-013
parent2 = add_task(
    project,
    name="Final Documentation",
    completion_location="DAL",
    calendar_mode="working_days",
    cycle_time_days=None,
    manual_start_date=None,
)
update_task(project, "TASK-008", parent_id=parent2.id)
update_task(project, "TASK-012", parent_id=parent2.id)
update_task(project, "TASK-013", parent_id=parent2.id)
print(f"Created {parent2.id} 'Final Documentation' with children TASK-008, TASK-012, TASK-013")

# 3. Break Wafer fab (TASK-003) into two sub-lots
#    TASK-003 becomes a parent; its dependency on TASK-002 provides the floor for children.
task003 = project.task_by_id("TASK-003")
lot1 = add_task(
    project,
    name="Wafer fab - Lot 1",
    completion_location="TAI",
    calendar_mode="e_days",
    cycle_time_days=10,
    manual_start_date=None,
    parent_id="TASK-003",
    dependencies=[{"id": "TASK-002", "type": "FS", "lag_days": 0}],
)
lot2 = add_task(
    project,
    name="Wafer fab - Lot 2",
    completion_location="TAI",
    calendar_mode="e_days",
    cycle_time_days=14,
    manual_start_date=None,
    parent_id="TASK-003",
    dependencies=[{"id": lot1.id, "type": "SS", "lag_days": 3}],
)
# TASK-003 is now a parent: clear cycle_time_days
update_task(project, "TASK-003", cycle_time_days=None)
print(f"Created {lot1.id} 'Lot 1' and {lot2.id} 'Lot 2' under TASK-003")

# Validate
from gantt_builder.errors import ValidationFailure
try:
    warnings = api.validate_project(project)
    if warnings:
        for w in warnings:
            print(f"Warning: {w}")
    print("Validation passed.")
except ValidationFailure as exc:
    for err in exc.errors:
        print(f"ERROR: {err.error_code}: {err.message}")
    sys.exit(1)

# Save
api.save_project(project, path)
print(f"Saved to {path}")
print(f"Project now has {len(project.tasks)} tasks")
