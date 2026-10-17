"""The orders creation-time index is added once, tolerates a rerun and is removed on downgrade."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = Path(__file__).resolve().parents[1]


class OrdersCreatedAtIndexMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        spec = importlib.util.spec_from_file_location("orders_index_migration", ROOT / "alembic/versions/0063_orders_created_at_index.py")
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        self.engine = sa.create_engine("sqlite://")
        with self.engine.begin() as conn:
            conn.execute(sa.text("CREATE TABLE orders (id INTEGER PRIMARY KEY, created_at DATETIME)"))

    def run_step(self, conn: sa.Connection, *, down: bool = False) -> None:
        with Operations.context(MigrationContext.configure(conn)):
            (self.migration.downgrade if down else self.migration.upgrade)()

    def names(self, conn: sa.Connection) -> set[str]:
        return {index["name"] for index in sa.inspect(conn).get_indexes("orders")}

    def test_upgrade_twice_then_downgrade(self) -> None:
        with self.engine.begin() as conn:
            self.run_step(conn)
            self.run_step(conn)
            self.assertIn("ix_orders_created_at", self.names(conn))
            self.run_step(conn, down=True)
            self.assertNotIn("ix_orders_created_at", self.names(conn))

    def test_a_database_without_the_table_is_left_alone(self) -> None:
        with sa.create_engine("sqlite://").begin() as conn:
            self.run_step(conn)
            self.run_step(conn, down=True)

    def test_there_is_a_single_migration_head(self) -> None:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "alembic"))
        self.assertEqual(ScriptDirectory.from_config(config).get_heads(), ["0063_orders_created_at_index"])
