"""Cross-variant sub-assembly reuse finder.

The pipeline is linear and file-to-file: ingest -> normalize -> resolve -> signatures ->
checks -> report, with `evaluate` deliberately outside that chain (docs/ARCHITECTURE.md).
"""

__all__: list[str] = []
