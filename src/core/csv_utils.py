import os
import csv
import tempfile
from pathlib import Path

def write_rows_to_csv_atomic(file_path, rows, fieldnames=None):
    """Write CSV rows atomically to avoid partial/corrupted files on interruption."""
    target = Path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    os.close(fd)
    try:
        with open(tmp_path, 'w', newline='', encoding='utf-8-sig') as csvfile:  
            if fieldnames is None and rows:
                fieldnames = list(rows[0].keys())
            elif fieldnames is None:
                fieldnames = ['line', 'start_time', 'end_time', 'speakers', 'listeners', 'targets', 'note']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                # Add check for missing keys in simple row
                writer.writerow({k: row.get(k, '') for k in fieldnames})
        os.replace(tmp_path, file_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
