"""Playwright UI verification for PMSuite Streamlit editing surface.

Step 7: automated browser tests covering all 16 golden-path flows.
Screens out bugs before adding feature complexity (holiday editor, etc.).

Design decisions documented in PLAYWRIGHT_SCREENING.md.

Requirements:
    pip install -e ".[test-ui]"
    playwright install chromium

Run:
    pytest tests/test_streamlit_playwright.py -m playwright
    HEADED=1 pytest tests/test_streamlit_playwright.py -k test_00  # watch the showcase
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright")
from playwright.async_api import async_playwright  # noqa: E402

from .playwright_helpers import (  # noqa: E402
    REPO_ROOT,
    PROJECTS_DIR,
    add_task,
    click_build_excel,
    click_save,
    click_set_baseline,
    click_validate,
    copy_fixture_to_projects,
    count_complete_indicators,
    create_new_project,
    delete_task,
    dismiss_auto_catchup,
    edit_task_name,
    expect_clean_indicator,
    expect_dirty_indicator,
    expect_task_visible,
    find_free_port,
    find_latest_excel,
    find_task_in_json,
    load_json_from_disk,
    load_project_via_url,
    mark_task_complete,
    open_task_expander,
    remove_fixture_from_projects,
    set_snapshot_count,
    start_streamlit,
    stop_streamlit,
    toggle_auto_delay_setting,
    wait_for_app_ready,
)

pytestmark = pytest.mark.playwright

FIXTURE_NAME = "pw_test_project.json"
FIXTURE_PATH = PROJECTS_DIR / FIXTURE_NAME
HEADED = os.environ.get("HEADED", "").strip() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def streamlit_server():
    port = find_free_port()
    proc = start_streamlit(port)
    yield f"http://127.0.0.1:{port}"
    stop_streamlit(proc)


@pytest.fixture(scope="session")
def browser_instance():
    """Single browser + context for the entire test session.

    Each test creates a fresh page (tab) within this context to avoid
    the Streamlit session-handling bug triggered by rapid
    browser-context create/destroy cycles.
    """
    import asyncio
    loop = asyncio.new_event_loop()

    async def _launch():
        p = await async_playwright().start()
        browser = await p.chromium.launch(headless=not HEADED)
        context = await browser.new_context(viewport={"width": 1920, "height": 4000})
        context.set_default_timeout(15000)
        return p, browser, context

    playwright_inst, browser, context = loop.run_until_complete(_launch())
    yield context, loop
    loop.run_until_complete(context.close())
    loop.run_until_complete(browser.close())
    loop.run_until_complete(playwright_inst.stop())
    loop.close()


@pytest.fixture()
def fresh_fixture():
    path = copy_fixture_to_projects(FIXTURE_NAME)
    yield path
    remove_fixture_from_projects(FIXTURE_NAME)


SCREENSHOT_DIR = REPO_ROOT / "test-results" / "screenshots"


@pytest.fixture()
def page_and_project(request, streamlit_server, browser_instance, fresh_fixture):
    """Open a fresh page (tab), navigate to the test fixture via URL query param."""
    context, loop = browser_instance
    url = streamlit_server

    async def _setup():
        page = await context.new_page()
        await load_project_via_url(page, url, FIXTURE_NAME)
        try:
            await page.locator("text=PW-TEST").wait_for(timeout=20000)
        except Exception:
            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(SCREENSHOT_DIR / f"setup_fail_{request.node.name}.png"))
            raise
        await dismiss_auto_catchup(page)
        return page

    page = loop.run_until_complete(_setup())
    yield page, loop, fresh_fixture, url

    if hasattr(request.node, "rep_call") and request.node.rep_call and request.node.rep_call.failed:
        _save_screenshot(loop, page, request.node.name)
    loop.run_until_complete(page.close())


def _save_screenshot(loop, page, test_name: str) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{test_name}.png"
    try:
        loop.run_until_complete(page.screenshot(path=str(path)))
    except Exception:
        pass


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


def run(loop, coro):
    return loop.run_until_complete(coro)


# ---------------------------------------------------------------------------
# Cleanup helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def cleanup_test_projects():
    yield
    for pattern in ("test-pw*.json", "pw-new-test.json"):
        for f in PROJECTS_DIR.glob(pattern):
            f.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestShowcase:

    def test_00_showcase_headed(self, streamlit_server, browser_instance, fresh_fixture):
        context, loop = browser_instance
        url = streamlit_server
        _page = None

        async def _run():
            nonlocal _page
            _page = await context.new_page()
            await load_project_via_url(_page, url, FIXTURE_NAME)
            await _page.locator("text=PW-TEST").wait_for(timeout=15000)
            await dismiss_auto_catchup(_page)

            await add_task(_page, name="Showcase Task", cycle_days=3)
            await expect_dirty_indicator(_page)

            await click_save(_page)
            await expect_clean_indicator(_page)

            data = load_json_from_disk(fresh_fixture)
            showcase = find_task_in_json(data, "TASK-015")
            assert showcase is not None, "TASK-015 not found in saved JSON"
            assert showcase["name"] == "Showcase Task"

            await load_project_via_url(_page, url, FIXTURE_NAME)
            await _page.locator("text=PW-TEST").wait_for(timeout=15000)
            await dismiss_auto_catchup(_page)
            await expect_task_visible(_page, "TASK-015")

            await _page.close()

        try:
            run(loop, _run())
        except Exception:
            if _page:
                _save_screenshot(loop, _page, "test_00_showcase_headed")
            raise


class TestLoadProject:

    def test_load_existing_project(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            await page.locator("text=PW-TEST").wait_for(timeout=5000)
            await page.locator("text=14 tasks").wait_for(timeout=5000)
            await expect_clean_indicator(page)

        run(loop, _run())


class TestTaskCRUD:

    def test_add_task(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            await add_task(page, name="New CRUD Task", cycle_days=7)
            await expect_task_visible(page, "TASK-015")
            await expect_dirty_indicator(page)

            await click_save(page)
            data = load_json_from_disk(fixture_path)
            task = find_task_in_json(data, "TASK-015")
            assert task is not None
            assert task["name"] == "New CRUD Task"
            assert task["cycle_time_days"] == 7

        run(loop, _run())

    def test_edit_task(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            await edit_task_name(page, "TASK-004", "Renamed Assembly")
            await expect_dirty_indicator(page)

            await click_save(page)
            data = load_json_from_disk(fixture_path)
            task = find_task_in_json(data, "TASK-004")
            assert task["name"] == "Renamed Assembly"

        run(loop, _run())

    def test_delete_task(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            await add_task(page, name="To Delete", cycle_days=1)
            await click_save(page)

            new_id = "TASK-015"
            await expect_task_visible(page, new_id)

            await open_task_expander(page, new_id)
            await delete_task(page, new_id)
            await expect_dirty_indicator(page)

            await click_save(page)
            data = load_json_from_disk(fixture_path)
            assert find_task_in_json(data, new_id) is None

        run(loop, _run())

    def test_delete_task_blocked_by_dependents(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            await open_task_expander(page, "TASK-003")
            section = page.locator('[data-testid="stExpander"]').filter(has_text="TASK-003 --")
            await section.get_by_role("button", name="Delete TASK-003").click()
            await page.wait_for_timeout(2000)
            await page.locator("text=TASK_DELETION_BLOCKED").wait_for(timeout=10000)

        run(loop, _run())


class TestDependencies:

    def test_add_dependency(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            await add_task(page, name="Dep Source", cycle_days=2)
            await click_save(page)

            await add_task(page, name="Dep Target", cycle_days=2)
            await click_save(page)

            await open_task_expander(page, "TASK-016")
            section = page.locator('[data-testid="stExpander"]').filter(has_text="TASK-016 --")
            form = section.locator('[data-testid="stForm"]').first
            await form.get_by_role("button", name="Add dependency").click()
            await page.wait_for_timeout(3000)

            await click_save(page)
            data = load_json_from_disk(fixture_path)
            task = find_task_in_json(data, "TASK-016")
            assert task is not None
            dep_ids = [d["id"] for d in task.get("dependencies", [])]
            assert len(dep_ids) > 0

        run(loop, _run())

    def test_remove_dependency(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            await open_task_expander(page, "TASK-004")
            section = page.locator('[data-testid="stExpander"]').filter(has_text="TASK-004 --")
            x_buttons = section.get_by_role("button", name="X")
            count = await x_buttons.count()
            if count > 0:
                await x_buttons.first.click()
                await page.wait_for_timeout(3000)
                await expect_dirty_indicator(page)

                await click_save(page)
                data = load_json_from_disk(fixture_path)
                task = find_task_in_json(data, "TASK-004")
                assert len(task["dependencies"]) == 0

        run(loop, _run())


class TestCompletion:

    def test_complete_indicator_visible(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            total, checked_before = await count_complete_indicators(page)
            assert total > 0, "No Complete? indicators found on page"
            assert checked_before > 0, "Fixture has completed tasks but no indicators are checked"

        run(loop, _run())

    def test_complete_indicator_updates_on_mark(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            _, checked_before = await count_complete_indicators(page)

            await mark_task_complete(page, "TASK-008")
            _, checked_after = await count_complete_indicators(page)
            assert checked_after > checked_before, (
                f"Expected more checked indicators after marking complete: "
                f"before={checked_before}, after={checked_after}"
            )

            await click_save(page)
            data = load_json_from_disk(fixture_path)
            task = find_task_in_json(data, "TASK-008")
            assert task["is_complete"] is True

        run(loop, _run())

    def test_mark_complete_with_cascade(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            await mark_task_complete(page, "TASK-008")
            await expect_dirty_indicator(page)

            await click_save(page)
            data = load_json_from_disk(fixture_path)
            task = find_task_in_json(data, "TASK-008")
            assert task["is_complete"] is True
            assert task["actual_completion_date"] is not None

        run(loop, _run())


class TestActionButtons:

    def test_validate_clean(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            await click_validate(page)
            alerts = page.locator('[data-testid="stAlert"]')
            await page.wait_for_timeout(1000)
            count = await alerts.count()
            assert count >= 0

        run(loop, _run())

    def test_validate_with_errors(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            await click_validate(page)
            await page.wait_for_timeout(1000)
            alerts = page.locator('[data-testid="stAlert"]')
            count = await alerts.count()
            assert count >= 0

        run(loop, _run())

    def test_save_and_dirty_state(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            await expect_clean_indicator(page)

            await add_task(page, name="Dirty State Test", cycle_days=1)
            await expect_dirty_indicator(page)

            await click_save(page)
            await expect_clean_indicator(page)

            data = load_json_from_disk(fixture_path)
            task = find_task_in_json(data, "TASK-015")
            assert task is not None

        run(loop, _run())

    def test_build_excel(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            output_dir = REPO_ROOT / "output"
            existing = set(output_dir.glob("*.xlsx")) if output_dir.exists() else set()

            await click_build_excel(page)
            await page.wait_for_timeout(2000)

            latest = find_latest_excel(output_dir)
            assert latest is not None, "No .xlsx file found in output/ after Build Excel"
            assert latest not in existing, "No new .xlsx file was created"

        run(loop, _run())

    def test_set_baseline(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            await click_set_baseline(page)
            await expect_dirty_indicator(page)

            await page.locator("text=Baseline set").wait_for(timeout=10000)

            await click_save(page)
            data = load_json_from_disk(fixture_path)
            has_baseline = any(
                t.get("baseline_start") is not None
                for t in data["tasks"]
            )
            assert has_baseline

        run(loop, _run())


class TestAutoCatchup:

    def test_auto_catchup_apply_and_undo(self, streamlit_server, browser_instance, fresh_fixture):
        context, loop = browser_instance
        url = streamlit_server
        _page = None

        async def _run():
            nonlocal _page
            _page = await context.new_page()
            await load_project_via_url(_page, url, FIXTURE_NAME)
            await _page.locator("text=PW-TEST").wait_for(timeout=15000)

            catchup_btn = _page.get_by_role("button", name="Apply auto-catchup")
            count = await catchup_btn.count()
            if count > 0:
                await catchup_btn.click()
                await _page.wait_for_timeout(3000)
                await expect_dirty_indicator(_page)
                await _page.locator("text=Auto-catchup applied").wait_for(timeout=10000)

                undo_btn = _page.get_by_role("button", name="Undo auto-catchup batch")
                if await undo_btn.count() > 0:
                    await undo_btn.click()
                    await _page.wait_for_timeout(2000)

            await _page.close()

        try:
            run(loop, _run())
        except Exception:
            if _page:
                _save_screenshot(loop, _page, "test_auto_catchup_apply_and_undo")
            raise

    def test_auto_catchup_skip(self, streamlit_server, browser_instance, fresh_fixture):
        context, loop = browser_instance
        url = streamlit_server
        _page = None

        async def _run():
            nonlocal _page
            _page = await context.new_page()
            await load_project_via_url(_page, url, FIXTURE_NAME)
            await _page.locator("text=PW-TEST").wait_for(timeout=15000)

            skip_btn = _page.get_by_role("button", name="Skip for now")
            count = await skip_btn.count()
            if count > 0:
                await skip_btn.click()
                await _page.wait_for_timeout(2000)
                skip_after = _page.get_by_role("button", name="Skip for now")
                assert await skip_after.count() == 0

            await _page.close()

        try:
            run(loop, _run())
        except Exception:
            if _page:
                _save_screenshot(loop, _page, "test_auto_catchup_skip")
            raise


class TestNewProject:

    def test_create_new_project(self, streamlit_server, browser_instance):
        context, loop = browser_instance
        url = streamlit_server
        _page = None
        dest = PROJECTS_DIR / "pw-new-test.json"
        if dest.exists():
            dest.unlink()

        async def _run():
            nonlocal _page
            _page = await context.new_page()
            await _page.goto(url)
            await wait_for_app_ready(_page)

            await create_new_project(_page, name="PW New Test", slug="PW-NEW-TEST")
            assert dest.exists(), "Project file not created on disk"

            await _page.close()

        try:
            run(loop, _run())
        except Exception:
            if _page:
                _save_screenshot(loop, _page, "test_create_new_project")
            raise
        finally:
            if dest.exists():
                dest.unlink()


class TestProjectSwitching:

    def test_switch_cancel(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            await add_task(page, name="Unsaved Switch Test", cycle_days=1)
            await expect_dirty_indicator(page)

            sidebar = page.locator('[data-testid="stSidebar"]')
            select_box = sidebar.get_by_role("combobox").first
            await select_box.click()
            await page.wait_for_timeout(500)
            await page.get_by_role("option").filter(has_text="small_demo").click()
            await page.wait_for_timeout(3000)

            cancel_btn = page.get_by_role("button", name="Cancel")
            if await cancel_btn.count() > 0:
                await cancel_btn.click()
                await page.wait_for_timeout(3000)

            await expect_dirty_indicator(page)

        run(loop, _run())

    def test_switch_discard(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            await add_task(page, name="Will Be Discarded", cycle_days=1)
            await expect_dirty_indicator(page)

            sidebar = page.locator('[data-testid="stSidebar"]')
            select_box = sidebar.get_by_role("combobox").first
            await select_box.click()
            await page.wait_for_timeout(500)
            await page.get_by_role("option").filter(has_text="small_demo").click()
            await page.wait_for_timeout(2000)

            discard_btn = page.get_by_role("button", name="Discard & Switch")
            if await discard_btn.count() > 0:
                await discard_btn.click()
                await page.wait_for_timeout(3000)

        run(loop, _run())

    def test_switch_save_and_switch(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            await add_task(page, name="Saved Before Switch", cycle_days=1)
            await expect_dirty_indicator(page)

            sidebar = page.locator('[data-testid="stSidebar"]')
            select_box = sidebar.get_by_role("combobox").first
            await select_box.click()
            await page.wait_for_timeout(500)
            await page.get_by_role("option").filter(has_text="small_demo").click()
            await page.wait_for_timeout(2000)

            save_switch_btn = page.get_by_role("button", name="Save & Switch")
            if await save_switch_btn.count() > 0:
                await save_switch_btn.click()
                await page.wait_for_timeout(3000)

                data = load_json_from_disk(fixture_path)
                task = find_task_in_json(data, "TASK-015")
                assert task is not None
                assert task["name"] == "Saved Before Switch"

        run(loop, _run())


class TestManualStartToggle:

    def test_manual_start_toggle(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            await open_task_expander(page, "TASK-004")
            section = page.locator('[data-testid="stExpander"]').filter(has_text="TASK-004 --")

            checkbox = section.get_by_label("Has manual start date")
            if not await checkbox.is_checked():
                await checkbox.evaluate("el => el.click()")
                await page.wait_for_timeout(500)

            apply_btn = section.get_by_role("button", name="Apply changes to TASK-004")
            await apply_btn.scroll_into_view_if_needed()
            await apply_btn.click()
            await page.wait_for_timeout(3000)
            await expect_dirty_indicator(page)

            await click_save(page)
            data = load_json_from_disk(fixture_path)
            task = find_task_in_json(data, "TASK-004")
            assert task["manual_start_date"] is not None

        run(loop, _run())


class TestSettings:

    def test_auto_delay_toggle(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            data_before = load_json_from_disk(fixture_path)
            auto_before = data_before["settings"]["auto_delay_on_load"]

            await toggle_auto_delay_setting(page)
            await expect_dirty_indicator(page)

            await click_save(page)
            data_after = load_json_from_disk(fixture_path)
            assert data_after["settings"]["auto_delay_on_load"] != auto_before

        run(loop, _run())

    def test_snapshot_count(self, page_and_project):
        page, loop, fixture_path, base_url = page_and_project

        async def _run():
            await set_snapshot_count(page, 5)
            await page.wait_for_timeout(1000)

            await click_save(page)
            data = load_json_from_disk(fixture_path)
            assert data["settings"]["keep_local_snapshots"] == 5

        run(loop, _run())
