"""文档解析器。"""

from document_qa.parsers.base import DocumentParser, DocumentParsingError
from document_qa.parsers.pymupdf_parser import PyMuPDFParser

__all__ = ["DocumentParser", "DocumentParsingError", "PyMuPDFParser"]

