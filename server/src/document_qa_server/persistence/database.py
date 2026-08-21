"""SQLite 连接、Schema 迁移与数据库数据字典。

原始文档、渲染图和导出文件仍保存在文件系统；本模块保存其元数据、
业务关系以及完整 QAReport。SQLite 不支持 COMMENT ON，因此 Schema SQL
保留中文行注释，并把同一份说明写入 schema_descriptions 供运行时查询。
"""

from __future__ import annotations

import contextlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


SCHEMA_VERSION = 4


# 表名、字段名（空串代表表）与中文用途。该数据同时是可查询的数据字典。
SCHEMA_DESCRIPTIONS: tuple[tuple[str, str, str], ...] = (
    ("schema_migrations", "", "记录已应用的数据库结构迁移，保证升级幂等可审计。"),
    ("schema_migrations", "version", "单调递增的迁移版本号。"),
    ("schema_migrations", "name", "迁移名称，用于识别本次结构变化。"),
    ("schema_migrations", "applied_at", "迁移完成的 UTC ISO 时间。"),
    ("schema_descriptions", "", "数据库内置数据字典，说明每张表和每个字段的业务用途。"),
    ("schema_descriptions", "table_name", "被说明的表名。"),
    ("schema_descriptions", "column_name", "被说明的字段名；空串表示整张表。"),
    ("schema_descriptions", "description", "表或字段的中文用途说明。"),
    ("legacy_imports", "", "记录旧目录 JSON 的一次性导入结果，避免重启后反复覆盖数据库状态。"),
    ("legacy_imports", "import_key", "遗留数据来源标识，例如 history_json_v1。"),
    ("legacy_imports", "source_count", "执行导入时发现的源文件数量。"),
    ("legacy_imports", "imported_count", "成功校验并写入数据库的记录数量。"),
    ("legacy_imports", "completed_at", "本次一次性导入完成的 UTC ISO 时间。"),
    ("stored_files", "", "登记服务器持有或引用的文档文件元数据，不保存文件二进制。"),
    ("stored_files", "file_id", "文件稳定标识；有内容摘要时使用 SHA-256。"),
    ("stored_files", "sha256", "文件内容 SHA-256；遗留文件缺失时允许为空。"),
    ("stored_files", "original_name", "面向用户展示的原始文件名。"),
    ("stored_files", "storage_path", "服务器文件系统中的绝对存储路径。"),
    ("stored_files", "file_format", "小写扩展名，用于格式识别和筛选。"),
    ("stored_files", "size_bytes", "文件字节数；遗留文件缺失时允许为空。"),
    ("stored_files", "origin", "文件来源：builtin、upload、sample 或 legacy。"),
    ("stored_files", "availability", "文件当前是否可读取：present 或 missing。"),
    ("stored_files", "created_at", "文件首次登记的 UTC ISO 时间。"),
    ("samples", "", "可复用的源文档与目标文档样本对。"),
    ("samples", "sample_id", "样本稳定标识。"),
    ("samples", "name", "样本名称，同一库中不区分大小写唯一。"),
    ("samples", "description", "样本用途、场景或已知缺陷说明。"),
    ("samples", "source_file_id", "源文档文件标识。"),
    ("samples", "target_file_id", "目标文档文件标识。"),
    ("samples", "source_language", "源文档语言的 BCP 47 代码；und 表示尚未指定。"),
    ("samples", "target_language", "目标文档语言的 BCP 47 代码；und 表示尚未指定。"),
    ("samples", "origin", "样本来源：builtin 或 user。"),
    ("samples", "status", "样本状态：active 或 archived。"),
    ("samples", "created_at", "样本创建的 UTC ISO 时间。"),
    ("samples", "updated_at", "样本最近修改的 UTC ISO 时间。"),
    ("rule_profile_versions", "", "版本化规则配置；历史使用版本归档后仍保留。"),
    ("rule_profile_versions", "profile_id", "规则配置家族标识。"),
    ("rule_profile_versions", "version", "同一配置家族内的正整数版本号。"),
    ("rule_profile_versions", "filename", "兼容现有 API 的安全文件名标识。"),
    ("rule_profile_versions", "name", "规则配置显示名称。"),
    ("rule_profile_versions", "status", "配置状态：draft、published 或 archived。"),
    ("rule_profile_versions", "description", "规则配置用途说明。"),
    ("rule_profile_versions", "payload_json", "经 RuleProfile 校验后的完整 JSON。"),
    ("rule_profile_versions", "payload_sha256", "完整配置 JSON 的内容摘要。"),
    ("rule_profile_versions", "created_at", "版本首次保存的 UTC ISO 时间。"),
    ("rule_profile_versions", "updated_at", "版本最近保存的 UTC ISO 时间。"),
    ("glossary_versions", "", "版本化术语库；历史引用版本归档后仍保留。"),
    ("glossary_versions", "glossary_id", "术语库家族标识。"),
    ("glossary_versions", "version", "同一术语库家族内的正整数版本号。"),
    ("glossary_versions", "filename", "兼容现有 API 的安全文件名标识。"),
    ("glossary_versions", "name", "术语库显示名称。"),
    ("glossary_versions", "status", "术语库状态：active 或 archived。"),
    ("glossary_versions", "description", "术语库用途说明。"),
    ("glossary_versions", "entry_count", "该版本包含的术语条目数。"),
    ("glossary_versions", "payload_json", "经 Glossary 校验后的完整 JSON。"),
    ("glossary_versions", "payload_sha256", "完整术语库 JSON 的内容摘要。"),
    ("glossary_versions", "created_at", "版本首次保存的 UTC ISO 时间。"),
    ("glossary_versions", "updated_at", "版本最近保存的 UTC ISO 时间。"),
    ("comparison_records", "", "一次文档质检的可查询摘要及输入、配置关联。"),
    ("comparison_records", "record_id", "对比记录稳定标识，兼容现有历史 ID。"),
    ("comparison_records", "source_file_id", "本次对比使用的源文档文件标识。"),
    ("comparison_records", "target_file_id", "本次对比使用的目标文档文件标识。"),
    ("comparison_records", "sample_id", "可选样本来源；样本归档不影响历史。"),
    ("comparison_records", "source_display", "对比发生时的源文档展示名快照。"),
    ("comparison_records", "target_display", "对比发生时的目标文档展示名快照。"),
    ("comparison_records", "status", "报告状态：pass、review 或 fail。"),
    ("comparison_records", "document_score", "报告总分，范围 0 至 100。"),
    ("comparison_records", "page_count", "报告页面数量。"),
    ("comparison_records", "issue_total", "报告问题总数。"),
    ("comparison_records", "rule_profile_id", "本次使用的规则配置家族标识。"),
    ("comparison_records", "rule_profile_version", "本次使用的规则配置版本号。"),
    ("comparison_records", "rule_profile_reference", "面向外部展示的规则版本引用快照。"),
    ("comparison_records", "normalized_from_json", "Office 归一化来源等元数据 JSON。"),
    ("comparison_records", "rendered_json", "源、目标渲染页相对路径索引 JSON。"),
    ("comparison_records", "created_at", "对比完成并持久化的 UTC ISO 时间。"),
    ("comparison_reports", "", "保存不可变的完整 QAReport JSON，与对比摘要一对一。"),
    ("comparison_reports", "record_id", "所属对比记录标识，同时是主键和外键。"),
    ("comparison_reports", "schema_version", "报告数据结构版本，用于兼容迁移。"),
    ("comparison_reports", "report_json", "完整 QAReport JSON 正文。"),
    ("comparison_reports", "byte_size", "UTF-8 报告正文的字节数。"),
    ("comparison_reports", "report_sha256", "完整报告正文的 SHA-256。"),
    ("comparison_reports", "created_at", "完整报告入库的 UTC ISO 时间。"),
    ("comparison_glossaries", "", "记录一次对比实际使用的术语库版本，保证历史可追溯。"),
    ("comparison_glossaries", "record_id", "所属对比记录标识，与对比记录一对一。"),
    ("comparison_glossaries", "glossary_id", "本次使用的术语库家族标识。"),
    ("comparison_glossaries", "glossary_version", "本次使用的术语库版本号。"),
    ("comparison_glossaries", "glossary_reference", "面向外部展示的术语库版本引用快照。"),
    ("review_tasks", "", "人工复核任务的报告身份快照，作为 Issue 判定父记录。"),
    ("review_tasks", "task_id", "复核任务标识，兼容现有前端任务键。"),
    ("review_tasks", "source_document_id", "源文档内容标识快照。"),
    ("review_tasks", "target_document_id", "目标文档内容标识快照。"),
    ("review_tasks", "rule_profile_reference", "复核对应的规则配置引用快照。"),
    ("review_tasks", "updated_at", "该复核任务最近变更的 UTC ISO 时间。"),
    ("review_decisions", "", "对单条 Issue 的人工确认、误报或忽略判定。"),
    ("review_decisions", "task_id", "所属复核任务标识。"),
    ("review_decisions", "issue_id", "报告内稳定 Issue 标识。"),
    ("review_decisions", "decision", "人工结论：confirmed、false_positive 或 ignored。"),
    ("review_decisions", "note", "复核人员补充说明。"),
    ("review_decisions", "reviewed_at", "该判定最近保存的 UTC ISO 时间。"),
)


class Database:
    """管理 SQLite 连接参数、事务和版本化 Schema。"""

    def __init__(self, *, artifacts_dir: Path) -> None:
        """在产物目录创建 metadata.sqlite3 并完成幂等迁移。"""

        artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.path = artifacts_dir / "metadata.sqlite3"
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        """创建短生命周期连接并统一开启完整性与并发参数。"""

        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """开启立即事务，异常回滚，成功原子提交。"""

        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        """串行执行未应用迁移，并写入数据库内数据字典。"""

        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
            )
            applied = {
                row[0]
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            if 1 not in applied:
                self._migration_1(connection)
                connection.execute(
                    "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                    (1, "initial_business_schema", self.now()),
                )
            if 2 not in applied:
                self._migration_2(connection)
                connection.execute(
                    "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                    (2, "legacy_import_audit", self.now()),
                )
            if 3 not in applied:
                self._migration_3(connection)
                connection.execute(
                    "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                    (3, "comparison_glossary_relation", self.now()),
                )
            if 4 not in applied:
                self._migration_4(connection)
                connection.execute(
                    "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                    (4, "sample_language_pair", self.now()),
                )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _migration_1(self, connection: sqlite3.Connection) -> None:
        """建立首版完整业务 Schema、约束、索引和字段说明。"""

        connection.executescript(
            """
            -- 数据字典：SQLite 无 COMMENT ON，以本表提供可查询中文注释。
            CREATE TABLE schema_descriptions (
                table_name TEXT NOT NULL,
                column_name TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL,
                PRIMARY KEY (table_name, column_name)
            );

            -- 文件元数据：二进制留在文件系统，数据库只保存身份与安全路径。
            CREATE TABLE stored_files (
                file_id TEXT PRIMARY KEY,
                sha256 TEXT UNIQUE CHECK (sha256 IS NULL OR length(sha256) = 64),
                original_name TEXT NOT NULL,
                storage_path TEXT NOT NULL UNIQUE,
                file_format TEXT NOT NULL,
                size_bytes INTEGER CHECK (size_bytes IS NULL OR size_bytes >= 0),
                origin TEXT NOT NULL CHECK (origin IN ('builtin','upload','sample','legacy')),
                availability TEXT NOT NULL CHECK (availability IN ('present','missing')),
                created_at TEXT NOT NULL
            );

            -- 样本对：源与目标必须是两个已登记文件，删除使用归档状态。
            CREATE TABLE samples (
                sample_id TEXT PRIMARY KEY,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                source_file_id TEXT NOT NULL REFERENCES stored_files(file_id) ON DELETE RESTRICT,
                target_file_id TEXT NOT NULL REFERENCES stored_files(file_id) ON DELETE RESTRICT,
                origin TEXT NOT NULL CHECK (origin IN ('builtin','user')),
                status TEXT NOT NULL CHECK (status IN ('active','archived')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK (source_file_id <> target_file_id)
            );

            -- 规则配置按 profile_id + version 不可变寻址，归档代替物理删除。
            CREATE TABLE rule_profile_versions (
                profile_id TEXT NOT NULL,
                version INTEGER NOT NULL CHECK (version > 0),
                filename TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('draft','published','archived')),
                description TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (profile_id, version)
            );

            -- 术语库同样按家族与版本寻址，历史引用不因归档失效。
            CREATE TABLE glossary_versions (
                glossary_id TEXT NOT NULL,
                version INTEGER NOT NULL CHECK (version > 0),
                filename TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('active','archived')),
                description TEXT NOT NULL DEFAULT '',
                entry_count INTEGER NOT NULL CHECK (entry_count >= 0),
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (glossary_id, version)
            );

            -- 对比摘要：高频列表字段独立存列，不必解析完整报告 JSON。
            CREATE TABLE comparison_records (
                record_id TEXT PRIMARY KEY,
                source_file_id TEXT NOT NULL REFERENCES stored_files(file_id) ON DELETE RESTRICT,
                target_file_id TEXT NOT NULL REFERENCES stored_files(file_id) ON DELETE RESTRICT,
                sample_id TEXT REFERENCES samples(sample_id) ON DELETE SET NULL,
                source_display TEXT NOT NULL,
                target_display TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pass','review','fail')),
                document_score REAL NOT NULL CHECK (document_score BETWEEN 0 AND 100),
                page_count INTEGER NOT NULL CHECK (page_count >= 0),
                issue_total INTEGER NOT NULL CHECK (issue_total >= 0),
                rule_profile_id TEXT NOT NULL,
                rule_profile_version INTEGER NOT NULL,
                rule_profile_reference TEXT NOT NULL,
                normalized_from_json TEXT,
                rendered_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (rule_profile_id, rule_profile_version)
                    REFERENCES rule_profile_versions(profile_id, version) ON DELETE RESTRICT
            );

            -- 完整报告与摘要一对一，同一事务写入以避免孤儿记录。
            CREATE TABLE comparison_reports (
                record_id TEXT PRIMARY KEY REFERENCES comparison_records(record_id) ON DELETE CASCADE,
                schema_version INTEGER NOT NULL CHECK (schema_version > 0),
                report_json TEXT NOT NULL,
                byte_size INTEGER NOT NULL CHECK (byte_size >= 2),
                report_sha256 TEXT NOT NULL CHECK (length(report_sha256) = 64),
                created_at TEXT NOT NULL
            );

            -- 复核父记录保存报告身份，判定表只保存逐 Issue 可变结论。
            CREATE TABLE review_tasks (
                task_id TEXT PRIMARY KEY,
                source_document_id TEXT NOT NULL,
                target_document_id TEXT NOT NULL,
                rule_profile_reference TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE review_decisions (
                task_id TEXT NOT NULL REFERENCES review_tasks(task_id) ON DELETE CASCADE,
                issue_id TEXT NOT NULL,
                decision TEXT NOT NULL CHECK (decision IN ('confirmed','false_positive','ignored')),
                note TEXT NOT NULL DEFAULT '',
                reviewed_at TEXT NOT NULL,
                PRIMARY KEY (task_id, issue_id)
            );

            CREATE INDEX comparison_records_created_idx ON comparison_records(created_at DESC);
            CREATE INDEX comparison_records_sample_idx ON comparison_records(sample_id, created_at DESC);
            CREATE INDEX comparison_records_status_idx ON comparison_records(status, created_at DESC);
            CREATE INDEX samples_status_idx ON samples(status, updated_at DESC);
            CREATE INDEX review_decisions_decision_idx ON review_decisions(decision);
            """
        )
        connection.executemany(
            "INSERT INTO schema_descriptions(table_name, column_name, description) VALUES (?, ?, ?)",
            SCHEMA_DESCRIPTIONS,
        )

    def _migration_2(self, connection: sqlite3.Connection) -> None:
        """增加一次性遗留导入审计，阻止旧 JSON 在重启后覆盖归档状态。"""

        connection.execute(
            "CREATE TABLE legacy_imports ("
            "import_key TEXT PRIMARY KEY, source_count INTEGER NOT NULL CHECK(source_count >= 0), "
            "imported_count INTEGER NOT NULL CHECK(imported_count >= 0), completed_at TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT OR REPLACE INTO schema_descriptions("
            "table_name, column_name, description) VALUES (?, ?, ?)",
            [item for item in SCHEMA_DESCRIPTIONS if item[0] == "legacy_imports"],
        )

    def legacy_import_done(self, import_key: str) -> bool:
        """判断某类旧 JSON 是否已经完成一次性导入。"""

        with self.connect() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM legacy_imports WHERE import_key = ?", (import_key,)
                ).fetchone()
                is not None
            )

    def _migration_3(self, connection: sqlite3.Connection) -> None:
        """增加对比记录与术语库不可变版本之间的关系。"""

        connection.execute(
            "CREATE TABLE comparison_glossaries ("
            "record_id TEXT PRIMARY KEY REFERENCES comparison_records(record_id) ON DELETE CASCADE, "
            "glossary_id TEXT NOT NULL, glossary_version INTEGER NOT NULL, "
            "glossary_reference TEXT NOT NULL, "
            "FOREIGN KEY(glossary_id, glossary_version) "
            "REFERENCES glossary_versions(glossary_id, version) ON DELETE RESTRICT)"
        )
        connection.executemany(
            "INSERT OR REPLACE INTO schema_descriptions("
            "table_name, column_name, description) VALUES (?, ?, ?)",
            [item for item in SCHEMA_DESCRIPTIONS if item[0] == "comparison_glossaries"],
        )

    def mark_legacy_import(
        self, import_key: str, *, source_count: int, imported_count: int
    ) -> None:
        """记录一次性导入审计；重复写保持首次结果。"""

        with self.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO legacy_imports("
                "import_key, source_count, imported_count, completed_at) VALUES (?, ?, ?, ?)",
                (import_key, source_count, imported_count, self.now()),
            )

    def _migration_4(self, connection: sqlite3.Connection) -> None:
        """给样本增加结构化源语言和目标语言，并补齐可证明的内置语言对。"""

        connection.execute(
            "ALTER TABLE samples ADD COLUMN source_language TEXT NOT NULL "
            "DEFAULT 'und' CHECK(length(source_language) BETWEEN 2 AND 35)"
        )
        connection.execute(
            "ALTER TABLE samples ADD COLUMN target_language TEXT NOT NULL "
            "DEFAULT 'und' CHECK(length(target_language) BETWEEN 2 AND 35)"
        )
        connection.execute(
            "UPDATE samples SET source_language = 'en', target_language = 'zh-CN' "
            "WHERE sample_id IN ("
            "SELECT s.sample_id FROM samples s "
            "JOIN stored_files sf ON sf.file_id = s.source_file_id "
            "JOIN stored_files tf ON tf.file_id = s.target_file_id "
            "WHERE sf.original_name LIKE '%-en.%' AND tf.original_name LIKE '%-zh.%')"
        )
        connection.execute(
            "CREATE INDEX samples_language_pair_idx "
            "ON samples(source_language, target_language, status)"
        )
        connection.executemany(
            "INSERT OR REPLACE INTO schema_descriptions("
            "table_name, column_name, description) VALUES (?, ?, ?)",
            [
                item
                for item in SCHEMA_DESCRIPTIONS
                if item[0] == "samples"
                and item[1] in {"source_language", "target_language"}
            ],
        )

    @staticmethod
    def now() -> str:
        """返回统一的 UTC ISO 时间字符串。"""

        return datetime.now(timezone.utc).isoformat()
