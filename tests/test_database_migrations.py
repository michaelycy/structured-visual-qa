import sqlite3
import tempfile
import unittest
from pathlib import Path

from document_qa_server.persistence.database import (
    SCHEMA_DESCRIPTIONS,
    SCHEMA_VERSION,
    Database,
)


class DatabaseMigrationTests(unittest.TestCase):
    """验证 SQLite 迁移的原子性、幂等性和数据字典完整性。"""

    def test_fresh_database_is_complete_and_repeatable(self) -> None:
        """空库应完整升级，重复初始化不得改变迁移记录。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = Database(artifacts_dir=root)
            Database(artifacts_dir=root)

            with database.connect() as connection:
                versions = [
                    row[0]
                    for row in connection.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    )
                ]
                descriptions = connection.execute(
                    "SELECT COUNT(*) FROM schema_descriptions"
                ).fetchone()[0]
                user_version = connection.execute("PRAGMA user_version").fetchone()[0]

            self.assertEqual(versions, list(range(1, SCHEMA_VERSION + 1)))
            self.assertEqual(descriptions, len(SCHEMA_DESCRIPTIONS))
            self.assertEqual(user_version, SCHEMA_VERSION)

    def test_failed_initial_migration_leaves_no_partial_schema(self) -> None:
        """迁移中途失败时业务表和迁移审计必须一起回滚。"""

        class FailingDatabase(Database):
            def _migration_1(self, connection: sqlite3.Connection) -> None:
                super()._migration_1(connection)
                raise sqlite3.OperationalError("injected migration failure")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(sqlite3.OperationalError, "injected"):
                FailingDatabase(artifacts_dir=root)

            connection = sqlite3.connect(root / "metadata.sqlite3")
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                applied = connection.execute(
                    "SELECT COUNT(*) FROM schema_migrations"
                ).fetchone()[0]
            finally:
                connection.close()

            self.assertEqual(tables, {"schema_migrations"})
            self.assertEqual(applied, 0)
            Database(artifacts_dir=root)


if __name__ == "__main__":
    unittest.main()
