"""Composable Playwright helpers for PMSuite Streamlit UI tests.

Each helper encapsulates a single UI action: click a button, fill a form,
wait for a result. Tests compose them in any order to build scenarios.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_SRC = REPO_ROOT / "tests" / "fixtures" / "npde_playwright_test_fixture.json"
PROJECTS_DIR = REPO_ROOT / "projects"
EXAMPLES_DIR = REPO_ROOT / "examples"

DEFAULT_TIMEOUT = 10_000
SLOW_TIMEOUT = 25_000


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def copy_fixture_to_projects(name: str = "pw_test_project.json") -> Path:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = PROJECTS_DIR / name
    shutil.copy2(FIXTURE_SRC, dest)
    return dest


def remove_fixture_from_projects(name: str = "pw_test_project.json") -> None:
    dest = PROJECTS_DIR / name
    if dest.exists():
        dest.unlink()


def start_streamlit(port: int) -> subprocess.Popen:
    log_dir = REPO_ROOT / "test-results"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_log = open(log_dir / "streamlit_stdout.log", "w")
    stderr_log = open(log_dir / "streamlit_stderr.log", "w")
    proc = subprocess.Popen(
        [
            "python", "-m", "streamlit", "run",
            str(REPO_ROOT / "ui" / "streamlit_app.py"),
            "--server.port", str(port),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
        ],
        cwd=str(REPO_ROOT),
        stdout=stdout_log,
        stderr=stderr_log,
    )
    proc._stdout_log = stdout_log
    proc._stderr_log = stderr_log
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return proc
        except OSError:
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError(f"Streamlit did not start on port {port} within 30 seconds")


def stop_streamlit(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    for f in (getattr(proc, "_stdout_log", None), getattr(proc, "_stderr_log", None)):
        if f:
            try:
                f.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Page-level helpers
# ---------------------------------------------------------------------------

async def wait_for_app_ready(page, timeout: int = SLOW_TIMEOUT) -> None:
    await page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=timeout)
    await page.wait_for_timeout(2000)


async def load_project_via_url(page, base_url: str, project_file: str, timeout: int = SLOW_TIMEOUT) -> None:
    await page.goto(f"{base_url}/?project=projects/{project_file}")
    await page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=timeout)
    await page.wait_for_timeout(3000)


async def load_project(page, project_label: str, timeout: int = SLOW_TIMEOUT) -> None:
    sidebar = page.locator('[data-testid="stSidebar"]')
    select_box = sidebar.get_by_role("combobox").first
    await select_box.click()
    await page.wait_for_timeout(500)
    option = page.get_by_role("option").filter(has_text=project_label)
    await option.click()
    await page.wait_for_timeout(5000)


async def dismiss_auto_catchup(page) -> None:
    skip_btn = page.get_by_role("button", name="Skip for now")
    if await skip_btn.count() > 0:
        await skip_btn.click()
        await page.wait_for_timeout(1500)


# ---------------------------------------------------------------------------
# Task CRUD helpers
# ---------------------------------------------------------------------------

async def add_task(
    page,
    name: str = "Test Task",
    location: str = "DAL",
    calendar: str = "working_days",
    cycle_days: int = 5,
) -> None:
    expander = page.locator('[data-testid="stExpander"]').filter(has_text="Add new task")
    summary = expander.locator("summary").first
    is_open = await expander.locator("details[open]").count() > 0
    if not is_open:
        await summary.click()
        await page.wait_for_timeout(1000)

    form = expander.locator('[data-testid="stForm"]').first
    name_input = form.get_by_label("Task name")
    await name_input.clear()
    await name_input.fill(name)

    cycle_input = form.get_by_label("Cycle time (days)")
    await cycle_input.clear()
    await cycle_input.fill(str(cycle_days))

    await form.get_by_role("button", name="Add task").click()
    await page.wait_for_timeout(3000)


def _task_locator(page, task_id: str):
    """Return a locator that uniquely matches the expander for *this* task.

    Uses ``"TASK-NNN --"`` so child expanders showing ``(child of TASK-NNN)``
    are excluded.
    """
    return page.locator('[data-testid="stExpander"]').filter(has_text=f"{task_id} --")


async def open_task_expander(page, task_id: str) -> None:
    expander = _task_locator(page, task_id)
    is_open = await expander.locator("details[open]").count() > 0
    if not is_open:
        summary = expander.locator("summary").first
        await summary.click()
        await page.wait_for_timeout(1000)


async def edit_task_name(page, task_id: str, new_name: str) -> None:
    await open_task_expander(page, task_id)
    section = _task_locator(page, task_id)
    name_input = section.get_by_label("Name")
    await name_input.clear()
    await name_input.fill(new_name)
    apply_btn = section.get_by_role("button", name=f"Apply changes to {task_id}")
    await apply_btn.click()
    await page.wait_for_timeout(3000)


async def delete_task(page, task_id: str) -> None:
    section = _task_locator(page, task_id)
    await section.get_by_role("button", name=f"Delete {task_id}").click()
    await page.wait_for_timeout(2000)


async def mark_task_complete(page, task_id: str) -> None:
    await open_task_expander(page, task_id)
    section = _task_locator(page, task_id)
    checkbox = section.get_by_label("Is Complete")
    if not await checkbox.is_checked():
        await checkbox.evaluate("el => el.click()")
        await page.wait_for_timeout(500)
    apply_btn = section.get_by_role("button", name=f"Apply changes to {task_id}")
    await apply_btn.scroll_into_view_if_needed()
    await apply_btn.click()
    await page.wait_for_timeout(3000)


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

async def add_dependency(
    page, task_id: str, predecessor_id: str, dep_type: str = "FS", lag: int = 0
) -> None:
    section = _task_locator(page, task_id)
    form = section.locator('[data-testid="stForm"]').first
    await form.get_by_role("button", name="Add dependency").click()
    await page.wait_for_timeout(2000)


async def remove_dependency(page, task_id: str, dep_id: str) -> None:
    section = _task_locator(page, task_id)
    x_buttons = section.get_by_role("button", name="X")
    if await x_buttons.count() > 0:
        await x_buttons.first.click()
        await page.wait_for_timeout(2000)


# ---------------------------------------------------------------------------
# Action button helpers
# ---------------------------------------------------------------------------

async def click_validate(page) -> None:
    btn = page.get_by_role("button", name="Validate")
    await btn.click()
    await page.wait_for_timeout(3000)


async def click_save(page) -> None:
    btn = page.get_by_role("button", name="Save")
    await btn.click()
    await page.wait_for_timeout(3000)


async def click_build_excel(page) -> None:
    btn = page.get_by_role("button", name="Build Excel")
    await btn.click()
    await page.wait_for_timeout(5000)


async def click_set_baseline(page) -> None:
    btn = page.get_by_role("button", name="Set Baseline")
    await btn.click()
    await page.wait_for_timeout(3000)


# ---------------------------------------------------------------------------
# Auto-catchup helpers
# ---------------------------------------------------------------------------

async def click_apply_auto_catchup(page) -> None:
    await page.get_by_role("button", name="Apply auto-catchup").click()
    await page.wait_for_timeout(3000)


async def click_skip_auto_catchup(page) -> None:
    await page.get_by_role("button", name="Skip for now").click()
    await page.wait_for_timeout(2000)


async def click_undo_auto_catchup(page) -> None:
    await page.get_by_role("button", name="Undo auto-catchup batch").click()
    await page.wait_for_timeout(2000)


# ---------------------------------------------------------------------------
# Project management helpers
# ---------------------------------------------------------------------------

async def create_new_project(
    page, name: str = "Test Project", slug: str = "TEST-PW"
) -> None:
    sidebar = page.locator('[data-testid="stSidebar"]')
    await sidebar.get_by_role("button", name="New Project").click()
    await page.wait_for_timeout(2000)

    form = sidebar.locator('[data-testid="stForm"]').first
    await form.wait_for(timeout=10000)

    name_input = form.get_by_label("Project name")
    await name_input.clear()
    await name_input.fill(name)

    slug_input = form.get_by_label("Project ID (auto-slugged)")
    await slug_input.clear()
    await slug_input.fill(slug)

    await form.get_by_role("button", name="Create").click()
    await page.wait_for_timeout(5000)


async def switch_project_discard(page, project_label: str) -> None:
    sidebar = page.locator('[data-testid="stSidebar"]')
    select_box = sidebar.get_by_role("combobox").first
    await select_box.click()
    await page.wait_for_timeout(500)
    await page.get_by_role("option").filter(has_text=project_label).click()
    await page.wait_for_timeout(1500)
    btn = page.get_by_role("button", name="Discard & Switch")
    if await btn.count() > 0:
        await btn.click()
        await page.wait_for_timeout(3000)


async def switch_project_save(page, project_label: str) -> None:
    sidebar = page.locator('[data-testid="stSidebar"]')
    select_box = sidebar.get_by_role("combobox").first
    await select_box.click()
    await page.wait_for_timeout(500)
    await page.get_by_role("option").filter(has_text=project_label).click()
    await page.wait_for_timeout(1500)
    btn = page.get_by_role("button", name="Save & Switch")
    if await btn.count() > 0:
        await btn.click()
        await page.wait_for_timeout(3000)


async def switch_project_cancel(page, project_label: str) -> None:
    sidebar = page.locator('[data-testid="stSidebar"]')
    select_box = sidebar.get_by_role("combobox").first
    await select_box.click()
    await page.wait_for_timeout(500)
    await page.get_by_role("option").filter(has_text=project_label).click()
    await page.wait_for_timeout(1500)
    btn = page.get_by_role("button", name="Cancel")
    if await btn.count() > 0:
        await btn.click()
        await page.wait_for_timeout(2000)


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

async def toggle_auto_delay_setting(page) -> None:
    sidebar = page.locator('[data-testid="stSidebar"]')
    checkbox = sidebar.get_by_label("Auto-delay on load")
    await checkbox.evaluate("el => el.click()")
    await page.wait_for_timeout(1000)


async def set_snapshot_count(page, count: int) -> None:
    sidebar = page.locator('[data-testid="stSidebar"]')
    input_field = sidebar.get_by_label("Keep local snapshots")
    await input_field.scroll_into_view_if_needed()
    await input_field.click(click_count=3)
    await input_field.fill(str(count))
    await input_field.press("Enter")
    await page.wait_for_timeout(1000)


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

async def expect_dirty_indicator(page, timeout: int = DEFAULT_TIMEOUT) -> None:
    await page.locator("text=Unsaved changes").first.wait_for(timeout=timeout)


async def expect_clean_indicator(page, timeout: int = DEFAULT_TIMEOUT) -> None:
    await page.locator("text=All changes saved").first.wait_for(timeout=timeout)


async def expect_task_visible(page, task_id: str, timeout: int = DEFAULT_TIMEOUT) -> None:
    await page.locator(f"text={task_id}").first.wait_for(timeout=timeout)


async def expect_task_not_visible(page, task_id: str, timeout: int = DEFAULT_TIMEOUT) -> None:
    count = await page.locator(f"text={task_id}").count()
    assert count == 0, f"Expected {task_id} to not be visible, but found {count} instances"


async def count_complete_indicators(page) -> tuple[int, int]:
    indicators = page.get_by_label("Complete?")
    total = await indicators.count()
    checked = 0
    for i in range(total):
        if await indicators.nth(i).is_checked():
            checked += 1
    return total, checked


def load_json_from_disk(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_task_in_json(data: dict, task_id: str) -> dict | None:
    for t in data.get("tasks", []):
        if t["id"] == task_id:
            return t
    return None


def find_latest_excel(output_dir: Path = REPO_ROOT / "output") -> Path | None:
    if not output_dir.exists():
        return None
    xlsx_files = sorted(output_dir.glob("*.xlsx"), key=lambda p: p.stat().st_mtime)
    return xlsx_files[-1] if xlsx_files else None
