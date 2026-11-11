import csv
import hashlib
from pathlib import Path

from terratwin.models import SourceRecord


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: str | Path, require_records: bool = True) -> dict[str, SourceRecord]:
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = [SourceRecord.model_validate(row) for row in csv.DictReader(stream)]
    if require_records and not rows:
        raise ValueError(
            "Source manifest is empty; register verified local products before processing"
        )
    records = {row.source_id: row for row in rows}
    if len(records) != len(rows):
        raise ValueError("Duplicate source IDs in manifest")
    return records
