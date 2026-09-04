"""
EFI file signing module.
Signs EFI files using sbsigntool via WSL.
Supports automatic backup of original files.
"""
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Callable, Optional, Tuple
from . import config
from .wsl_utils import run_wsl, win_to_wsl_path
from .config_patcher import patch_config_plist, ConfigPatchResult


class SignResult:
    """Result of a signing operation."""
    def __init__(self):
        self.total = 0
        self.signed = 0
        self.failed = 0
        self.backup_dir: Optional[str] = None
        self.files: List[Tuple[str, bool, str]] = []  # (path, success, message)
        self.config_patch: Optional[ConfigPatchResult] = None

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.signed > 0


class EfiSigner:
    """Signs EFI files using ISK key."""

    def __init__(self):
        self.isk_key = config.get_key_path("ISK", "key")
        self.isk_pem = config.get_key_path("ISK", "pem")

    def can_sign(self) -> bool:
        """Check if signing is possible (keys exist)."""
        return self.isk_key.exists() and self.isk_pem.exists()

    def find_efi_files(self, directory: str | Path) -> List[Path]:
        """Find all .efi files in a directory recursively.

        Args:
            directory: Root directory to search

        Returns:
            List of .efi file paths
        """
        directory = Path(directory)
        if not directory.exists():
            return []
        return sorted(directory.rglob("*.efi"))

    def _backup_files(self, files: List[Path], source_dir: Path) -> Path:
        """
        备份原始 EFI 文件到 _backup_YYYYMMDD_HHMMSS 目录。
        保持相对目录结构。
        
        Returns:
            备份目录路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = source_dir.parent / f"_backup_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        for f in files:
            rel_path = f.relative_to(source_dir)
            dest = backup_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(f), str(dest))
        
        return backup_dir

    def sign_directory(
        self,
        directory: str | Path,
        backup: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> SignResult:
        """Sign all .efi files in a directory.

        Args:
            directory: Directory containing EFI files
            backup: Whether to backup original files before signing
            progress_callback: Optional callback (msg, current, total)

        Returns:
            SignResult with details
        """
        result = SignResult()
        directory = Path(directory)
        files = self.find_efi_files(directory)
        result.total = len(files)

        if result.total == 0:
            return result

        # 先备份原始文件
        if backup:
            if progress_callback:
                progress_callback(f"正在备份 {result.total} 个原始文件...", 0, result.total)
            try:
                backup_dir = self._backup_files(files, directory)
                result.backup_dir = str(backup_dir)
                if progress_callback:
                    progress_callback(f"已备份到：{backup_dir}", 0, result.total)
            except Exception as e:
                if progress_callback:
                    progress_callback(f"备份失败：{e}", 0, result.total)
                # 备份失败不阻止签名，但记录警告

        isk_key_wsl = win_to_wsl_path(str(self.isk_key))
        isk_pem_wsl = win_to_wsl_path(str(self.isk_pem))

        for i, efi_path in enumerate(files, 1):
            rel_path = str(efi_path.relative_to(directory))
            efi_wsl = win_to_wsl_path(str(efi_path))

            if progress_callback:
                progress_callback(f"签名中：{rel_path}", i, result.total)

            # Sign the file
            sign_cmd = f'sbsign --key "{isk_key_wsl}" --cert "{isk_pem_wsl}" --output "{efi_wsl}" "{efi_wsl}" 2>&1'
            rc, out, err = run_wsl(sign_cmd, timeout=30)

            if rc != 0:
                result.failed += 1
                result.files.append((rel_path, False, out + err))
                continue

            # Verify the signature
            verify_cmd = f'sbverify --cert "{isk_pem_wsl}" "{efi_wsl}" 2>&1'
            rc, out, err = run_wsl(verify_cmd, timeout=30)

            if rc == 0 and "Signature verification OK" in (out + err):
                result.signed += 1
                result.files.append((rel_path, True, "OK"))
            else:
                result.failed += 1
                result.files.append((rel_path, False, f"验证失败：{out}{err}"))

        # 签名完成后自动修补 config.plist
        if result.failed == 0 and result.signed > 0:
            if progress_callback:
                progress_callback("正在检查 config.plist ...", result.total, result.total)
            try:
                patch_result = patch_config_plist(
                    directory,
                    backup_dir=Path(result.backup_dir) if result.backup_dir else None,
                )
                result.config_patch = patch_result
                if progress_callback:
                    progress_callback(patch_result.message, result.total, result.total)
            except Exception as e:
                if progress_callback:
                    progress_callback(f"config.plist 修补异常：{e}", result.total, result.total)

        if progress_callback:
            status = f"完成：{result.signed} 成功，{result.failed} 失败"
            progress_callback(status, result.total, result.total)

        return result

    def sign_file(self, efi_file: str | Path, backup: bool = True) -> Tuple[bool, str]:
        """Sign a single EFI file.

        Args:
            efi_file: Path to EFI file
            backup: Whether to backup original file before signing

        Returns:
            Tuple of (success, message)
        """
        efi_file = Path(efi_file)
        if not efi_file.exists():
            return False, "文件不存在"

        # 备份
        if backup:
            backup_path = efi_file.parent / f"{efi_file.stem}.bak{efi_file.suffix}"
            try:
                shutil.copy2(str(efi_file), str(backup_path))
            except Exception as e:
                return False, f"备份失败：{e}"

        isk_key_wsl = win_to_wsl_path(str(self.isk_key))
        isk_pem_wsl = win_to_wsl_path(str(self.isk_pem))
        efi_wsl = win_to_wsl_path(str(efi_file))

        sign_cmd = f'sbsign --key "{isk_key_wsl}" --cert "{isk_pem_wsl}" --output "{efi_wsl}" "{efi_wsl}" 2>&1'
        rc, out, err = run_wsl(sign_cmd, timeout=30)

        if rc != 0:
            return False, out + err

        verify_cmd = f'sbverify --cert "{isk_pem_wsl}" "{efi_wsl}" 2>&1'
        rc, out, err = run_wsl(verify_cmd, timeout=30)

        if rc == 0 and "Signature verification OK" in (out + err):
            return True, "签名验证通过"
        else:
            return False, f"验证失败：{out}{err}"
