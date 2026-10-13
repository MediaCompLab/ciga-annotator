# Research coding workflow (1.1.0)

## Prepare the study

Open the video and SRT files by browsing or pasting existing paths. Coding units are subtitle cues: segmentation must be prepared before coding. The tool does not split or merge video intervals.

In **Project coding rules**, enter the coder ID, codebook version, and each role’s operational definition, examples and ambiguous cases. Speaker/Listener/Target meanings are decided by the study. Choose required roles; the default requires all three. Metadata fields may be left blank, but the application displays “not set” and the record then has no named coder/codebook attribution.

Save a baseline project and give each independent coder a separate copy. Set each copy’s coder ID before coding. Character IDs persist across copies; character names remain in CIGA-compatible exports.

## Code and confirm

Select a role button and check one or more characters, or use Alt + the character key. A role can have selections or explicit N/A, never both. Optional roles may remain empty. Every required role needs a selection or N/A before confirmation is enabled.

- **Pending:** no coding started. Older filled-role projects migrate to In progress, never Confirmed.
- **In progress:** coding has started, without human confirmation.
- **Confirmed:** explicitly checked under the project’s current rules. Confirmation records its time, coder and codebook version.
- **Needs review:** an unresolved judgement, a previously confirmed unit edited again, or a unit affected by changed completion rules/definitions/codebook version.
- **Excluded:** explicitly removed from the study with a recorded reason. The coding remains in the project. Editing it sends it back to review.

Use Confirm & next, Needs review, or Exclude. Inherited Listener/Target values are visible suggestions that remain unconfirmed. The Next Unfinished action finds Pending, In progress and Needs review units. Navigation clears filters when necessary to reveal the selected unit.

The Characters tab has Add/Rename/Delete. Names must be unique and contain no commas. Renaming updates all role references and preserves identity and old names as aliases. Deleting an in-use character is blocked with the affected unit count. Templates are not overwritten automatically; export one explicitly if needed.

Click the video or a role button to return to coding after editing characters. Text fields accept typing normally. Shortcut help uses the actual configured keys; Preferences rejects conflicting or reserved shortcuts.

## Protect and correct records

Each coding edit immediately updates its subtitle row, marks the project unsaved and becomes eligible for the 15-second crash-recovery copy. The title and status bar show unsaved changes. Recovery-copy feedback is separate from explicit project save.

Ctrl+S writes the project atomically. CSV export never marks the project saved. Closing offers save/discard/cancel. Recovery copies are removed after explicit save or discard.

Edit → Undo Coding / Redo Coding restores coding selections, notes, N/A, review states and adjudication. The in-session history contains up to 200 edits; continuous note typing is one edit, with navigation/save boundaries. Rename/delete, project-rule changes and CSV replacement clear this undo history to avoid restoring stale names or rules. The persistent audit log still records these changes, including undo/redo. Undo history is not restored across application restarts.

Tools → Material and Coding History displays project metadata and timestamped records. Times are UTC. This is a local research log, not a cryptographically protected or tamper-proof audit system.

## Export and import

- **Export Confirmed Coding for Analysis:** exports only Confirmed units, using CIGA’s standard `line,position,start_time,end_time,speakers,listeners,targets` and custom fields. Excluded and unfinished units do not enter this export; original numeric positions retain gaps.
- **Export All Coding to CSV:** exports every cue, including pending/excluded units, and adds unit/material IDs, review state, N/A, coder/codebook, confirmation and rules. Use for inspection or exchange, not as the final analysis sample.
- **Save Project (.vat):** preserves characters/IDs, rules, full annotations, material metadata and audit history. CSV is not a substitute for this research record.

CSV import replaces current coding after a dialog warning. It validates the complete file before replacing any data: material/text, timestamps/position, duplicate units, N/A and state metadata. Standard older CSV files remain supported and require explicit confirmation. Confirmed metadata is retained only when the material/unit and project rules match and required-role checks pass; otherwise it returns to Needs review. CSV import starts a new undo history and adds an import event.

N/A means no selected character for that role. It is exported as an empty role cell, not as an invented character named N/A. CIGA analyses needing interaction edges still require selected characters in their source/target columns.

## Compare independent coders

Tools → Compare Another Coder’s Project checks the parsed subtitle content hash, coding unit IDs, definitions, required roles, custom-field schema and codebook version. Both project videos are read to verify their actual SHA-256 content, with a cancelable progress indicator; comparison fails if the video bytes differ or no longer match a recorded digest. Renamed character identities are matched by ID; independently created projects can match unique, identical names. No fuzzy name matching is used.

Inspect role sets, N/A, review states, notes, custom fields and exclusions side by side. Show unit navigates to the video without creating inherited coding. Keep current / Use other records the source project, source coder and decision, leaves the result in Needs review and supports undo. Confirm the result after adjudication. The other coder’s file is never modified.

This workflow does not calculate inter-coder reliability statistics or provide real-time shared editing. Independent originals should be retained separately from an adjudicated project.

## Existing projects and material changes

Version 1.1.0 opens older .vat projects and adds schema version 2 metadata in memory, marked unsaved. Save As is recommended for an upgraded copy. Older releases can lose the new metadata or misinterpret confirmation; do not use them to edit the upgraded research copy. The analysis CSV remains compatible with CIGA 0.1.5 and CIGA GUI 1.0.2.

Subtitle IDs hash parsed cue times and text, so file moves, encoding and newline changes do not change identity. Changed subtitle content or an unexpected video size is rejected when opening a recorded project. Video content hashes are verified when comparing; ordinary project opening checks video size, not every byte. Changing the material/segmentation requires a new coding baseline rather than silently reassigning old annotations.

Validation uses real Qt widget mouse/key events and synthetic material. Video codec/playback coverage and research-user usability studies are separate from these automated checks.
