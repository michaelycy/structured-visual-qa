"""归一化文档模型。"""

from pydantic import Field, model_validator

from document_qa.schemas.common import Metadata, SchemaModel
from document_qa.schemas.page import Page


class Document(SchemaModel):
    """保存一个文档的全部归一化页面。"""

    document_id: str = Field(min_length=1)
    source_path: str
    pages: list[Page] = Field(default_factory=list)
    metadata: Metadata = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_pages(self) -> "Document":
        """保证文档内页码唯一，并且页面属于当前文档。"""

        page_numbers = [page.page for page in self.pages]
        if len(page_numbers) != len(set(page_numbers)):
            raise ValueError("page numbers must be unique within a document")
        if any(page.document_id != self.document_id for page in self.pages):
            raise ValueError("all pages must belong to this document")
        return self

