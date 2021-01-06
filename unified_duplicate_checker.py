"""
Stores all file names and sizes in a CSV file.

"""

import config
from pathlib import Path
import csv
import re

unified_duplicate_log = Path(config.LOG_PATH) / "unified-duplicate-log.txt"

def log_file(file_name: str, file_size: str) -> None:
    """Log file name and size"""
    with unified_duplicate_log.open("a", newline='') as f:
        writer = csv.writer(f)
        writer.writerow([file_name, file_size])

def mangle_file_name(file_name: str) -> str:
    file_name = file_name.upper()
    file_name = re.sub(r"\[re-?up\] ", "", file_name, flags=re.IGNORECASE)
    file_name = re.sub(r"\[new\] (- )?", "", file_name, flags=re.IGNORECASE)
    return file_name
mfn = mangle_file_name

def is_duplicate(file_name: str, file_size: str) -> bool:
    if not unified_duplicate_log.exists():
        return False
    with unified_duplicate_log.open("r", newline='') as f:
        reader = csv.reader(f)
        for row in reader:
            if mfn(file_name) == mfn(row[0]) and str(file_size) == row[1]:
                return True
    return False

def is_duplicate_file(f) -> bool:
    return is_duplicate(Path(f.url).name, f.size)

