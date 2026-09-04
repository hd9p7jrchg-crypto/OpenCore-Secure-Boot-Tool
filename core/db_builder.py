"""
Database (db) builder module.
Builds the EFI signature database (db) from ISK + Microsoft certs + extracted certs.
Also builds PK and KEK ESL/P7 files.
"""
from pathlib import Path
from typing import List, Callable, Optional
from . import config
from .wsl_utils import run_wsl, win_to_wsl_path


class DatabaseBuilder:
    """Builds Secure Boot databases (db, KEK, PK)."""

    def __init__(self):
        self.keys_dir = config.KEYS_DIR
        self.certs_dir = config.CERTS_DIR
        self.extracted_dir = config.EXTRACTED_DIR

    def _run_build_cmd(self, cmd: str, timeout: int = 60) -> tuple[int, str, str]:
        """Run a build command in WSL."""
        return run_wsl(cmd, timeout=timeout)

    def build_pk_kek(self, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """Build PK and KEK ESL + P7 files.

        Returns:
            True if successful
        """
        def log(msg):
            if progress_callback:
                progress_callback(msg)

        keys_wsl = win_to_wsl_path(str(self.keys_dir))
        certs_wsl = win_to_wsl_path(str(self.certs_dir))

        cmd = f"""
mkdir -p "{certs_wsl}" &&
cd "{keys_wsl}" &&

echo "Building PK..." &&
cert-to-efi-sig-list -g "$(uuidgen)" PK.pem "{certs_wsl}/PK.esl" &&
sign-efi-sig-list -k PK.key -c PK.pem PK "{certs_wsl}/PK.esl" "{certs_wsl}/PK.p7" &&

echo "Building KEK..." &&
cert-to-efi-sig-list -g "$(uuidgen)" KEK.pem "{certs_wsl}/KEK.esl" &&
sign-efi-sig-list -k PK.key -c PK.pem KEK "{certs_wsl}/KEK.esl" "{certs_wsl}/KEK.p7" &&

echo "PK_KEK_OK"
"""

        log("Building PK and KEK certificates...")
        rc, out, err = self._run_build_cmd(cmd, timeout=60)
        output = out + err

        if "PK_KEK_OK" in output:
            log("✓ PK and KEK built successfully")
            return True
        else:
            log(f"✗ PK/KEK build failed: {output}")
            return False

    def build_db(self, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """Build the db (signature database).

        Includes:
        - ISK (our image signing key)
        - Microsoft certificates (if present in keys dir)
        - Extracted Windows certificates (if present in extracted dir)

        Returns:
            True if successful
        """
        def log(msg):
            if progress_callback:
                progress_callback(msg)

        keys_wsl = win_to_wsl_path(str(self.keys_dir))
        certs_wsl = win_to_wsl_path(str(self.certs_dir))
        extracted_wsl = win_to_wsl_path(str(self.extracted_dir))

        cmd = f"""
mkdir -p "{certs_wsl}" &&
cd "{keys_wsl}" &&

# Start with ISK
echo "Adding ISK..." &&
cert-to-efi-sig-list -g "$(uuidgen)" ISK.pem /tmp/db_tmp.esl &&

# Add Microsoft Windows Production PCA 2011 if exists
if [ -f MicWinProPCA2011.pem ]; then
    echo "Adding Microsoft Windows Production PCA 2011..." &&
    cert-to-efi-sig-list -g "$(uuidgen)" MicWinProPCA2011.pem /tmp/ms1.esl &&
    cat /tmp/db_tmp.esl /tmp/ms1.esl > /tmp/db_combined.esl &&
    mv /tmp/db_combined.esl /tmp/db_tmp.esl
fi &&

# Add Microsoft UEFI CA 2011 if exists
if [ -f MicCorUEFCA2011.pem ]; then
    echo "Adding Microsoft UEFI CA 2011..." &&
    cert-to-efi-sig-list -g "$(uuidgen)" MicCorUEFCA2011.pem /tmp/ms2.esl &&
    cat /tmp/db_tmp.esl /tmp/ms2.esl > /tmp/db_combined.esl &&
    mv /tmp/db_combined.esl /tmp/db_tmp.esl
fi &&

# Add Windows UEFI CA 2023 if exists
if [ -f WinUEFICA2023.pem ]; then
    echo "Adding Windows UEFI CA 2023..." &&
    cert-to-efi-sig-list -g "$(uuidgen)" WinUEFICA2023.pem /tmp/ms3.esl &&
    cat /tmp/db_tmp.esl /tmp/ms3.esl > /tmp/db_combined.esl &&
    mv /tmp/db_combined.esl /tmp/db_tmp.esl
fi &&

# Add extracted Windows certificates
ext_count=0
for cert in "{extracted_wsl}"/*.crt; do
    [ -f "$cert" ] || continue
    echo "Adding extracted cert: $(basename "$cert")..." &&
    cert-to-efi-sig-list -g "$(uuidgen)" "$cert" /tmp/ext.esl &&
    cat /tmp/db_tmp.esl /tmp/ext.esl > /tmp/db_combined.esl &&
    mv /tmp/db_combined.esl /tmp/db_tmp.esl
    ext_count=$((ext_count + 1))
done &&

# Copy to certs dir
cp /tmp/db_tmp.esl "{certs_wsl}/db.esl" &&

# Sign db with KEK
echo "Signing db with KEK..." &&
sign-efi-sig-list -k KEK.key -c KEK.pem db "{certs_wsl}/db.esl" "{certs_wsl}/db.p7" &&

echo "DB_BUILD_OK"
"""

        log("Building signature database (db)...")
        rc, out, err = self._run_build_cmd(cmd, timeout=60)
        output = out + err

        if "DB_BUILD_OK" in output:
            db_esl = config.get_cert_path("db", "esl")
            db_p7 = config.get_cert_path("db", "p7")
            if db_esl.exists() and db_p7.exists():
                log(f"✓ db built: {db_esl.stat().st_size} bytes (ESL), {db_p7.stat().st_size} bytes (P7)")
                return True

        log(f"✗ db build failed: {output}")
        return False

    def build_all(self, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """Build all certificates: PK, KEK, and db.

        Returns:
            True if all successful
        """
        pk_ok = self.build_pk_kek(progress_callback)
        db_ok = self.build_db(progress_callback)
        return pk_ok and db_ok

    def get_cert_sizes(self) -> dict:
        """Get sizes of built certificate files."""
        sizes = {}
        for cert_name in ["PK", "KEK", "db"]:
            for cert_type in ["esl", "p7"]:
                path = config.get_cert_path(cert_name, cert_type)
                key = f"{cert_name}_{cert_type}"
                sizes[key] = path.stat().st_size if path.exists() else 0
        return sizes
