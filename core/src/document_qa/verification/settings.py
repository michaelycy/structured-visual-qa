"""渲染验证层配置（T38）。

阶段 2 起配置迁入 `RuleProfile.verification`（VerificationSettings），
随 Profile 快照进报告、可复现（契约 §12）。本模块保留类型引用，
历史引擎级常量已删除——配置单一事实来源是 profiles.py。
"""

from document_qa.profiles import VerificationSettings

__all__ = ["VerificationSettings"]
