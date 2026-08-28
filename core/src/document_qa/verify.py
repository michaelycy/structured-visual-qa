"""分阶段验证运行器：逐步执行流水线并输出各阶段可审查的中间产物。

开发后的验证不依赖测试代码，而是选取真实 PDF 对逐阶段执行 QA 流水线；
每个阶段产出一份数据制品和一个人类可读摘要，便于在阶段之间交互确认。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from document_qa.pipeline import DocumentQAPipeline


class Stage(StrEnum):
    """验证流程的六个阶段，与流水线六段一一对应。"""

    PARSE = "parse"
    GROUP = "group"
    ALIGNMENT = "alignment"
    MATCH = "match"
    DETECT = "detect"
    REPORT = "report"

    @classmethod
    def ordered(cls) -> list["Stage"]:
        """返回按执行顺序排列的全部阶段。"""

        return [cls.PARSE, cls.GROUP, cls.ALIGNMENT, cls.MATCH, cls.DETECT, cls.REPORT]

    def includes(self, other: "Stage") -> bool:
        """判断本阶段是否晚于或等于另一阶段（即已覆盖其执行范围）。"""

        return self.ordered().index(self) >= self.ordered().index(other)


@dataclass
class StageArtifact:
    """一个阶段的执行结果：结构化制品与终端摘要。"""

    stage: Stage
    data: dict[str, Any]
    summary: str


class StagedVerifier:
    """驱动 DocumentQAPipeline 逐阶段执行并生成审查产物。"""

    def __init__(self, pipeline: DocumentQAPipeline | None = None) -> None:
        """允许注入自定义流水线；缺省使用内置 Profile。"""

        self.pipeline = pipeline or DocumentQAPipeline()
        self._documents: dict[str, Any] = {}

    def run(
        self,
        source_path: Path,
        target_path: Path,
        stop_after: Stage = Stage.REPORT,
    ) -> list[StageArtifact]:
        """执行到指定阶段为止，返回从 parse 开始的全部阶段产物。"""

        artifacts: list[StageArtifact] = []
        for stage in Stage.ordered():
            if not stop_after.includes(stage):
                break
            artifacts.append(self._run_stage(stage, source_path, target_path))
        return artifacts

    def _run_stage(
        self, stage: Stage, source_path: Path, target_path: Path
    ) -> StageArtifact:
        """执行单个阶段；前置阶段的结果缓存在实例中避免重复解析。"""

        if stage == Stage.PARSE:
            source = self.pipeline.parser.parse(source_path)
            target = self.pipeline.parser.parse(target_path)
            self._documents = {"source": source, "target": target}
            data = {
                "source": self._document_overview(source),
                "target": self._document_overview(target),
            }
            summary = (
                f"[parse] 源文档 {len(source.pages)} 页 / "
                f"{sum(len(p.blocks) for p in source.pages)} 个 Block；"
                f"目标文档 {len(target.pages)} 页 / "
                f"{sum(len(p.blocks) for p in target.pages)} 个 Block"
            )
        elif stage == Stage.GROUP:
            grouped = {
                key: self.pipeline._group_document(document)
                for key, document in self._documents.items()
            }
            self._documents = grouped
            data = {
                key: {
                    "pages": len(document.pages),
                    "regions": sum(len(page.regions) for page in document.pages),
                    "region_types": self._region_type_counts(document),
                }
                for key, document in grouped.items()
            }
            summary = (
                f"[group] 源 {data['source']['regions']} 个 Region / "
                f"目标 {data['target']['regions']} 个 Region"
            )
        elif stage == Stage.ALIGNMENT:
            alignment = self.pipeline.page_aligner.align(
                self._documents["source"], self._documents["target"]
            )
            self._documents["alignment"] = alignment
            data = {
                "pairs": alignment.pairs,
                "missing_source_pages": alignment.missing_source_pages,
                "extra_target_pages": alignment.extra_target_pages,
            }
            summary = (
                f"[alignment] {len(alignment.pairs)} 对页面配对，"
                f"源缺失 {len(alignment.missing_source_pages)} 页，"
                f"目标新增 {len(alignment.extra_target_pages)} 页"
            )
        elif stage == Stage.MATCH:
            source_pages = {
                page.page: page for page in self._documents["source"].pages
            }
            target_pages = {
                page.page: page for page in self._documents["target"].pages
            }
            for source_number, target_number in self._documents["alignment"].pairs:
                source_page, target_page = (
                    self.pipeline.logical_region_composer.compose_pair(
                        source_pages[source_number], target_pages[target_number]
                    )
                )
                source_pages[source_number] = source_page
                target_pages[target_number] = target_page
            self._documents["source"] = self._documents["source"].model_copy(
                update={"pages": list(source_pages.values())}
            )
            self._documents["target"] = self._documents["target"].model_copy(
                update={"pages": list(target_pages.values())}
            )
            results = []
            for source_number, target_number in self._documents["alignment"].pairs:
                source_page = next(
                    p for p in self._documents["source"].pages
                    if p.page == source_number
                )
                target_page = next(
                    p for p in self._documents["target"].pages
                    if p.page == target_number
                )
                result = self.pipeline.matcher.match_page(source_page, target_page)
                results.append(
                    {
                        "source_page": source_number,
                        "target_page": target_number,
                        "matched": len(result.matches),
                        "unmatched_source": result.unmatched_source_region_ids,
                        "unmatched_target": result.unmatched_target_region_ids,
                        "mean_score": (
                            sum(m.score for m in result.matches) / len(result.matches)
                            if result.matches
                            else None
                        ),
                    }
                )
            self._documents["match_results"] = results
            total = sum(item["matched"] for item in results)
            summary = f"[match] 共匹配 {total} 对 Region"
            data = {"pages": results}
        elif stage == Stage.DETECT:
            source_doc = self._documents["source"]
            target_doc = self._documents["target"]
            alignment = self._documents["alignment"]
            source_pages = {page.page: page for page in source_doc.pages}
            target_pages = {page.page: page for page in target_doc.pages}
            # 与 DocumentQAPipeline.compare 相同的页面条目构造（配对页 + 源缺失页
            # + 目标新增页），复用 _compare_page 保证缺页/多页与术语检测等
            # 全部路径与真实流水线一致，避免两套检测逻辑漂移。
            entries = [
                (
                    source_number,
                    source_pages[source_number],
                    target_pages[target_number],
                )
                for source_number, target_number in alignment.pairs
            ]
            for number in alignment.missing_source_pages:
                entries.append((number, source_pages[number], None))
            for number in alignment.extra_target_pages:
                entries.append((number, None, target_pages[number]))
            entries.sort(key=lambda entry: entry[0])
            page_results = [
                self.pipeline._compare_page(number, source_page, target_page)
                for number, source_page, target_page in entries
            ]
            issues = [
                issue for page_result in page_results for issue in page_result.issues
            ]
            self._documents["issues"] = issues
            data = {
                "total": len(issues),
                "by_type": self._issue_type_counts(issues),
            }
            summary = f"[detect] 共产生 {len(issues)} 个 Issue"
        else:  # REPORT
            report = self.pipeline.compare(source_path, target_path)
            data = json.loads(report.model_dump_json())
            summary = (
                f"[report] 状态={report.status.value} "
                f"分数={report.document_score:.2f} "
                f"页数={report.summary.pages}"
            )
        return StageArtifact(stage=stage, data=data, summary=summary)

    @staticmethod
    def _document_overview(document: Any) -> dict[str, Any]:
        """文档级解析摘要：页数、Block 数量与类型分布。"""

        return {
            "document_id": document.document_id[:12],
            "pages": len(document.pages),
            "blocks": sum(len(page.blocks) for page in document.pages),
            "page_sizes": [
                {"page": page.page, "width": page.width, "height": page.height}
                for page in document.pages[:3]
            ],
        }

    @staticmethod
    def _region_type_counts(document: Any) -> dict[str, int]:
        """统计文档内各类型 Region 数量。"""

        counts: dict[str, int] = {}
        for page in document.pages:
            for region in page.regions:
                counts[region.type.value] = counts.get(region.type.value, 0) + 1
        return counts

    @staticmethod
    def _issue_type_counts(issues: list[Any]) -> dict[str, int]:
        """统计各类型 Issue 数量。"""

        counts: dict[str, int] = {}
        for issue in issues:
            counts[issue.type.value] = counts.get(issue.type.value, 0) + 1
        return counts


def save_artifacts(artifacts: list[StageArtifact], output_dir: Path) -> list[Path]:
    """把每个阶段产物写入独立 JSON，返回文件路径列表。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for artifact in artifacts:
        path = output_dir / f"stage-{artifact.stage.value}.json"
        path.write_text(
            json.dumps(artifact.data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        paths.append(path)
    return paths
