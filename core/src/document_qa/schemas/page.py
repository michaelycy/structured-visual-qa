"""归一化页面模型。"""

from pydantic import Field, model_validator

from document_qa.schemas.block import Block
from document_qa.schemas.common import Metadata, SchemaModel
from document_qa.schemas.region import Region


class Page(SchemaModel):
    """包含原始 Block 和分组 Region 的单个归一化页面。"""

    document_id: str = Field(min_length=1)
    page: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    blocks: list[Block] = Field(default_factory=list)
    regions: list[Region] = Field(default_factory=list)
    metadata: Metadata = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_children(self) -> "Page":
        """校验页内 ID、页码归属和 Region 对 Block 的引用。"""

        block_ids = [block.id for block in self.blocks]
        region_ids = [region.id for region in self.regions]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("block ids must be unique within a page")
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("region ids must be unique within a page")
        if any(block.page != self.page for block in self.blocks):
            raise ValueError("all blocks must belong to this page")
        if any(region.page != self.page for region in self.regions):
            raise ValueError("all regions must belong to this page")
        unknown_block_ids = {
            block_id
            for region in self.regions
            for block_id in region.children
            if block_id not in set(block_ids)
        }
        if unknown_block_ids:
            unknown = ", ".join(sorted(unknown_block_ids))
            raise ValueError(f"regions reference unknown blocks: {unknown}")
        return self
