"""
WSL utility module.
Handles all interactions with WSL for signing, certificate generation, etc.
"""
import subprocess
import shlex
import sys
from pathlib import Path
from typing import Tuple, Optional

# Windows 下隐藏控制台窗口的标志
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def win_to_wsl_path(win_path: str | Path) -> str:
    """Convert a Windows path to WSL path."""
    p = str(win_path).replace("\\", "/")
    # Replace drive letter: C: -> /mnt/c
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        rest = p[2:]
        # 确保驱动器号后面有 /
        if not rest.startswith("/"):
            rest = "/" + rest
        p = f"/mnt/{drive}{rest}"
    return p


def wsl_to_win_path(wsl_path: str) -> str:
    """Convert a WSL path to Windows path."""
    p = wsl_path
    if p.startswith("/mnt/") and len(p) > 5:
        drive = p[5].upper()
        p = f"{drive}:{p[6:]}"
    return p.replace("/", "\\")


def run_wsl(cmd: str, timeout: int = 120) -> Tuple[int, str, str]:
    """Run a command in WSL.

    Args:
        cmd: Shell command to run (will be passed to bash -c)
        timeout: Timeout in seconds

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    try:
        result = subprocess.run(
            ["wsl", "--", "bash", "-c", cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except FileNotFoundError:
        return -1, "", "WSL not found"


def check_wsl_available() -> bool:
    """Check if WSL is available, starting the service if needed.

    After a reboot, the WSL service (LxssManager) may not be running.
    This function tries to start it before giving up.
    """
    import shutil
    import time as _time

    # 1. 快速检查 wsl.exe 是否存在
    if not shutil.which("wsl"):
        return False

    # 2. 尝试直接运行 WSL 命令
    rc, out, _ = run_wsl("echo WSL_OK", timeout=10)
    if rc == 0 and "WSL_OK" in out:
        return True

    # 3. 首次失败 — 可能是 WSL 服务未启动，尝试触发启动
    #    运行 wsl --list 会触发 LxssManager 服务启动
    try:
        subprocess.run(
            ["wsl", "--list", "--quiet"],
            capture_output=True, text=True, timeout=20,
            creationflags=CREATE_NO_WINDOW
        )
    except Exception:
        pass

    # 4. 等待服务启动
    _time.sleep(3)

    # 5. 重试
    rc, out, _ = run_wsl("echo WSL_OK", timeout=15)
    return rc == 0 and "WSL_OK" in out


def check_sbsigntool() -> bool:
    """Check if sbsigntool is installed in WSL."""
    rc, out, _ = run_wsl("which sbsign && which sbverify && which cert-to-efi-sig-list && which sign-efi-sig-list", timeout=10)
    return rc == 0 and "sbsign" in out and "sbverify" in out and "cert-to-efi-sig-list" in out and "sign-efi-sig-list" in out


def check_openssl() -> bool:
    """Check if openssl is available in WSL."""
    rc, out, _ = run_wsl("which openssl", timeout=10)
    return rc == 0 and "openssl" in out


def install_dependencies() -> Tuple[bool, str]:
    """Install required tools in WSL.

    Uses `wsl -u root` to avoid sudo password prompts.

    Returns:
        Tuple of (success, output)
    """
    cmd = "apt-get update && apt-get install -y sbsigntool efitools openssl uuid-runtime"
    try:
        result = subprocess.run(
            ["wsl", "-u", "root", "--", "bash", "-c", cmd],
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except FileNotFoundError:
        return False, "WSL not found"
