# 1.1.0 validation — 2026-10-13

- Windows / Python 3.13.7 / PySide6 6.11.2: 93 annotator tests passed, including real Qt mouse/key events, legacy project/CSV support, save/recovery protection, completion rules, undo, import failure preservation and adjudication.
- Existing CIGA GUI: 16 tests passed against installed CIGA 0.1.5. Actual new confirmed-only and metadata CSV exports were loaded through the GUI and built graphs without changing their selected source/target/position columns. Confirmed export retained position 1; full export retained positions 1 and 2, with pending empty rows dropped from interaction edges.
- Real synthetic MP4 playback (H.264/AAC, 640×360, 24 fps, four seconds): decoded 59 valid video frames, paused at both subtitle boundaries, preserved both units’ coding and reported no media error. This checks this generated format, not every user video codec/device.
- Current coding workspace, project rule dialog and comparison dialog rendered and inspected with Segoe UI. Screenshot uses synthetic subtitles and does not represent a user’s research data.
- Windows one-file executable built in an isolated environment with a minimal DLL search path. Frozen source signatures checked against the delivered version, annotator, research model/workflow/dialogs, setup, project and CSV modules. Independent startup outside the repository directory passed with a minimal PATH.

The GitHub test workflow additionally runs Windows and Linux with Python 3.11/3.13. Per-release CI status and the final SHA-256 checksums are attached to the GitHub release. Packaged startup and source playback are distinct checks; no claim is made that every Windows 11 machine/video file has been tested.

Undo is bounded and session-local; the persisted audit log is editable local JSON. User-task studies and inter-coder reliability statistics are not automated by these tests.
