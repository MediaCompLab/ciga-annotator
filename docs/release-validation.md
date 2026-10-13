# 1.1.1 validation — 2026-10-13

- Windows / Python 3.13.7 / PySide6 6.11.2: 112 annotator tests passed. New tests exercise the original Alt+character / Space sequence with missing roles, N skipping written/unreviewed units, the separate manual review queue and approval shortcut, passive row colors, independent filters, and progress updates after rules/import/undo/exclusion.
- CIGA GUI compatibility is checked against CIGA 0.1.5 using its 16 tests plus actual reviewed-only and full metadata CSV exports. Standard role/time/position columns and persisted project/review-state keys remain compatible.
- Local UI processing benchmark: 3000 synthetic subtitle cues, 24 real Qt Alt+1 toggles, media decoding disabled, runs executed serially with the same Python/Qt runtime. Median event processing was 2.66 ms in v1.0.3 and 0.91 ms in v1.1.1; v1.1.0 measured 11.31 ms. These are local input-handler timings, not human coding-speed measurements, an FPS measurement, or a general hardware guarantee.
- Current coding, Manual review and project-rule dialogs rendered and inspected with Segoe UI. Screenshot uses synthetic data. The review status dot stays visible on selected rows.
- Release checks also verify generated H.264/AAC video playback, the isolated Windows one-file executable, frozen source/entrypoint signatures and independent startup. The final GitHub release links Windows/Linux × Python 3.11/3.13 test results and SHA-256 asset checksums.

The saved approval state remains `confirmed`; the UI calls it Reviewed. No automatically computed color constitutes human approval. Required-role checks only gate explicit manual approval. Coded progress means content was recorded; it does not claim that every field has been completed or reviewed.

Undo remains session-local and bounded; the persistent research log is editable local JSON. Research-user task testing is still needed to measure actual coding accuracy and productivity. See the historical 1.1.0 release for earlier package validation evidence.
