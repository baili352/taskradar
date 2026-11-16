"""材料文件的受控存储。

- 磁盘文件名由 UUID 生成，原始文件名只保存到数据库；
- 所有读写路径都会解析并校验必须位于上传根目录内，防止路径穿越；
- 上传目录不在 FastAPI 静态目录中，文件不会被直接对外暴露。
"""

import re
import uuid
from pathlib import Path

from app.core.config import settings

_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_MAX_NAME_LENGTH = 120


def get_upload_root() -> Path:
    root = Path(settings.material_upload_dir)
    if not root.is_absolute():
        root = settings.base_dir / root
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def sanitize_filename(filename: str) -> str:
    """只保留基名并清理不安全字符，用于展示与数据库记录。"""
    base = Path(filename or "").name.strip()
    cleaned = _UNSAFE_CHARS.sub("_", base).strip(" .")
    if not cleaned:
        cleaned = "material"
    if len(cleaned) > _MAX_NAME_LENGTH:
        stem = Path(cleaned).stem[: _MAX_NAME_LENGTH - 16]
        cleaned = stem + Path(cleaned).suffix
    return cleaned


def _resolve_within_root(relative_path: str) -> Path:
    root = get_upload_root()
    target = (root / relative_path).resolve()
    if target != root and root not in target.parents:
        raise ValueError("文件路径超出受控存储目录")
    return target


def save_material_file(
    matter_id: int, extension: str, content: bytes
) -> str:
    """写入文件并返回相对上传根目录的 POSIX 路径。"""
    root = get_upload_root()
    folder = root / f"matter-{int(matter_id)}"
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{extension.lower()}"
    target = folder / filename
    target.write_bytes(content)

    relative = target.relative_to(root).as_posix()
    # 二次校验，确保写入位置没有越出受控目录。
    _resolve_within_root(relative)
    return relative


def resolve_stored_file(relative_path: str) -> Path | None:
    """返回受控目录内的真实文件路径；不存在或越界时返回 None。"""
    if not relative_path:
        return None
    try:
        target = _resolve_within_root(relative_path)
    except ValueError:
        return None
    return target if target.is_file() else None


def delete_stored_file(relative_path: str | None) -> bool:
    """只删除受控目录内的文件，避免误删其他路径。"""
    target = resolve_stored_file(relative_path or "")
    if target is None:
        return False
    try:
        target.unlink()
    except OSError:
        return False
    return True
