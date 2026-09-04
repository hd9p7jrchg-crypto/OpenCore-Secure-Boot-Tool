"""
Configuration module for Secure Boot Tool.
Manages paths, settings, and global state.
"""
import os
import sys
from pathlib import Path


def get_app_dir():
    """Get the application base directory (for output: keys, certs, etc.)."""
    if getattr(sys, 'frozen', False):
        # PyInstaller bundle — exe 目录用于输出
        return Path(sys.executable).parent
    else:
        # Normal Python script
        return Path(__file__).parent.parent


def get_resource_dir():
    """Get the resource directory (for bundled assets like SVG icons)."""
    if getattr(sys, 'frozen', False):
        # PyInstaller bundle — 资源解压到 _MEIPASS
        return Path(sys._MEIPASS)
    else:
        # Normal Python script
        return Path(__file__).parent.parent


# Base directories
APP_DIR = get_app_dir()
RESOURCE_DIR = get_resource_dir()
KEYS_DIR = APP_DIR / "keys"
CERTS_DIR = APP_DIR / "certs"
EXTRACTED_DIR = APP_DIR / "extracted"
OUTPUT_DIR = APP_DIR / "output"
RESOURCES_DIR = APP_DIR / "resources"

# Ensure directories exist
for d in [KEYS_DIR, CERTS_DIR, EXTRACTED_DIR, OUTPUT_DIR, RESOURCES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Key file names
KEY_FILES = {
    "PK": {"key": "PK.key", "pem": "PK.pem"},
    "KEK": {"key": "KEK.key", "pem": "KEK.pem"},
    "ISK": {"key": "ISK.key", "pem": "ISK.pem"},
}

# Microsoft certificates (pre-packaged)
MS_CERTS = {
    "WinUEFICA2023": "WinUEFICA2023.pem",
    "MicWinProPCA2011": "MicWinProPCA2011.pem",
    "MicCorUEFCA2011": "MicCorUEFCA2011.pem",
}

# Certificate output files
CERT_OUTPUTS = {
    "PK": {"esl": "PK.esl", "p7": "PK.p7", "auth": "PK.auth"},
    "KEK": {"esl": "KEK.esl", "p7": "KEK.p7", "auth": "KEK.auth"},
    "db": {"esl": "db.esl", "p7": "db.p7", "auth": "db.auth"},
}


def get_key_path(key_name: str, key_type: str = "key") -> Path:
    """Get full path to a key file.

    Args:
        key_name: PK, KEK, or ISK
        key_type: 'key' or 'pem'
    """
    return KEYS_DIR / KEY_FILES[key_name][key_type]


def get_cert_path(cert_name: str, cert_type: str = "esl") -> Path:
    """Get full path to a certificate output file.

    Args:
        cert_name: PK, KEK, or db
        cert_type: 'esl', 'p7', or 'auth'
    """
    return CERTS_DIR / CERT_OUTPUTS[cert_name][cert_type]


def keys_exist() -> bool:
    """Check if all required keys exist."""
    for name, files in KEY_FILES.items():
        for ftype in ["key", "pem"]:
            if not (KEYS_DIR / files[ftype]).exists():
                return False
    return True
