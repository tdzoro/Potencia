"""Alembic database migration verification test.

Verifies that the entire migration chain from revision 0001_users to head
applies cleanly against a fresh database, can safely downgrade one step,
and can upgrade back to head without syntax or constraint errors.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config


def test_alembic_migration_cycle_on_clean_database() -> None:
    temp_dir = tempfile.mkdtemp(prefix="potencia-migration-test-")
    db_path = Path(temp_dir) / "migration_test.db"
    db_url = f"sqlite+pysqlite:///{db_path.as_posix()}"

    repo_root = Path(__file__).resolve().parent.parent.parent
    alembic_ini = repo_root / "backend" / "alembic.ini"
    migrations_dir = repo_root / "backend" / "migrations"

    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", db_url)

    # 1. Upgrade from empty to head (exercises all 7 revisions)
    command.upgrade(cfg, "head")
    assert db_path.exists()
    assert db_path.stat().st_size > 0

    # 2. Downgrade one step (0006_auth_tokens -> 0005_export_revision)
    command.downgrade(cfg, "-1")

    # 3. Upgrade back to head
    command.upgrade(cfg, "head")

    # Cleanup
    try:
        if db_path.exists():
            db_path.unlink()
        os.rmdir(temp_dir)
    except OSError:
        pass

