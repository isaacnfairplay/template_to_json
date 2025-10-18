# To-Do

The following tasks outline the most impactful next steps for making the template extraction and printing pipeline production-ready.

## Immediate Priorities
- [x] Finalize the **vector extraction pass**: solidify rectangle detection, infer rounded corners, and validate grid clustering on representative vector PDFs.
- [ ] Implement the **raster fallback** pipeline end-to-end (render → edge detection → morphology → connected components → grid inference) with deterministic outputs.
- [ ] Add integration tests that run both extraction modes on synthetic PDFs to guarantee <0.5 pt error for geometry metrics.
- [ ] Flesh out the JSON/CSV exporters to cover **percent_of_width**, points, inches, and millimeters; include round-trip tests.
- [ ] Create regression fixtures (synthetic) and scripts under `scripts/` to reproduce extraction on sample inputs.

## Near-Term Enhancements
- [ ] Expose a concise `templator.cli` interface for extraction and circle synthesis, including usage docs in the README.
- [ ] Implement circle lattice synthesizers (simple and close-packing) with property tests for in-bounds, non-overlapping placement.
- [ ] Harden unit conversion helpers in `templator.geometry` with exhaustive type hints and edge-case tests.
- [ ] Add mypy strict configuration fixes and ensure `uvx mypy .`, `uvx ruff check .`, and `uv run pytest -q` all pass locally.
- [ ] Benchmark extraction performance across DPI settings and document recommended defaults.

## Strategic Initiatives
- [ ] Design the future **printing API** surface (render specs, layout engine, encoder hooks) and draft implementation milestones.
- [ ] Evaluate barcode/QR/Data Matrix encoder dependencies for pure-Python or wheel availability and plan integration strategy.
- [ ] Develop a PDF verification harness that checks label placement accuracy for generated print jobs.
- [ ] Plan CI coverage (Linux/macOS/Windows) with caching to keep runtime low.

## Developer Experience & Documentation
- [ ] Expand README quickstart with uv/uvx commands, example outputs, and percent-of-width rationale.
- [ ] Provide contribution guidelines emphasizing deterministic outputs, synthetic fixtures, and sensitive-data handling.
- [ ] Document troubleshooting steps for common extraction failures (e.g., noisy rasters, malformed PDFs).
- [ ] Automate changelog generation and release packaging (sdist/wheel) workflows.

## Open Questions
- [ ] How to gracefully warn users about potential PII in supplied templates without storing sensitive data?
- [ ] What heuristics should govern switching between vector and raster paths for mixed-content PDFs?
- [ ] Which performance metrics should we track to ensure scalability for bulk extraction and printing jobs?
