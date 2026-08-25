"""源区域与目标区域匹配。"""

from document_qa.matching.page_aligner import PageAlignment, PageAligner
from document_qa.matching.logical_region_composer import LogicalRegionComposer
from document_qa.matching.region_matcher import RegionMatcher

__all__ = [
    "LogicalRegionComposer",
    "PageAlignment",
    "PageAligner",
    "RegionMatcher",
]
