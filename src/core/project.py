"""Project (.vat) file storage and crash-recovery autosave.

Autosave never writes to the user's project file. It writes a hidden sibling file
that records which project it belongs to, so choosing "don't save" really discards
changes, and an explicit save or discard removes the autosave.
"""
import json
import os
import tempfile
from pathlib import Path

# Key stored in an autosave file: absolute path of the project it recovers, or ""
# when the session had never been saved to a project.
AUTOSAVE_OF_KEY = "autosave_of"


def autosave_path_for(vat_file, srt_file):
    """Hidden autosave location: next to the project if there is one, else the subtitles."""
    anchor = Path(vat_file) if vat_file else Path(srt_file)
    return str(anchor.parent / f".{anchor.name}.autosave.vat")


def write_project_file(file_path, project_data):
    """Write JSON atomically; on any failure the previous file is left untouched.

    Errors (serialization or I/O) propagate so callers decide how to report them.
    """
    target = Path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    os.close(fd)
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(project_data, f, indent=4)
        os.replace(tmp_path, target)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def read_project_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def autosave_is_recoverable(autosave_path, vat_file):
    """An autosave is worth offering only if it exists and is newer than its project."""
    if not os.path.exists(autosave_path):
        return False
    if vat_file and os.path.exists(vat_file):
        return os.path.getmtime(autosave_path) > os.path.getmtime(vat_file)
    return True


def remove_file_quietly(file_path):
    """Delete a file if present. Used for autosaves, whose loss is never fatal."""
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass
