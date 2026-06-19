"""Source registry assembly.

`register_all` is the single place that decides which sources exist. Adding a source =
writing its file (see ARCHITECTURE.md "Add a new fetched source") and registering it here.

There are NO fabricated/demo sources. Until a real source is registered, the Updates and
Material panes are honestly empty. The example HTTP and Playwright sources below do real
I/O and are opt-in (kept out of the default set so a plain run makes no network calls).
"""

from __future__ import annotations

from ..source import SourceRegistry


def register_all(registry: SourceRegistry, include_network: bool = False,
                 include_playwright: bool = False) -> SourceRegistry:
    # Real sources go here. The EASY way is a scraper script + a ScriptSource line
    # (see docs/SCRAPER_PLAYBOOK.md):
    #
    #     from .script_source import ScriptSource
    #     from datetime import timedelta
    #     registry.register(ScriptSource(
    #         id="acme_portal", name="Acme Portal", group="material",
    #         script="acme_portal.py", refresh_after=timedelta(minutes=30)))

    if include_network:
        # Worked example of the script-based path (real HTTP, no fabricated data).
        from .script_source import ScriptSource
        registry.register(ScriptSource(
            id="example_com", name="Example.com (script demo)", group="updates",
            script="example_com.py"))

    if include_playwright:
        from .playwright_example import ExamplePlaywrightSource, playwright_available
        if playwright_available():
            registry.register(ExamplePlaywrightSource())

    return registry


def all_known_source_ids() -> set[str]:
    """Every source id the app could ever register (used to prune stale store data).

    Includes the opt-in example sources so their cached data survives, but excludes
    anything that has been removed from the codebase — so deleting a source file makes
    its old records self-prune on next startup.
    """
    reg = register_all(SourceRegistry(), include_network=True, include_playwright=True)
    return {s.id for s in reg.all()}
