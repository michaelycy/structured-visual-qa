"""为不同检测器生成一致的可读区域证据。"""

from __future__ import annotations

from typing import Any

from document_qa.schemas import Region, RegionMatch


def region_evidence(
    source: Region | None = None,
    target: Region | None = None,
    match: RegionMatch | None = None,
) -> dict[str, Any]:
    """返回可安全写入 Issue.metrics 的源/目标文本、几何与匹配证据。"""

    evidence: dict[str, Any] = {}
    if source is not None:
        evidence.update(
            {
                "source_text": source.content.text if source.content else None,
                "source_bbox": source.bbox.model_dump(mode="json"),
                "source_region_type": source.type.value,
            }
        )
        source_atomic_ids = source.metadata.get("atomic_region_ids")
        if isinstance(source_atomic_ids, list) and source_atomic_ids:
            evidence.update(
                {
                    "source_region_ids": source_atomic_ids,
                    "source_logical_region_count": len(source_atomic_ids),
                }
            )
    if target is not None:
        evidence.update(
            {
                "target_text": target.content.text if target.content else None,
                "target_bbox": target.bbox.model_dump(mode="json"),
                "target_region_type": target.type.value,
            }
        )
        target_atomic_ids = target.metadata.get("atomic_region_ids")
        if isinstance(target_atomic_ids, list) and target_atomic_ids:
            evidence.update(
                {
                    "target_region_ids": target_atomic_ids,
                    "target_logical_region_count": len(target_atomic_ids),
                }
            )
    if match is not None:
        evidence.update(
            {
                "match_score": match.score,
                "match_position_similarity": match.metrics.position_similarity,
                "match_size_similarity": match.metrics.size_similarity,
                "match_type_similarity": match.metrics.type_similarity,
                "match_order_similarity": match.metrics.order_similarity,
            }
        )
    return evidence
