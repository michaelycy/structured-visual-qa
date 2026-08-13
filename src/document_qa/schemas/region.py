"""分组后的语义 Region 模型。"""

from pydantic import Field

from document_qa.schemas.common import (
    BoundingBox,
    Content,
    ElementType,
    Metadata,
    RegionRelationships,
    SchemaModel,
    TextStyle,
)


class Region(SchemaModel):
    """由一个或多个 Block 组成的语义比较单元。"""

    id: str = Field(min_length=1)
    page: int = Field(ge=1)
    type: ElementType
    bbox: BoundingBox
    style: TextStyle | None = None
    content: Content | None = None
    children: list[str] = Field(default_factory=list)
    relationships: RegionRelationships = Field(default_factory=RegionRelationships)
    metadata: Metadata = Field(default_factory=dict)
