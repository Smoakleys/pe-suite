"""Fetch service: the out-of-process fetched-data side of PE Suite.

This package is pure infrastructure — no Qt, no `pesuite` imports. It runs in its own
process (via `fetch_service.runner`), scrapes/parses external sources behind the
`Source` contract, and writes normalized records to the hidden SQLite store. The PE
Suite UI only ever *reads* that store (through `pesuite.fetch_client`).

Boundary rule: nothing here imports the UI; the UI never fetches.
"""
