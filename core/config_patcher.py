"""
config.plist 修补模块
在签名 OC EFI 文件后，自动将 UEFI → Quirks → DisableSecurityPolicy 设为 true。
备份机制与 EFI 文件签名备份一致。
"""
import shutil
import plistlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


class ConfigPatchResult:
    """config.plist 修补结果。"""
    def __init__(self):
        self.found: bool = False          # 是否找到 config.plist
        self.patched: bool = False        # 是否成功修改
        self.already_set: bool = False    # 原本就已是 true
        self.backup_path: Optional[str] = None
        self.config_path: Optional[str] = None
        self.message: str = ""

    @property
    def success(self) -> bool:
        return self.patched or self.already_set


def find_config_plist(oc_dir: str | Path) -> Optional[Path]:
    """在 OC 目录中查找 config.plist。"""
    oc_dir = Path(oc_dir)
    # 常见位置：OC/config.plist 或直接在目录下
    candidates = [
        oc_dir / "config.plist",
        oc_dir / "OC" / "config.plist",
    ]
    for c in candidates:
        if c.exists():
            return c
    # 递归查找
    results = list(oc_dir.rglob("config.plist"))
    if results:
        return results[0]
    return None


def patch_config_plist(
    oc_dir: str | Path,
    backup_dir: Optional[Path] = None,
) -> ConfigPatchResult:
    """
    在 OC 目录中查找 config.plist，
    备份后将 UEFI → Quirks → DisableSecurityPolicy 设为 true。

    Args:
        oc_dir: OC 根目录（包含 OC/ 子目录的路径）
        backup_dir: 备份目录（与 EFI 文件备份共用同一个 _backup_ 时间戳目录）

    Returns:
        ConfigPatchResult
    """
    result = ConfigPatchResult()
    config_path = find_config_plist(oc_dir)

    if config_path is None:
        result.message = "未找到 config.plist，跳过 DisableSecurityPolicy 修补"
        return result

    result.config_path = str(config_path)
    result.found = True

    try:
        # 读取 plist
        with open(config_path, "rb") as f:
            data = plistlib.load(f)
    except Exception as e:
        result.message = f"读取 config.plist 失败：{e}"
        return result

    # 导航到 UEFI → Quirks → DisableSecurityPolicy
    uefi = data.get("UEFI")
    if not isinstance(uefi, dict):
        uefi = {}
        data["UEFI"] = uefi

    quirks = uefi.get("Quirks")
    if not isinstance(quirks, dict):
        quirks = {}
        uefi["Quirks"] = quirks

    # 检查当前值
    current = quirks.get("DisableSecurityPolicy")
    if current is True:
        result.already_set = True
        result.message = "config.plist 中 DisableSecurityPolicy 已为 true，无需修改"
        return result

    # 备份原始 config.plist
    if backup_dir is not None:
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        # 保持相对目录结构
        oc_dir = Path(oc_dir)
        try:
            rel = config_path.relative_to(oc_dir)
        except ValueError:
            rel = Path(config_path.name)
        dest = backup_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(config_path), str(dest))
        result.backup_path = str(dest)

    # 修改
    quirks["DisableSecurityPolicy"] = True

    try:
        with open(config_path, "wb") as f:
            plistlib.dump(data, f)
    except Exception as e:
        result.message = f"写入 config.plist 失败：{e}"
        return result

    result.patched = True
    if result.backup_path:
        result.message = f"已备份并设置 DisableSecurityPolicy=true（备份：{result.backup_path}）"
    else:
        result.message = "已设置 DisableSecurityPolicy=true"
    return result
