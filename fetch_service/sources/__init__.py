"""Source registry assembly.

`register_all` is the single place that decides which sources exist. Adding a source =
importing it and registering it here (plus its own file). Network/browser sources are
opt-in so default runs (and tests) stay deterministic and offline.
"""

from __future__ import annotations

from ..source import SourceRegistry


def register_all(registry: SourceRegistry, include_network: bool = False,
                 include_playwright: bool = False) -> SourceRegistry:
    from .demo import DemoMaterialSource, DemoUpdatesSource

    registry.register(DemoUpdatesSource())
    registry.register(DemoMaterialSource())

    if include_network:
        from .web_example import ExampleWebSource
        registry.register(ExampleWebSource())

    if include_playwright:
        from .playwright_example import ExamplePlaywrightSource, playwright_available
        if playwright_available():
            registry.register(ExamplePlaywrightSource())

    return registry
