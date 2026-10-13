# Changelog

## 1.1.0 — 2026-10-13

- Protect keyboard coding and notes with immediate dirty state, row feedback and recovery saves; CSV export no longer clears unsaved project changes.
- Add mouse coding, character management controls, separate coding/character tabs, pasted-path validation and visible subtitle navigation.
- Introduce configurable required roles, study definitions/examples, explicit N/A, Confirmed/Needs review/Excluded states and confirmed-only analysis export.
- Preserve stable character/unit identities, coder/codebook metadata and UTC coding history; provide coding undo/redo and independent-coder comparison/adjudication with material verification.
- Keep old project/CSV reading and standard CIGA analysis columns. Legacy coding is unconfirmed until reviewed; use Save As for an upgraded schema version 2 project.
- Preserve coding at the end of the last subtitle, reject ambiguous/invalid imports without replacing records, and show inherited values as unconfirmed suggestions.

See docs/research-workflow.md for migration and limitations.
