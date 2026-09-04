"""
EFI 分区检测与挂载工具
自动检测 Windows EFI 分区和 OpenCore 分区
"""
import subprocess
import sys
import re
import string
from pathlib import Path
from typing import List, Optional, Tuple

# Windows 下隐藏控制台窗口的标志
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _run_ps(cmd: str) -> Tuple[int, str, str]:
    """运行 PowerShell 命令并返回结果。"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, timeout=15,
            creationflags=_CREATE_NO_WINDOW
        )
        # 手动解码，兼容中文 Windows GBK 编码
        out = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
        err = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        return result.returncode, out, err
    except Exception as e:
        return -1, "", str(e)


def is_admin() -> bool:
    """检查当前是否以管理员权限运行。"""
    rc, out, _ = _run_ps(
        "[Security.Principal.WindowsIdentity]::GetCurrent().Name;"
        "$id = [Security.Principal.WindowsIdentity]::GetCurrent();"
        "$prp = New-Object Security.Principal.WindowsPrincipal($id);"
        "$prp.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)"
    )
    if rc == 0:
        lines = out.strip().splitlines()
        if lines and "True" in lines[-1]:
            return True
    return False


def find_efi_partitions() -> List[dict]:
    """
    查找所有 EFI 系统分区。
    返回列表：[{"drive_letter": "S:", "size": 123456789, "label": ""}, ...]
    """
    partitions = []
    
    # 先尝试获取所有已挂载的 EFI 分区
    rc, out, _ = _run_ps(
        "Get-Partition | Where-Object { $_.Type -eq 'System' -or $_.GptType -eq 'c12a7328-f81f-11d2-ba4b-00a0c93ec93b' } | "
        "ForEach-Object { $letter = ($_.DriveLetter); if ($letter) { $letter + ':' + '|' + $_.Size + '|' + ($_.DriveLetter -as [string]) } }"
    )
    
    # 如果上面不行，用 mountvol 枚举
    if rc != 0 or not out.strip():
        rc2, out2, _ = _run_ps("mountvol")
        if rc2 == 0:
            # 解析 mountvol 输出
            lines = out2.splitlines()
            for i, line in enumerate(lines):
                line = line.strip()
                if line.startswith("\\?\Volume"):
                    # 看下一行是否有驱动器号
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        match = re.match(r"([A-Z]):\\", next_line)
                        if match:
                            drive = match.group(1) + ":"
                            # 检查是否是 EFI 分区
                            partitions.append({"drive_letter": drive, "size": 0, "label": ""})
    
    # 从 WMI 获取更详细的信息
    rc3, out3, _ = _run_ps(
        "Get-WmiObject -Class Win32_Volume | Where-Object { $_.DriveType -eq 2 -and $_.DriveLetter } | "
        "ForEach-Object { $_.DriveLetter + '|' + $_.Capacity + '|' + $_.Label }"
    )
    
    vol_info = {}
    if rc3 == 0:
        for line in out3.strip().splitlines():
            parts = line.strip().split("|")
            if len(parts) >= 3:
                vol_info[parts[0].upper()] = {"size": int(parts[1]) if parts[1].isdigit() else 0, "label": parts[2]}
    
    # 用 Get-Partition 获取 EFI 类型分区
    rc4, out4, _ = _run_ps(
        "Get-Partition | Where-Object { $_.GptType -eq 'c12a7328-f81f-11d2-ba4b-00a0c93ec93b' -or $_.Type -eq 'System' } | "
        "ForEach-Object { if ($_.DriveLetter) { $_.DriveLetter + ':' + '|' + $_.Size } }"
    )
    
    efi_drives = set()
    if rc4 == 0:
        for line in out4.strip().splitlines():
            line = line.strip()
            if line and "|" in line:
                parts = line.split("|")
                drive = parts[0].upper()
                efi_drives.add(drive)
                size = int(parts[1]) if parts[1].isdigit() else 0
                info = vol_info.get(drive, {"size": size, "label": ""})
                partitions.append({
                    "drive_letter": drive,
                    "size": info["size"] or size,
                    "label": info["label"]
                })
    
    # 如果没有找到 EFI 分区，检查所有 FAT32 小分区（可能是 EFI 但未标记）
    if not partitions:
        rc5, out5, _ = _run_ps(
            "Get-WmiObject -Class Win32_Volume | Where-Object { $_.DriveType -eq 2 -and $_.DriveLetter -and $_.FileSystem -eq 'FAT32' -and $_.Capacity -lt 1GB } | "
            "ForEach-Object { $_.DriveLetter + '|' + $_.Capacity + '|' + $_.Label }"
        )
        if rc5 == 0:
            for line in out5.strip().splitlines():
                parts = line.strip().split("|")
                if len(parts) >= 3:
                    partitions.append({
                        "drive_letter": parts[0].upper(),
                        "size": int(parts[1]) if parts[1].isdigit() else 0,
                        "label": parts[2]
                    })
    
    # 去重
    seen = set()
    unique = []
    for p in partitions:
        dl = p["drive_letter"].upper()
        if dl not in seen:
            seen.add(dl)
            unique.append(p)
    
    return unique


def detect_windows_efi_path() -> Optional[str]:
    """
    自动检测 Windows EFI 启动目录路径。
    返回类似 "S:\EFI\Microsoft\Boot" 的路径，如果找不到返回 None。
    """
    partitions = find_efi_partitions()
    
    for part in partitions:
        drive = part["drive_letter"]
        boot_path = Path(drive) / "EFI" / "Microsoft" / "Boot"
        if boot_path.exists():
            return str(boot_path)
    
    # 也检查系统分区
    rc, out, _ = _run_ps("$env:SystemDrive")
    if rc == 0 and out.strip():
        sys_drive = out.strip().upper()
        boot_path = Path(sys_drive) / "EFI" / "Microsoft" / "Boot"
        if boot_path.exists():
            return str(boot_path)
    
    return None


def detect_opencore_efi_path() -> Optional[str]:
    """
    自动检测 OpenCore EFI 目录路径。
    返回类似 "S:\EFI\OC" 的路径，如果找不到返回 None。
    """
    partitions = find_efi_partitions()
    
    for part in partitions:
        drive = part["drive_letter"]
        # 检查常见 OC 路径
        oc_paths = [
            Path(drive) / "EFI" / "OC",
            Path(drive) / "OC",
            Path(drive) / "EFI" / "Boot" / "OC",
        ]
        for oc_path in oc_paths:
            if oc_path.exists():
                # 进一步验证：检查 OpenCore.efi
                if (oc_path / "OpenCore.efi").exists():
                    return str(oc_path)
                # 或者有 Drivers、Tools、ACPI 等子目录
                if any((oc_path / d).exists() for d in ["Drivers", "Tools", "ACPI", "Kexts"]):
                    return str(oc_path)
    
    return None


def mount_efi_partition() -> Optional[str]:
    """
    尝试挂载 EFI 系统分区并分配驱动器号。
    需要管理员权限。返回分配的驱动器号，失败返回 None。
    """
    # 找到系统的 EFI 分区
    rc, out, _ = _run_ps(
        "$esp = Get-Partition | Where-Object { $_.GptType -eq 'c12a7328-f81f-11d2-ba4b-00a0c93ec93b' } | Select-Object -First 1;"
        "if ($esp -and -not $esp.DriveLetter) {"
        "  $letter = (Get-PartitionSupportedDriveLetter -DiskNumber $esp.DiskNumber -PartitionNumber $esp.PartitionNumber)[-1];"
        "  Set-Partition -DiskNumber $esp.DiskNumber -PartitionNumber $esp.PartitionNumber -NewDriveLetter $letter;"
        "  $letter + ':'"
        "} else { $esp.DriveLetter + ':' }"
    )
    
    if rc == 0 and out.strip():
        letter = out.strip().upper()
        if re.match(r"^[A-Z]:$", letter):
            return letter
    
    return None


def list_disks() -> List[dict]:
    """
    列出所有物理磁盘。
    返回：[{"number": 0, "size": 1234567890, "model": "...", "gpt": True}, ...]
    """
    rc, out, _ = _run_ps(
        "Get-Disk | ForEach-Object {"
        "  $style = 'Unknown';"
        "  if ($_.PartitionStyle -eq 'GPT') { $style = 'GPT' }"
        "  elseif ($_.PartitionStyle -eq 'MBR') { $style = 'MBR' }"
        "  $_.Number.ToString() + '|' + $_.Size.ToString() + '|' + $_.Model + '|' + $style"
        "}"
    )

    disks = []
    if rc == 0:
        for line in out.strip().splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) >= 4:
                try:
                    disks.append({
                        "number": int(parts[0]),
                        "size": int(parts[1]) if parts[1].isdigit() else 0,
                        "model": parts[2].strip(),
                        "gpt": parts[3].strip().upper() == "GPT"
                    })
                except (ValueError, IndexError):
                    continue
    return disks


def list_partitions(disk_number: int) -> List[dict]:
    """
    列出指定磁盘上的所有分区。
    返回：[{"number": 1, "size": 123456789, "type": "System", "drive_letter": "S:", "gpt_type": "..."}, ...]
    """
    cmd = (
        "Get-Partition -DiskNumber {} | ForEach-Object {{"
        "  $dl = '';"
        "  if ($_.DriveLetter -and $_.DriveLetter -ne '') {{ $dl = ($_.DriveLetter).ToString() + ':' }};"
        "  $gt = '';"
        "  if ($_.GptType) {{ $gt = $_.GptType }};"
        "  $tp = 'Unknown';"
        "  if ($_.Type) {{ $tp = $_.Type }};"
        "  $_.PartitionNumber.ToString() + '|' + $_.Size.ToString() + '|' + $tp + '|' + $dl + '|' + $gt"
        "}}".format(disk_number)
    )

    rc, out, _ = _run_ps(cmd)

    partitions = []
    if rc == 0:
        for line in out.strip().splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) >= 3:
                try:
                    partitions.append({
                        "number": int(parts[0]),
                        "size": int(parts[1]) if parts[1].isdigit() else 0,
                        "type": parts[2],
                        "drive_letter": parts[3] if len(parts) > 3 and parts[3] else "",
                        "gpt_type": parts[4] if len(parts) > 4 else ""
                    })
                except (ValueError, IndexError):
                    continue
    return partitions


def mount_partition(disk_number: int, partition_number: int, drive_letter: str = "") -> Tuple[bool, str]:
    """
    手动挂载指定分区并分配驱动器号。
    
    Args:
        disk_number: 磁盘号
        partition_number: 分区号
        drive_letter: 驱动器号（如 "S"），为空则自动分配
    
    Returns:
        (成功, 驱动器号或错误信息)
    """
    # 先检查是否已有驱动器号
    check_cmd = (
        f"$p = Get-Partition -DiskNumber {disk_number} -PartitionNumber {partition_number} -ErrorAction SilentlyContinue;"
        "if ($p -and $p.DriveLetter -and $p.DriveLetter -ne [char]0) { $p.DriveLetter.ToString() + ':' }"
    )
    rc, out, _ = _run_ps(check_cmd)
    if rc == 0 and out.strip():
        existing = out.strip().upper()
        if re.match(r"^[A-Z]:$", existing):
            return True, existing

    # 需要分配驱动器号
    if drive_letter:
        letter = drive_letter.upper().replace(":", "")
    else:
        # 自动获取可用驱动器号
        rc2, out2, _ = _run_ps(
            f"(Get-PartitionSupportedDriveLetter -DiskNumber {disk_number} "
            f"-PartitionNumber {partition_number})[-1].ToString()"
        )
        if rc2 == 0 and out2.strip():
            letter = out2.strip()
        else:
            # 回退：找一个未使用的盘符
            used = set()
            import string as str_mod
            for c in str_mod.ascii_uppercase:
                from pathlib import Path as P
                if P(f"{c}:").exists():
                    used.add(c)
            for c in reversed(str_mod.ascii_uppercase):
                if c not in used and c not in ("C", "A", "B"):
                    letter = c
                    break
            else:
                return False, "无法找到可用的驱动器号"

    # 使用 Add-PartitionAccessPath 挂载分区
    cmd = (
        f"Add-PartitionAccessPath -DiskNumber {disk_number} -PartitionNumber {partition_number} "
        f"-AccessPath '{letter}:\\' -ErrorAction Stop; '{letter}:'"
    )

    rc, out, err = _run_ps(cmd)
    if rc == 0 and out.strip():
        result = out.strip().upper()
        if re.match(r"^[A-Z]:$", result):
            return True, result

    return False, (err or out or "挂载失败").strip()


def unmount_partition(drive_letter: str) -> Tuple[bool, str]:
    """
    卸载指定驱动器号对应的分区挂载。

    Args:
        drive_letter: 驱动器号（如 "Z:"）

    Returns:
        (成功, 消息)
    """
    letter = drive_letter.upper().replace("\\", "").replace("/", "")
    if not re.match(r"^[A-Z]:$", letter):
        return False, f"无效的驱动器号：{drive_letter}"

    # 使用 Remove-PartitionAccessPath 卸载
    # AccessPath 需要格式 "Z:\" — Python 字符串中 \\ 产生一个反斜杠
    cmd = (
        f"$p = Get-Partition -DriveLetter {letter[0]} -ErrorAction SilentlyContinue;"
        "if ($p) { "
        f"  Remove-PartitionAccessPath -InputObject $p -AccessPath '{letter}\\' -ErrorAction Stop;"
        "  'OK'"
        "} else { 'NOT_FOUND' }"
    )
    rc, out, err = _run_ps(cmd)
    if rc == 0:
        result = out.strip().upper()
        if "OK" in result:
            return True, f"分区 {letter} 已卸载"
        if "NOT_FOUND" in result:
            return True, f"分区 {letter} 未挂载或已卸载"

    return False, (err or out or "卸载失败").strip()


def assign_drive_letter(disk_number: int, partition_number: int, letter: str = "") -> Optional[str]:
    """为分区分配驱动器号（如果已有则返回现有）。"""
    # 先检查是否已有驱动器号
    parts = list_partitions(disk_number)
    for p in parts:
        if p["number"] == partition_number and p["drive_letter"]:
            return p["drive_letter"]
    
    ok, result = mount_partition(disk_number, partition_number, letter)
    if ok:
        return result
    return None


def get_oc_directory_from_partition(drive_letter: str) -> Optional[str]:
    """从给定的 EFI 分区查找 OC 目录。"""
    oc_paths = [
        Path(drive_letter) / "EFI" / "OC",
        Path(drive_letter) / "OC",
    ]
    for p in oc_paths:
        if p.exists():
            return str(p)
    return None


def get_windows_boot_from_partition(drive_letter: str) -> Optional[str]:
    """从给定的 EFI 分区查找 Windows 启动目录。"""
    boot_path = Path(drive_letter) / "EFI" / "Microsoft" / "Boot"
    if boot_path.exists():
        return str(boot_path)
    return None


def format_size(size_bytes: int) -> str:
    """格式化字节大小为可读字符串。"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
