"""文档解析器抽象接口。"""

from pathlib import Path
from typing import Protocol

from document_qa.schemas import Document


class DocumentParsingError(RuntimeError):
    """表示输入文档无法安全、完整地转换为项目 Schema。"""


class DocumentParser(Protocol):
    """所有文档解析器必须实现的最小接口。"""

    def parse(self, path: Path, document_id: str | None = None) -> Document:
        """解析文档并返回与底层引擎无关的归一化模型。"""

        ...

