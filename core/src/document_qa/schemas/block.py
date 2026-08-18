"""原始文档 Block 模型。"""

from pydantic import Field

from document_qa.schemas.common import (
    BoundingBox,
    Content,
    ElementType,
    Metadata,
    SchemaModel,
    TextStyle,
)


class Block(SchemaModel):
    """解析器生成的最小文档元素。"""

    id: str = Field(min_length=1)
    page: int = Field(ge=1)
    type: ElementType
    bbox: BoundingBox
    style: TextStyle | None = None
    content: Content | None = None
    parent_id: str | None = None
    children: list[str] = Field(default_factory=list)
    metadata: Metadata = Field(default_factory=dict)
