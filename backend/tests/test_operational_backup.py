import json
import sqlite3
from contextlib import closing
from pathlib import Path
from zipfile import ZipFile

import pytest

from app.operations import backup
from app.operations.backup import (
    DATABASE_ARCHIVE_PATH,
    MANIFEST_ARCHIVE_PATH,
    create_runtime_backup,
    inspect_runtime_backup,
    restore_runtime_backup,
)


def test_runtime_backup_archive_restores_sqlite_uploads_and_exports(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "app.sqlite3"
    upload_dir = tmp_path / "data" / "uploads"
    export_dir = tmp_path / "data" / "exports"
    backup_dir = tmp_path / "data" / "backups"
    database_path.parent.mkdir(parents=True)
    upload_dir.mkdir(parents=True)
    export_dir.mkdir(parents=True)
    _write_database(database_path, value="before-backup")
    (upload_dir / "upload-1").mkdir()
    (upload_dir / "upload-1" / "plan.xlsx").write_bytes(b"upload-bytes")
    (export_dir / "run-1").mkdir()
    (export_dir / "run-1" / "machine_load.xlsx").write_bytes(b"export-bytes")

    result = create_runtime_backup(
        database_path=database_path,
        upload_dir=upload_dir,
        export_dir=export_dir,
        backup_dir=backup_dir,
        label="pilot smoke",
    )

    assert result.backup_path.name.endswith("-pilot-smoke.zip")
    assert result.manifest["file_counts"] == {"database": 1, "exports": 1, "uploads": 1}
    with ZipFile(result.backup_path) as archive:
        assert MANIFEST_ARCHIVE_PATH in archive.namelist()
        assert DATABASE_ARCHIVE_PATH in archive.namelist()
        assert "uploads/upload-1/plan.xlsx" in archive.namelist()
        assert "exports/run-1/machine_load.xlsx" in archive.namelist()

    restore_root = tmp_path / "restore"
    restored_manifest = restore_runtime_backup(
        backup_path=result.backup_path,
        database_path=restore_root / "app.sqlite3",
        upload_dir=restore_root / "uploads",
        export_dir=restore_root / "exports",
    )

    assert restored_manifest["format_version"] == 1
    assert _read_value(restore_root / "app.sqlite3") == "before-backup"
    assert (restore_root / "uploads" / "upload-1" / "plan.xlsx").read_bytes() == b"upload-bytes"
    assert (restore_root / "exports" / "run-1" / "machine_load.xlsx").read_bytes() == b"export-bytes"
    assert inspect_runtime_backup(backup_path=result.backup_path)["file_counts"]["uploads"] == 1


def test_runtime_restore_refuses_to_overwrite_existing_runtime_data_without_force(tmp_path: Path) -> None:
    database_path = tmp_path / "source.sqlite3"
    upload_dir = tmp_path / "source_uploads"
    export_dir = tmp_path / "source_exports"
    upload_dir.mkdir()
    export_dir.mkdir()
    _write_database(database_path, value="source")

    result = create_runtime_backup(
        database_path=database_path,
        upload_dir=upload_dir,
        export_dir=export_dir,
        backup_dir=tmp_path / "backups",
    )

    restore_database_path = tmp_path / "restore.sqlite3"
    restore_upload_dir = tmp_path / "restore_uploads"
    restore_export_dir = tmp_path / "restore_exports"
    restore_upload_dir.mkdir()
    restore_export_dir.mkdir()
    _write_database(restore_database_path, value="existing")

    with pytest.raises(FileExistsError, match="Use force to replace"):
        restore_runtime_backup(
            backup_path=result.backup_path,
            database_path=restore_database_path,
            upload_dir=restore_upload_dir,
            export_dir=restore_export_dir,
        )

    restore_runtime_backup(
        backup_path=result.backup_path,
        database_path=restore_database_path,
        upload_dir=restore_upload_dir,
        export_dir=restore_export_dir,
        force=True,
    )

    assert _read_value(restore_database_path) == "source"


def test_runtime_backup_uses_unique_filename_when_timestamp_and_label_collide(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "source.sqlite3"
    upload_dir = tmp_path / "uploads"
    export_dir = tmp_path / "exports"
    backup_dir = tmp_path / "backups"
    upload_dir.mkdir()
    export_dir.mkdir()
    _write_database(database_path, value="source")
    monkeypatch.setattr(backup, "_build_backup_filename", lambda *, created_at, label: "fixed.zip")

    first_result = create_runtime_backup(
        database_path=database_path,
        upload_dir=upload_dir,
        export_dir=export_dir,
        backup_dir=backup_dir,
    )
    second_result = create_runtime_backup(
        database_path=database_path,
        upload_dir=upload_dir,
        export_dir=export_dir,
        backup_dir=backup_dir,
    )

    assert first_result.backup_path.name == "fixed.zip"
    assert second_result.backup_path.name == "fixed-2.zip"
    assert inspect_runtime_backup(backup_path=first_result.backup_path)["format_version"] == 1
    assert inspect_runtime_backup(backup_path=second_result.backup_path)["format_version"] == 1


def test_force_restore_preserves_existing_runtime_data_when_archive_is_missing_database(tmp_path: Path) -> None:
    bad_backup_path = tmp_path / "bad-backup.zip"
    _write_backup_archive(
        bad_backup_path,
        members={
            MANIFEST_ARCHIVE_PATH: json.dumps({"format_version": 1}).encode(),
            "uploads/upload-1/plan.xlsx": b"new-upload",
        },
    )
    target = _write_existing_runtime_target(tmp_path)

    with pytest.raises(ValueError, match="missing the SQLite database copy"):
        restore_runtime_backup(
            backup_path=bad_backup_path,
            database_path=target["database_path"],
            upload_dir=target["upload_dir"],
            export_dir=target["export_dir"],
            force=True,
        )

    _assert_existing_runtime_target_preserved(target)


def test_force_restore_preserves_existing_runtime_data_when_staged_database_is_invalid(tmp_path: Path) -> None:
    bad_backup_path = tmp_path / "bad-sqlite.zip"
    _write_backup_archive(
        bad_backup_path,
        members={
            MANIFEST_ARCHIVE_PATH: json.dumps({"format_version": 1}).encode(),
            DATABASE_ARCHIVE_PATH: b"not a sqlite database",
            "uploads/upload-1/plan.xlsx": b"new-upload",
        },
    )
    target = _write_existing_runtime_target(tmp_path)

    with pytest.raises(ValueError, match="SQLite integrity check failed"):
        restore_runtime_backup(
            backup_path=bad_backup_path,
            database_path=target["database_path"],
            upload_dir=target["upload_dir"],
            export_dir=target["export_dir"],
            force=True,
        )

    _assert_existing_runtime_target_preserved(target)


def test_force_restore_rejects_unsafe_archive_paths_before_touching_runtime_data(tmp_path: Path) -> None:
    bad_backup_path = tmp_path / "unsafe-backup.zip"
    _write_backup_archive(
        bad_backup_path,
        members={
            MANIFEST_ARCHIVE_PATH: json.dumps({"format_version": 1}).encode(),
            DATABASE_ARCHIVE_PATH: b"not reached",
            "uploads\\..\\evil.txt": b"evil",
        },
    )
    target = _write_existing_runtime_target(tmp_path)

    with pytest.raises(ValueError, match="Unsafe backup archive member path"):
        restore_runtime_backup(
            backup_path=bad_backup_path,
            database_path=target["database_path"],
            upload_dir=target["upload_dir"],
            export_dir=target["export_dir"],
            force=True,
        )

    _assert_existing_runtime_target_preserved(target)


def test_runtime_backup_cli_create_and_inspect_round_trips_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / "cli.sqlite3"
    upload_dir = tmp_path / "uploads"
    export_dir = tmp_path / "exports"
    backup_dir = tmp_path / "backups"
    upload_dir.mkdir()
    export_dir.mkdir()
    _write_database(database_path, value="cli")

    exit_code = backup.main(
        [
            "create",
            "--database-path",
            database_path.as_posix(),
            "--upload-dir",
            upload_dir.as_posix(),
            "--export-dir",
            export_dir.as_posix(),
            "--backup-dir",
            backup_dir.as_posix(),
            "--label",
            "cli-smoke",
        ]
    )

    assert exit_code == 0
    backup_path = Path(capsys.readouterr().out.strip())
    assert backup_path.is_file()

    inspect_exit_code = backup.main(["inspect", backup_path.as_posix()])

    assert inspect_exit_code == 0
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["file_counts"] == {"database": 1, "exports": 0, "uploads": 0}


def _write_database(database_path: Path, *, value: str) -> None:
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("CREATE TABLE smoke_check (value TEXT NOT NULL)")
        connection.execute("INSERT INTO smoke_check (value) VALUES (?)", (value,))
        connection.commit()


def _read_value(database_path: Path) -> str:
    with closing(sqlite3.connect(database_path)) as connection:
        return connection.execute("SELECT value FROM smoke_check").fetchone()[0]


def _write_backup_archive(backup_path: Path, *, members: dict[str, bytes]) -> None:
    with ZipFile(backup_path, "w") as archive:
        for path, content in members.items():
            archive.writestr(path, content)


def _write_existing_runtime_target(tmp_path: Path) -> dict[str, Path]:
    database_path = tmp_path / "existing" / "app.sqlite3"
    upload_dir = tmp_path / "existing" / "uploads"
    export_dir = tmp_path / "existing" / "exports"
    database_path.parent.mkdir()
    upload_dir.mkdir()
    export_dir.mkdir()
    _write_database(database_path, value="existing")
    (upload_dir / "existing-upload.xlsx").write_bytes(b"existing-upload")
    (export_dir / "existing-export.xlsx").write_bytes(b"existing-export")
    return {
        "database_path": database_path,
        "upload_dir": upload_dir,
        "export_dir": export_dir,
    }


def _assert_existing_runtime_target_preserved(target: dict[str, Path]) -> None:
    assert _read_value(target["database_path"]) == "existing"
    assert (target["upload_dir"] / "existing-upload.xlsx").read_bytes() == b"existing-upload"
    assert (target["export_dir"] / "existing-export.xlsx").read_bytes() == b"existing-export"
