"""比较任务的隔离执行核心与子进程入口（T23 进程隔离）。

CompareService 的同步路径（DQA_ASYNC_MODE=false / MCP）与异步任务的
子进程路径共用本模块的 execute_compare，保证两条路径的执行逻辑不漂移；
异步任务通过 run_compare 在 spawn 子进程中运行，PaddleOCR 的 CPU 推理
不再挤占 API 进程的 GIL 与计算核，接口延迟与比较耗时互不影响。

本模块顶层禁止导入重依赖（numpy/pymupdf/paddle 链路）：spawn 会重新
import 本模块，BLAS/推理线程数上限必须先于这些导入写入环境变量，
因此核心引擎只在函数体内导入。
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from document_qa_server.services.normalization_service import NormalizationService

if TYPE_CHECKING:
    from document_qa.glossary import Glossary
    from document_qa.ocr import OCRProvider
    from document_qa.profiles import RuleProfile
    from document_qa.schemas import QAReport

# 线程数上限需要覆盖的 BLAS/推理运行时环境变量。
_THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


def apply_thread_limit(worker_threads: int) -> None:
    """把线程数上限写入环境变量；必须在导入 numpy/paddle 之前调用。

    setdefault 语义：部署侧已显式配置的变量（如容器 CPU 配额）保持
    优先；0 或负数表示不限制，行为与引入隔离前一致。
    """

    if worker_threads <= 0:
        return
    for name in _THREAD_ENV_VARS:
        os.environ.setdefault(name, str(worker_threads))


def execute_compare(
    *,
    artifacts_dir: Path,
    source: Path,
    target: Path,
    profile: "RuleProfile",
    glossary: "Glossary | None",
    ocr_provider: "OCRProvider | None",
    render: bool = True,
    render_scope: str = "issues",
    source_password: str | None = None,
    target_password: str | None = None,
) -> tuple["QAReport", dict[str, list[str]]]:
    """执行一次完整比较：归一化、流水线、渲染索引与报告元数据补记。

    从 CompareService.run 抽取为模块级函数：比较子进程只导入本模块，
    不能反向依赖 compare_service（避免 import 环，也不把任务注册表带进
    子进程）。非 PDF 输入先经 LibreOffice 归一化；归一化发生时给偏移类
    阈值叠加转换噪声容差（Profile 副本上改，不污染用户配置，core 保持
    无来源感知）。密码只参与本次解析与渲染，不写入任何产物。
    """

    from document_qa.pipeline import DocumentQAPipeline

    normalizer = NormalizationService(artifacts_dir=artifacts_dir)
    source_pdf, source_origin = _ensure_pdf(normalizer, source)
    target_pdf, target_origin = _ensure_pdf(normalizer, target)

    effective_profile = profile
    if source_origin or target_origin:
        noise = profile.detectors.thresholds.conversion_noise_ratio
        thresholds = profile.detectors.thresholds.model_copy(
            update={
                "shifted_ratio": min(
                    1.0, profile.detectors.thresholds.shifted_ratio + noise
                ),
                "severely_shifted_ratio": min(
                    1.0,
                    profile.detectors.thresholds.severely_shifted_ratio + noise,
                ),
            }
        )
        effective_profile = profile.model_copy(
            update={
                "detectors": profile.detectors.model_copy(
                    update={"thresholds": thresholds}
                )
            }
        )

    # 渲染产物按任务隔离：每任务独立子目录，避免并发结果互相覆盖，
    # 索引天然是本次比较的快照，无跨任务串染。
    render_dir = (
        artifacts_dir / "pages" / f"task-{uuid.uuid4().hex[:10]}"
        if render
        else None
    )
    report = DocumentQAPipeline(
        profile=effective_profile,
        glossary=glossary,
        ocr_provider=ocr_provider,
    ).compare(
        source_pdf,
        target_pdf,
        render_dir=render_dir,
        render_scope=render_scope,  # type: ignore[arg-type]
        source_password=source_password,
        target_password=target_password,
    )
    rendered = (
        _index_rendered(render_dir) if render else {"source": [], "target": []}
    )

    # 在流水线产物之上补记归一化来源（验收提示含转换因素）与本次实际
    # 术语版本引用，持久化层据此建立不可变外键。
    origins = {"source": source_origin, "target": target_origin}
    metadata = dict(report.metadata)
    if any(origins.values()):
        metadata["normalized_from"] = origins
    if glossary is not None:
        metadata["glossary_reference"] = glossary.reference
    if metadata != report.metadata:
        report = report.model_copy(update={"metadata": metadata})
    return report, rendered


def run_compare(payload: dict, sender: Any) -> None:
    """子进程入口：执行一次比较并通过管道回传结果或错误。

    任何异常都转换为 {"error": ...} 回传，保证父进程 recv 一定能收到
    结束信号，不会无限等待。OCR 适配器按子进程内的 DQA_ 环境变量重建
    （Provider 持有延迟初始化锁，不可跨进程 pickle）；密码经 spawn
    管道内存传递，不写入磁盘与任何产物。
    """

    try:
        apply_thread_limit(int(payload.get("worker_threads") or 0))
        # 线程上限生效之后再导入核心引擎与可选推理依赖。
        from document_qa.glossary import Glossary
        from document_qa.profiles import RuleProfile

        from document_qa_server.adapters.ocr import build_ocr_provider
        from document_qa_server.settings import load_settings

        profile = RuleProfile.model_validate_json(payload["profile_json"])
        glossary_json = payload.get("glossary_json")
        glossary = (
            Glossary.model_validate_json(glossary_json)
            if glossary_json
            else None
        )
        artifacts_dir = Path(payload["artifacts_dir"])
        settings = load_settings()
        report, rendered = execute_compare(
            artifacts_dir=artifacts_dir,
            source=Path(payload["source"]),
            target=Path(payload["target"]),
            profile=profile,
            glossary=glossary,
            ocr_provider=build_ocr_provider(settings, artifacts_dir=artifacts_dir),
            render=bool(payload.get("render", True)),
            render_scope=str(payload.get("render_scope", "issues")),
            source_password=payload.get("source_password"),
            target_password=payload.get("target_password"),
        )
        sender.send(
            {"report": report.model_dump(mode="json"), "rendered": rendered}
        )
    except BaseException as exc:  # 子进程内任何失败都回传，绝不让管道悬空
        sender.send({"error": f"{type(exc).__name__}: {exc}"[:500]})
    finally:
        sender.close()


def _ensure_pdf(
    normalizer: NormalizationService, path: Path
) -> tuple[Path, str | None]:
    """PDF 直接返回；Office 格式归一化为 PDF 并返回原格式标记。"""

    if path.suffix.lower() == ".pdf":
        return path, None
    normalized, origin = normalizer.normalize(path)
    return normalized, origin


def _index_rendered(task_dir: Path) -> dict[str, list[str]]:
    """列出该任务两侧已渲染页面的文件名，供前端拼接图片 URL。"""

    prefix = task_dir.name
    index: dict[str, list[str]] = {}
    for side in ("source", "target"):
        side_dir = task_dir / side
        index[side] = (
            sorted(
                f"{prefix}/{side}/{path.name}"
                for path in side_dir.glob("page-*.png")
            )
            if side_dir.is_dir()
            else []
        )
    return index
