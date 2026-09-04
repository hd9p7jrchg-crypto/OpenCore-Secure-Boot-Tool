"""
Key management module.
Handles generation and validation of PK, KEK, and ISK keys.
"""
from pathlib import Path
from typing import Callable, Optional
from . import config
from .wsl_utils import run_wsl, win_to_wsl_path


class KeyManager:
    """Manages Secure Boot keys (PK, KEK, ISK)."""

    def __init__(self):
        self.keys_dir = config.KEYS_DIR

    def keys_exist(self) -> bool:
        """Check if all required keys exist."""
        return config.keys_exist()

    def get_key_status(self) -> dict:
        """Get status of all keys."""
        status = {}
        for name, files in config.KEY_FILES.items():
            key_path = self.keys_dir / files["key"]
            pem_path = self.keys_dir / files["pem"]
            status[name] = {
                "key": key_path.exists(),
                "pem": pem_path.exists(),
                "key_size": key_path.stat().st_size if key_path.exists() else 0,
                "pem_size": pem_path.stat().st_size if pem_path.exists() else 0,
            }
        return status

    def generate_keys(self, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """Generate new PK, KEK, and ISK keys.

        Args:
            progress_callback: Optional callback for progress messages

        Returns:
            True if successful
        """
        def log(msg):
            if progress_callback:
                progress_callback(msg)

        keys_wsl = win_to_wsl_path(str(self.keys_dir))

        cmd = f"""
mkdir -p "{keys_wsl}" && cd "{keys_wsl}" &&
echo "Generating PK key..." &&
openssl req -new -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \\
    -keyout PK.key -out PK.pem \\
    -subj "/CN=OpenCore Platform Key/" &&
echo "Generating KEK key..." &&
openssl req -new -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \\
    -keyout KEK.key -out KEK.pem \\
    -subj "/CN=OpenCore Key Exchange Key/" &&
echo "Generating ISK key..." &&
openssl req -new -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \\
    -keyout ISK.key -out ISK.pem \\
    -subj "/CN=OpenCore Image Signing Key/" &&
echo "KEY_GEN_OK"
"""

        log("Generating PK/KEK/ISK keys (RSA-2048, valid 10 years)...")
        rc, stdout, stderr = run_wsl(cmd, timeout=60)

        output = stdout + stderr

        if "KEY_GEN_OK" in output and self.keys_exist():
            log("✓ Keys generated successfully!")
            return True
        else:
            log(f"✗ Key generation failed: {output}")
            return False

    def backup_keys(self, backup_path: str | Path) -> bool:
        """Backup all keys to a zip file.

        Args:
            backup_path: Path to save the backup zip

        Returns:
            True if successful
        """
        import zipfile
        backup_path = Path(backup_path)
        try:
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for name, files in config.KEY_FILES.items():
                    for ftype in ["key", "pem"]:
                        fpath = self.keys_dir / files[ftype]
                        if fpath.exists():
                            zf.write(fpath, fpath.name)
            return True
        except Exception:
            return False
