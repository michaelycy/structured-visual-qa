"""多格式归一化服务：把 Office 文档统一转换为 PDF 后复用现有流水线。

Word/PPT/Excel 的版面语义各不相同，为每种格式写原生解析器会产生 N 条
平行链路。本服务用 LibreOffice headless 做统一转换：转换产物是普通
PDF，下游 parse→group→align→match→detect→score 全部零改动。
LibreOffice 渲染与 Office 原生排版存在小比例偏差，由 Profile 的
conversion_noise_ratio 容差吸收（见 T9 方案）。
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

# 支持归一化的源格式（扩展名 → 魔数前缀，魔数可缺省表示仅查扩展名）。
SUPPORTED_FORMATS: dict[str, bytes | None] = {
    ".docx": b"PK",
    ".doc": b"\xd0\xcf",
    ".pptx": b"PK",
    ".ppt": b"\xd0\xcf",
    ".xlsx": b"PK",
    ".xls": b"\xd0\xcf",
    ".odt": b"PK",
    ".odp": b"PK",
}

DEFAULT_TIMEOUT_SECONDS = 60


def matches_magic(extension: str, head: bytes) -> bool:
    """校验文件头部字节与扩展名声明的格式魔数是否一致。

    SUPPORTED_FORMATS 中魔数为 None 的格式只按扩展名放行；有魔数定义
    的格式必须头部匹配，防止任意文件改名后喂给 LibreOffice。
    """

    magic = SUPPORTED_FORMATS.get(extension.lower())
    if magic is None:
        return True
    return head.startswith(magic)


class NormalizationError(Exception):
    """归一化失败（引擎缺失、格式非法或转换超时）。"""


class NormalizationService:
    """封装 LibreOffice 转换的格式探测、执行与产物管理。"""

    def __init__(
        self,
        *,
        artifacts_dir: Path,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """注入产物根目录与单文件转换超时；产物写 normalized/ 子目录。"""

        self._normalized_dir = artifacts_dir / "normalized"
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def supported_extensions() -> list[str]:
        """返回可归一化的扩展名列表，供前端选择器过滤。"""

        return sorted(SUPPORTED_FORMATS)

    @staticmethod
    def is_supported(filename: str) -> bool:
        """扩展名校验：是否属于可归一化的 Office 格式。

        内容魔数校验在 normalize() 读取文件头部时进行（matches_magic），
        因为此方法只有文件名、没有文件内容。
        """

        return Path(filename).suffix.lower() in SUPPORTED_FORMATS

    @staticmethod
    def check_engine() -> str | None:
        """探测 soffice 是否可用；返回版本号或 None。"""

        binary = shutil.which("soffice") or shutil.which("libreoffice")
        if binary is None:
            return None
        try:
            result = subprocess.run(
                [binary, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        return result.stdout.strip() or None

    def normalize(self, source: Path) -> tuple[Path, str]:
        """把 Office 文档转成 PDF，返回 (PDF 路径, 原格式扩展名)。

        转换结果带内容摘要缓存：同一文件重复归一化直接复用产物。
        """

        if not self.is_supported(source.name):
            raise NormalizationError(
                f"不支持归一化的格式: {source.suffix or '(无扩展名)'}"
            )
        if not source.is_file():
            raise NormalizationError(f"文件不存在: {source}")
        # 扩展名 + 魔数双重校验：文件内容必须与声明格式一致。
        extension = source.suffix.lower()
        with source.open("rb") as handle:
            head = handle.read(8)
        if not matches_magic(extension, head):
            raise NormalizationError(f"文件内容与扩展名不符: {source.name}")
        engine_version = self.check_engine()
        if engine_version is None:
            raise NormalizationError(
                "LibreOffice 不可用。请安装 LibreOffice（macOS: "
                "brew install --cask libreoffice；Linux: apt install "
                "libreoffice）并确保 soffice 在 PATH 中。"
            )

        self._normalized_dir.mkdir(parents=True, exist_ok=True)
        # 以内容摘要命名缓存，避免同名不同内容互相覆盖。
        digest = _file_digest(source)
        output_pdf = self._normalized_dir / f"{digest}-normalized.pdf"
        if output_pdf.is_file():
            return output_pdf, source.suffix.lower()

        # soffice 不能指定输出文件名，只能指定输出目录（产物与源同名）。
        # staging 名带随机后缀：并发归一化同一文件时互不干扰
        # （对抗审查 M-6：同名 staging 的 move/rmtree 竞争）。
        staging = self._normalized_dir / f"staging-{digest}-{uuid.uuid4().hex[:6]}"
        staging.mkdir(parents=True, exist_ok=True)
        try:
            # 与 check_engine 相同的二进制解析：部分发行版只有
            # libreoffice 命令（对抗审查 M-3：硬编码 soffice 崩溃）。
            binary = shutil.which("soffice") or shutil.which("libreoffice")
            if binary is None:
                raise NormalizationError(
                    "LibreOffice 不可用。请安装 LibreOffice（macOS: "
                    "brew install --cask libreoffice；Linux: apt install "
                    "libreoffice）并确保 soffice 在 PATH 中。"
                )
            subprocess.run(
                [
                    binary,
                    "--headless",
                    "--norestore",
                    # 隔离用户配置目录：共享默认 profile 在并发/残留锁时
                    # 会触发 DeploymentException 崩溃（macOS 常见）；
                    # UserInstallation 要求绝对路径 URL，相对路径会挂起。
                    f"-env:UserInstallation=file://{self._normalized_dir.resolve() / 'lo-profile'}",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(staging),
                    str(source.resolve()),
                ],
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise NormalizationError(
                f"转换超时（>{self._timeout_seconds}s）: {source.name}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise NormalizationError(
                f"转换失败: {source.name}: {exc.stderr[:200]}"
            ) from exc
        except OSError as exc:
            raise NormalizationError(
                f"转换引擎启动失败: {source.name}: {exc}"
            ) from exc
        # 产物名 = 源完整主名 + .pdf（对抗审查 M-4：双重 stem 会把
        # report.v2.docx 算成 report.pdf 而 soffice 实际产 report.v2.pdf）。
        produced = staging / f"{source.name}.pdf"
        try:
            if not produced.is_file():
                raise NormalizationError(
                    f"转换未产出 PDF: {source.name}（可能是加密或损坏文件）"
                )
            shutil.move(str(produced), output_pdf)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return output_pdf, source.suffix.lower()


def _file_digest(path: Path) -> str:
    """流式计算文件摘要前 16 位，用于转换产物缓存键。"""

    from hashlib import sha256

    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()[:16]
