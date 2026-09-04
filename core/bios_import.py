"""
BIOS import module.
Imports Secure Boot certificates into BIOS using PowerShell's Set-SecureBootUEFI.
"""
import subprocess
import sys
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime
from . import config

# Windows 下隐藏控制台窗口的标志
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class BIOSStatus:
    """Represents current BIOS Secure Boot status."""
    def __init__(self):
        self.secure_boot_enabled = False
        self.pk_size = 0
        self.kek_size = 0
        self.db_size = 0
        self.setup_mode = True  # True if PK is empty

    @property
    def user_mode(self) -> bool:
        return not self.setup_mode and self.pk_size > 0


class BIOSImporter:
    """Imports certificates into BIOS Secure Boot variables."""

    # Fixed timestamp for signing (required by Set-SecureBootUEFI)
    _TIME = datetime(2024, 1, 1, 0, 0, 0)

    def __init__(self):
        self.certs_dir = config.CERTS_DIR

    def get_status(self) -> BIOSStatus:
        """Get current BIOS Secure Boot status.

        Returns:
            BIOSStatus object
        """
        status = BIOSStatus()

        try:
            # Check Secure Boot enabled
            result = subprocess.run(
                ["powershell", "-Command", "Confirm-SecureBootUEFI"],
                capture_output=True, timeout=10,
                creationflags=_CREATE_NO_WINDOW
            )
            stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
            status.secure_boot_enabled = "True" in stdout
        except Exception:
            status.secure_boot_enabled = False

        # Check each variable
        for var, attr in [("PK", "pk_size"), ("KEK", "kek_size"), ("db", "db_size")]:
            try:
                cmd = f"(Get-SecureBootUEFI -Name {var}).Bytes.Length"
                result = subprocess.run(
                    ["powershell", "-Command", cmd],
                    capture_output=True, timeout=10,
                    creationflags=_CREATE_NO_WINDOW
                )
                stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
                size_str = stdout.strip()
                if size_str.isdigit():
                    setattr(status, attr, int(size_str))
            except Exception:
                pass

        status.setup_mode = (status.pk_size == 0)
        return status

    def import_certificates(
        self,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> tuple[bool, str]:
        """Import all certificates to BIOS.

        Automatically detects Setup Mode vs User Mode:
        - Setup Mode: imports db -> KEK -> PK (full import)
        - User Mode: updates db and KEK only (PK cannot be changed)

        Returns:
            Tuple of (success, message)
        """
        def log(msg):
            if progress_callback:
                progress_callback(msg)

        # Check files
        required_files = {
            "db": (config.get_cert_path("db", "esl"), config.get_cert_path("db", "p7")),
            "KEK": (config.get_cert_path("KEK", "esl"), config.get_cert_path("KEK", "p7")),
            "PK": (config.get_cert_path("PK", "esl"), config.get_cert_path("PK", "p7")),
        }

        for name, (esl, p7) in required_files.items():
            if not esl.exists():
                return False, f"Missing {name}.esl"
            if not p7.exists():
                return False, f"Missing {name}.p7"

        status = self.get_status()

        if status.setup_mode:
            log("Setup Mode detected. Importing: db -> KEK -> PK")

            # Import db
            ok, msg = self._import_single("db", log)
            if not ok:
                return False, f"db import failed: {msg}"

            # Import KEK
            ok, msg = self._import_single("KEK", log)
            if not ok:
                return False, f"KEK import failed: {msg}"

            # Import PK (locks Secure Boot)
            ok, msg = self._import_single("PK", log)
            if not ok:
                return False, f"PK import failed: {msg}"

            log("✓ All certificates imported. Secure Boot is now active!")
            return True, "All certificates imported successfully"

        else:
            log("User Mode detected. Updating db and KEK only (PK cannot be changed)")

            # Update db
            ok, msg = self._import_single("db", log)
            if not ok:
                return False, f"db update failed: {msg}"

            # Update KEK
            ok, msg = self._import_single("KEK", log)
            if not ok:
                return False, f"KEK update failed: {msg}"

            log("✓ db and KEK updated successfully")
            log("Note: To replace PK, reset to Setup Mode in BIOS first")
            return True, "db and KEK updated successfully"

    def _import_single(self, name: str, log_fn: Callable) -> tuple[bool, str]:
        """Import a single certificate variable.

        Args:
            name: Variable name (db, KEK, PK)
            log_fn: Logging callback

        Returns:
            Tuple of (success, message)
        """
        esl_path = config.get_cert_path(name, "esl")
        p7_path = config.get_cert_path(name, "p7")

        time_str = self._TIME.strftime("%Y-%m-%dT%H:%M:%S")

        ps_cmd = (
            f'Set-SecureBootUEFI -Name {name} '
            f'-ContentFilePath "{esl_path}" '
            f'-SignedFilePath "{p7_path}" '
            f'-Time (Get-Date "{time_str}")'
        )

        log_fn(f"  Importing {name}...")

        try:
            result = subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True, timeout=30,
                creationflags=_CREATE_NO_WINDOW
            )

            stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
            stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""

            if result.returncode == 0:
                log_fn(f"  ✓ {name} imported ({esl_path.stat().st_size} bytes)")
                return True, "OK"
            else:
                error_msg = (stderr or stdout).strip()
                log_fn(f"  ✗ {name} failed: {error_msg}")
                return False, error_msg

        except Exception as e:
            log_fn(f"  ✗ {name} exception: {e}")
            return False, str(e)
