import ast
import tempfile
import unittest
from importlib.metadata import version
from pathlib import Path

from fastapi.testclient import TestClient

from document_qa_server.api.app import create_app
from document_qa_server.settings import ServerSettings


class ServerArchitectureTests(unittest.TestCase):
    """守护 server 的 api → services → core 单向依赖。"""

    def test_api_modules_do_not_import_core_package(self) -> None:
        """协议层不得直接导入 document_qa，核心类型由服务层封装。"""

        api_dir = (
            Path(__file__).resolve().parents[1]
            / "server"
            / "src"
            / "document_qa_server"
            / "api"
        )
        violations: list[str] = []
        for path in sorted(api_dir.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (
                    node.module == "document_qa"
                    or (node.module or "").startswith("document_qa.")
                ):
                    violations.append(f"{path.name}:{node.lineno} {node.module}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "document_qa" or alias.name.startswith(
                            "document_qa."
                        ):
                            violations.append(
                                f"{path.name}:{node.lineno} {alias.name}"
                            )

        self.assertEqual(violations, [])

    def test_health_uses_distribution_version(self) -> None:
        """应用版本只能来自发行包元数据，避免 API 与 pyproject 漂移。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = ServerSettings(
                artifacts_dir=root,
                samples_dir=Path(__file__).resolve().parents[1] / "examples",
                log_file_enabled=False,
                ocr_enabled=False,
            )
            response = TestClient(create_app(settings=settings)).get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version"], version("document-qa-server"))


if __name__ == "__main__":
    unittest.main()
