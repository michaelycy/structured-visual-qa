"""应用服务层：编排用例，桥接 API 层与核心引擎。

服务层职责：任务级互斥、产物目录管理、跨组件组装。它返回核心模型或
纯数据结构，不了解 HTTP 的存在；核心引擎（pipeline/matching/detectors）
也不知道服务层的存在。分层方向：api → services → 核心引擎。
"""

from document_qa.services.compare_service import CompareService
from document_qa.services.file_service import FileService
from document_qa.services.profile_service import ProfileService
from document_qa.services.verify_service import VerifyService, VerifyStageResult

__all__ = [
    "CompareService",
    "FileService",
    "ProfileService",
    "VerifyService",
    "VerifyStageResult",
]
