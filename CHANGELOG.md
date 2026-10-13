# Changelog

## 1.1.1 — 2026-10-13

- Separate continuous keyboard coding from Manual review. Missing roles, N/A resolution and review approval never block Space/Up/Down navigation.
- Restore N / Next Uncoded to skipping written but unreviewed/flagged units. Add a separate review queue and Ctrl+Return approval available only in Manual review.
- Show passive full-row colors, text, issue tooltips and status dots for missing roles, inherited values and review state. Track Coded and Reviewed progress separately.
- Update only the changed unit’s progress and skip unnecessary filter scans during normal coding, improving keyboard response on large subtitle files.
- Preserve project schema version 2, old CSV reading, manual approval rules and reviewed-only analysis exports.

## 1.1.0 — 2026-10-13

- Protect keyboard coding and notes with immediate dirty state, row feedback and recovery saves; CSV export no longer clears unsaved project changes.
- Add mouse coding, character management controls, separate coding/character tabs, pasted-path validation and visible subtitle navigation.
- Introduce configurable required roles, study definitions/examples, explicit N/A, Confirmed/Needs review/Excluded states and confirmed-only analysis export.
- Preserve stable character/unit identities, coder/codebook metadata and UTC coding history; provide coding undo/redo and independent-coder comparison/adjudication with material verification.
- Keep old project/CSV reading and standard CIGA analysis columns. Legacy coding is unconfirmed until reviewed; use Save As for an upgraded schema version 2 project.
- Preserve coding at the end of the last subtitle, reject ambiguous/invalid imports without replacing records, and show inherited values as unconfirmed suggestions.

See docs/research-workflow.md for migration and limitations.
