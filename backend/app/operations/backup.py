from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from app.core.config import Settings, get_settings
from app.core.paths import sqlite_file_path

BACKUP_FORMAT_VERSION = 1
DEFAULT_BACKUP_DIR = Path("data/backups")
DATABASE_ARCHIVE_PATH = "database/app.sqlite3"
MANIFEST_ARCHIVE_PATH = "manifest.json"


@dataclass(frozen=True)
class RuntimeBackupPaths:
    database_path: Path
    upload_dir: Path
    export_dir: Path


@dataclass(frozen=True)
class RuntimeBackupResult:
    backup_path: Path
    manifest: dict[str, Any]


def runtime_paths_from_settings(settings: Settings | None = None) -> RuntimeBackupPaths:
    resolved_settings = settings or get_settings()
    database_path = sqlite_file_path(resolved_settings.database_url)
    if database_path is None:
        raise ValueError("Runtime backup supports file-backed SQLite DATABASE_URL values only.")

    return RuntimeBackupPaths(
        database_path=database_path,
        upload_dir=resolved_settings.upload_dir,
        export_dir=resolved_settings.export_dir,
    )


def create_runtime_backup(
    *,
    database_path: Path,
    upload_dir: Path,
    export_dir: Path,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    label: str | None = None,
) -> RuntimeBackupResult:
    database_path = database_path.expanduser()
    upload_dir = upload_dir.expanduser()
    export_dir = export_dir.expanduser()
    backup_dir = backup_dir.expanduser()

    _validate_backup_source(database_path=database_path, upload_dir=upload_dir, export_dir=export_dir)

    backup_dir.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(UTC).replace(microsecond=0)
    backup_path = _unique_backup_path(backup_dir / _build_backup_filename(created_at=created_at, label=label))

    upload_files = _relative_files(upload_dir)
    export_files = _relative_files(export_dir)

    manifest: dict[str, Any] = {
        "format_version": BACKUP_FORMAT_VERSION,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "source_paths": {
            "database_path": database_path.as_posix(),
            "upload_dir": upload_dir.as_posix(),
            "export_dir": export_dir.as_posix(),
        },
        "archive_paths": {
            "database": DATABASE_ARCHIVE_PATH,
            "uploads": "uploads/",
            "exports": "exports/",
        },
        "file_counts": {
            "database": 1,
            "uploads": len(upload_files),
            "exports": len(export_files),
        },
    }

    with tempfile.TemporaryDirectory(prefix="planning-backup-") as temp_dir_name:
        temp_database_path = Path(temp_dir_name) / "app.sqlite3"
        _copy_sqlite_database(database_path, temp_database_path)

        with ZipFile(backup_path, "x", compression=ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_ARCHIVE_PATH, json.dumps(manifest, indent=2, sort_keys=True))
            archive.write(temp_database_path, DATABASE_ARCHIVE_PATH)
            _write_tree_to_archive(archive=archive, source_dir=upload_dir, archive_root="uploads", files=upload_files)
            _write_tree_to_archive(archive=archive, source_dir=export_dir, archive_root="exports", files=export_files)

    return RuntimeBackupResult(backup_path=backup_path, manifest=manifest)


def restore_runtime_backup(
    *,
    backup_path: Path,
    database_path: Path,
    upload_dir: Path,
    export_dir: Path,
    force: bool = False,
) -> dict[str, Any]:
    backup_path = backup_path.expanduser()
    database_path = database_path.expanduser()
    upload_dir = upload_dir.expanduser()
    export_dir = export_dir.expanduser()

    if not backup_path.is_file():
        raise FileNotFoundError(f"Backup archive does not exist: {backup_path}")

    with ZipFile(backup_path) as archive:
        _validate_archive_members(archive)
        manifest = _read_manifest(archive)
        _assert_required_archive_members(archive)

        with tempfile.TemporaryDirectory(prefix="planning-restore-") as temp_dir_name:
            staging_root = Path(temp_dir_name)
            staging_database_path = staging_root / DATABASE_ARCHIVE_PATH
            staging_upload_dir = staging_root / "uploads"
            staging_export_dir = staging_root / "exports"

            _extract_database(archive=archive, database_path=staging_database_path)
            _extract_tree(archive=archive, archive_root="uploads", target_dir=staging_upload_dir)
            _extract_tree(archive=archive, archive_root="exports", target_dir=staging_export_dir)
            _assert_sqlite_integrity(staging_database_path)

            if not force:
                _ensure_restore_target_empty(database_path=database_path, upload_dir=upload_dir, export_dir=export_dir)

            _prepare_restore_target(database_path=database_path, upload_dir=upload_dir, export_dir=export_dir, force=force)
            shutil.copy2(staging_database_path, database_path)
            _copy_tree(source_dir=staging_upload_dir, target_dir=upload_dir)
            _copy_tree(source_dir=staging_export_dir, target_dir=export_dir)

    _assert_sqlite_integrity(database_path)
    return manifest


def inspect_runtime_backup(*, backup_path: Path) -> dict[str, Any]:
    with ZipFile(backup_path.expanduser()) as archive:
        _validate_archive_members(archive)
        return _read_manifest(archive)


def _validate_backup_source(*, database_path: Path, upload_dir: Path, export_dir: Path) -> None:
    if not database_path.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {database_path}")
    if not upload_dir.is_dir():
        raise FileNotFoundError(f"Upload directory does not exist: {upload_dir}")
    if not export_dir.is_dir():
        raise FileNotFoundError(f"Export directory does not exist: {export_dir}")

    _assert_sqlite_integrity(database_path)


def _assert_sqlite_integrity(database_path: Path) -> None:
    try:
        with closing(sqlite3.connect(database_path)) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"SQLite integrity check failed for {database_path}: {exc}") from exc

    if result is None or result[0] != "ok":
        raise ValueError(f"SQLite integrity check failed for {database_path}: {result[0] if result else 'no result'}")


def _copy_sqlite_database(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source_path)) as source_connection:
        with closing(sqlite3.connect(target_path)) as target_connection:
            source_connection.backup(target_connection)


def _relative_files(source_dir: Path) -> list[Path]:
    return sorted(
        (path.relative_to(source_dir) for path in source_dir.rglob("*") if path.is_file()),
        key=lambda path: path.as_posix(),
    )


def _write_tree_to_archive(
    *,
    archive: ZipFile,
    source_dir: Path,
    archive_root: str,
    files: list[Path],
) -> None:
    for relative_path in files:
        archive.write(source_dir / relative_path, f"{archive_root}/{relative_path.as_posix()}")


def _build_backup_filename(*, created_at: datetime, label: str | None) -> str:
    timestamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    normalized_label = _normalize_label(label)
    suffix = f"-{normalized_label}" if normalized_label else ""
    return f"production-planning-ai-runtime-{timestamp}{suffix}.zip"


def _unique_backup_path(preferred_path: Path) -> Path:
    if not preferred_path.exists():
        return preferred_path

    for suffix in range(2, 1000):
        candidate = preferred_path.with_name(f"{preferred_path.stem}-{suffix}{preferred_path.suffix}")
        if not candidate.exists():
            return candidate

    raise FileExistsError(f"Could not find an available backup filename near {preferred_path}.")


def _normalize_label(label: str | None) -> str:
    if label is None:
        return ""

    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", label.strip()).strip("-")
    return normalized[:64]


def _validate_archive_members(archive: ZipFile) -> None:
    for member in archive.namelist():
        normalized_member = member.replace("\\", "/")
        path = PurePosixPath(normalized_member)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe backup archive member path: {member}")


def _assert_required_archive_members(archive: ZipFile) -> None:
    members = set(archive.namelist())
    if DATABASE_ARCHIVE_PATH not in members:
        raise ValueError("Backup archive is missing the SQLite database copy.")


def _read_manifest(archive: ZipFile) -> dict[str, Any]:
    try:
        manifest = json.loads(archive.read(MANIFEST_ARCHIVE_PATH))
    except KeyError as exc:
        raise ValueError("Backup archive is missing manifest.json.") from exc

    if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
        raise ValueError(f"Unsupported backup format version: {manifest.get('format_version')}")
    return manifest


def _ensure_restore_target_empty(*, database_path: Path, upload_dir: Path, export_dir: Path) -> None:
    conflicts: list[str] = []
    if database_path.exists():
        conflicts.append(database_path.as_posix())
    if _has_runtime_files(upload_dir):
        conflicts.append(upload_dir.as_posix())
    if _has_runtime_files(export_dir):
        conflicts.append(export_dir.as_posix())

    if conflicts:
        joined_conflicts = ", ".join(conflicts)
        raise FileExistsError(f"Restore target already contains runtime data: {joined_conflicts}. Use force to replace.")


def _has_runtime_files(directory: Path) -> bool:
    return directory.exists() and any(path.is_file() and path.name != ".gitkeep" for path in directory.rglob("*"))


def _prepare_restore_target(*, database_path: Path, upload_dir: Path, export_dir: Path, force: bool) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)

    if not force:
        return

    database_path.unlink(missing_ok=True)
    _clear_directory(upload_dir)
    _clear_directory(export_dir)


def _clear_directory(directory: Path) -> None:
    for child in directory.iterdir():
        if child.name == ".gitkeep":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _extract_database(*, archive: ZipFile, database_path: Path) -> None:
    try:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(DATABASE_ARCHIVE_PATH) as source:
            with database_path.open("wb") as target:
                shutil.copyfileobj(source, target)
    except KeyError as exc:
        raise ValueError("Backup archive is missing the SQLite database copy.") from exc


def _extract_tree(*, archive: ZipFile, archive_root: str, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{archive_root}/"
    for member in archive.infolist():
        normalized_member = member.filename.replace("\\", "/")
        if member.is_dir() or not normalized_member.startswith(prefix):
            continue

        relative_path = PurePosixPath(normalized_member).relative_to(archive_root)
        target_path = target_dir.joinpath(*relative_path.parts)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source:
            with target_path.open("wb") as target:
                shutil.copyfileobj(source, target)


def _copy_tree(*, source_dir: Path, target_dir: Path) -> None:
    if not source_dir.exists():
        return

    for source_path in source_dir.rglob("*"):
        if source_path.is_dir():
            continue

        relative_path = source_path.relative_to(source_dir)
        target_path = target_dir / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)


def _paths_from_args(args: argparse.Namespace) -> RuntimeBackupPaths:
    settings_paths = runtime_paths_from_settings()
    return RuntimeBackupPaths(
        database_path=Path(args.database_path) if args.database_path else settings_paths.database_path,
        upload_dir=Path(args.upload_dir) if args.upload_dir else settings_paths.upload_dir,
        export_dir=Path(args.export_dir) if args.export_dir else settings_paths.export_dir,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Back up and restore Production Planning AI runtime data.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a runtime backup archive.")
    create_parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR.as_posix())
    create_parser.add_argument("--label", default=None)
    create_parser.add_argument("--database-path", default=None)
    create_parser.add_argument("--upload-dir", default=None)
    create_parser.add_argument("--export-dir", default=None)

    inspect_parser = subparsers.add_parser("inspect", help="Print backup manifest JSON.")
    inspect_parser.add_argument("backup_path")

    restore_parser = subparsers.add_parser("restore", help="Restore a backup archive into runtime paths.")
    restore_parser.add_argument("backup_path")
    restore_parser.add_argument("--database-path", default=None)
    restore_parser.add_argument("--upload-dir", default=None)
    restore_parser.add_argument("--export-dir", default=None)
    restore_parser.add_argument("--force", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.command == "create":
        paths = _paths_from_args(args)
        result = create_runtime_backup(
            database_path=paths.database_path,
            upload_dir=paths.upload_dir,
            export_dir=paths.export_dir,
            backup_dir=Path(args.backup_dir),
            label=args.label,
        )
        print(result.backup_path.as_posix())
        return 0

    if args.command == "inspect":
        manifest = inspect_runtime_backup(backup_path=Path(args.backup_path))
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    if args.command == "restore":
        paths = _paths_from_args(args)
        manifest = restore_runtime_backup(
            backup_path=Path(args.backup_path),
            database_path=paths.database_path,
            upload_dir=paths.upload_dir,
            export_dir=paths.export_dir,
            force=args.force,
        )
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
