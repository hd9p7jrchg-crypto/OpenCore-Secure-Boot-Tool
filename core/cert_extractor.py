"""
Certificate extraction module.
Extracts certificates from Windows EFI files (Authenticode signatures).
"""
import struct
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Callable
from . import config


class ExtractedCert:
    """Represents an extracted certificate."""
    def __init__(self, data: bytes, subject: str = "", issuer: str = "", thumbprint: str = ""):
        self.data = data
        self.subject = subject
        self.issuer = issuer
        self.thumbprint = thumbprint
        self.filename = ""

    def save(self, path: str | Path):
        """Save certificate to file."""
        Path(path).write_bytes(self.data)


class CertExtractor:
    """Extracts certificates from Windows EFI files."""

    def __init__(self):
        self.output_dir = config.EXTRACTED_DIR

    def find_efi_files(self, directory: str | Path) -> List[Path]:
        """Find all .efi files in directory."""
        directory = Path(directory)
        if not directory.exists():
            return []
        return sorted(directory.rglob("*.efi"))

    def extract_from_file(self, filepath: str | Path) -> List[ExtractedCert]:
        """Try to extract certificates from a single file.

        Uses multiple methods:
        1. Direct X509 import (if file is a cert)
        2. Authenticode signature extraction from PE files
        """
        certs = []
        filepath = Path(filepath)

        # Method 1: Try cryptography library
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes

            data = filepath.read_bytes()
            try:
                cert = x509.load_der_x509_certificate(data)
                thumb = cert.fingerprint(hashes.SHA256()).hex()
                ec = ExtractedCert(
                    data=data,
                    subject=cert.subject.rfc4514_string(),
                    issuer=cert.issuer.rfc4514_string(),
                    thumbprint=thumb
                )
                certs.append(ec)
                return certs
            except Exception:
                pass
        except ImportError:
            pass

        # Method 2: Extract Authenticode signature from PE file
        try:
            pe_certs = self._extract_pe_signature_certs(filepath)
            certs.extend(pe_certs)
        except Exception:
            pass

        return certs

    def _extract_pe_signature_certs(self, filepath: Path) -> List[ExtractedCert]:
        """Extract certificates from PE file's Authenticode signature."""
        certs = []
        data = filepath.read_bytes()

        if len(data) < 0x40:
            return certs

        # Check MZ signature
        if data[0:2] != b'MZ':
            return certs

        # Get PE header offset
        pe_offset = struct.unpack_from('<I', data, 0x3C)[0]
        if pe_offset + 4 > len(data):
            return certs

        # Check PE signature
        if data[pe_offset:pe_offset+4] != b'PE\x00\x00':
            return certs

        # Parse PE header to find certificate table
        # PE32 or PE32+
        magic_offset = pe_offset + 24
        if magic_offset + 2 > len(data):
            return certs

        magic = struct.unpack_from('<H', data, magic_offset)[0]

        if magic == 0x10b:  # PE32
            cert_table_offset = pe_offset + 152  # IMAGE_DIRECTORY_ENTRY_SECURITY (4th entry, offset 128+24? Let's compute properly)
        elif magic == 0x20b:  # PE32+
            cert_table_offset = pe_offset + 168
        else:
            return certs

        # Actually compute from number of directories
        # PE header structure:
        # PE signature (4) + COFF header (20) = 24 bytes from pe_offset
        # Then Optional header starts at pe_offset + 24
        # Magic at offset 0 of optional header (2 bytes)
        # Number of RVA and sizes at different offsets for PE32 vs PE32+
        # Security directory is index 4

        # Let's use a more robust approach
        try:
            # Optional header starts at pe_offset + 24
            opt_header_start = pe_offset + 24

            if magic == 0x10b:  # PE32
                # NumberOfRvaAndSizes at offset 92 from opt header start
                num_rva_offset = opt_header_start + 92
                # Data directory starts at offset 96
                data_dir_start = opt_header_start + 96
            else:  # PE32+
                num_rva_offset = opt_header_start + 108
                data_dir_start = opt_header_start + 112

            if num_rva_offset + 4 > len(data):
                return certs

            num_rva = struct.unpack_from('<I', data, num_rva_offset)[0]
            if num_rva < 5:
                return certs

            # Security directory (index 4) = RVA + Size (8 bytes each entry, 4 bytes for RVA + 4 for size)
            sec_dir_offset = data_dir_start + 4 * 8

            if sec_dir_offset + 8 > len(data):
                return certs

            cert_rva, cert_size = struct.unpack_from('<II', data, sec_dir_offset)

            if cert_size == 0 or cert_rva == 0:
                return certs

            if cert_rva + cert_size > len(data):
                return certs

            # Parse WIN_CERTIFICATE structure
            cert_data = data[cert_rva:cert_rva + cert_size]

            # WIN_CERTIFICATE:
            #   dwLength (4)
            #   wRevision (2)
            #   wCertificateType (2)
            #   bCertificate (variable)

            offset = 0
            while offset + 8 < len(cert_data):
                dwLength, wRevision, wCertType = struct.unpack_from('<IHH', cert_data, offset)

                if dwLength == 0:
                    break

                cert_content_start = offset + 8
                cert_content_end = offset + dwLength

                if cert_content_end > len(cert_data):
                    break

                # WIN_CERT_TYPE_PKCS_SIGNED_DATA = 2
                if wCertType == 2:
                    pkcs_data = cert_data[cert_content_start:cert_content_end]
                    extracted = self._extract_certs_from_pkcs7(pkcs_data)
                    certs.extend(extracted)

                offset += ((dwLength + 7) // 8) * 8  # Align to 8 bytes

        except Exception:
            pass

        return certs

    def _extract_certs_from_pkcs7(self, pkcs_data: bytes) -> List[ExtractedCert]:
        """Extract certificates from PKCS#7 signed data.

        Tries multiple methods:
        1. cryptography.pkcs7 API
        2. Manual DER scan for X.509 certificate patterns
        """
        certs = []

        # Method 1: Try cryptography pkcs7 API
        try:
            from cryptography.hazmat.primitives.serialization import pkcs7
            from cryptography.hazmat.primitives import hashes, serialization

            try:
                p7 = pkcs7.load_der_pkcs7_certificates(pkcs_data)
                for cert in p7:
                    thumb = cert.fingerprint(hashes.SHA256()).hex()
                    ec = ExtractedCert(
                        data=cert.public_bytes(serialization.Encoding.DER),
                        subject=cert.subject.rfc4514_string(),
                        issuer=cert.issuer.rfc4514_string(),
                        thumbprint=thumb
                    )
                    certs.append(ec)
                if certs:
                    return certs
            except Exception:
                pass
        except ImportError:
            pass

        # Method 2: Manual DER scan — find X.509 certificates by pattern
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization

            found = self._scan_for_der_certs(pkcs_data)
            for der_data in found:
                try:
                    cert = x509.load_der_x509_certificate(der_data)
                    thumb = cert.fingerprint(hashes.SHA256()).hex()
                    ec = ExtractedCert(
                        data=der_data,
                        subject=cert.subject.rfc4514_string(),
                        issuer=cert.issuer.rfc4514_string(),
                        thumbprint=thumb
                    )
                    certs.append(ec)
                except Exception:
                    continue
        except ImportError:
            pass

        return certs

    def _scan_for_der_certs(self, data: bytes) -> List[bytes]:
        """Scan raw bytes for DER-encoded X.509 certificate patterns.

        A DER certificate starts with 0x30 0x82 (SEQUENCE, 2-byte length).
        """
        results = []
        offset = 0
        data_len = len(data)

        while offset < data_len - 4:
            # Look for SEQUENCE tag with 2-byte length: 0x30 0x82
            if data[offset] == 0x30 and data[offset + 1] == 0x82:
                # Read the 2-byte length (big-endian)
                cert_len = (data[offset + 2] << 8) | data[offset + 3]
                cert_start = offset
                cert_end = offset + 4 + cert_len

                # Sanity check: certificate should be reasonable size (512B - 32KB)
                if 512 <= cert_len <= 32768 and cert_end <= data_len:
                    cert_data = data[cert_start:cert_end]
                    # Try to validate it's a real certificate
                    try:
                        from cryptography import x509
                        x509.load_der_x509_certificate(cert_data)
                        results.append(cert_data)
                        offset = cert_end
                        continue
                    except Exception:
                        pass

            offset += 1

        return results

    def extract_from_directory(
        self,
        directory: str | Path,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> List[ExtractedCert]:
        """Extract all unique certificates from EFI files in a directory.

        Args:
            directory: Directory to scan
            progress_callback: Optional callback (msg, current, total)

        Returns:
            List of unique extracted certificates
        """
        directory = Path(directory)
        files = self.find_efi_files(directory)
        total = len(files)

        if total == 0:
            if progress_callback:
                progress_callback("No EFI files found", 0, 0)
            return []

        seen_thumbprints: Dict[str, ExtractedCert] = {}

        for i, f in enumerate(files, 1):
            rel = str(f.relative_to(directory))
            if progress_callback:
                progress_callback(f"Scanning: {rel}", i, total)

            extracted = self.extract_from_file(f)
            for cert in extracted:
                if cert.thumbprint and cert.thumbprint not in seen_thumbprints:
                    seen_thumbprints[cert.thumbprint] = cert

        # Save all unique certificates
        result = list(seen_thumbprints.values())
        for idx, cert in enumerate(result, 1):
            # Generate filename from subject
            if cert.subject:
                # Extract CN from subject
                cn = cert.subject
                if "CN=" in cn:
                    cn = cn.split("CN=")[-1].split(",")[0]
                safe_name = "".join(c for c in cn if c.isalnum() or c in " -_")[:50]
                cert.filename = f"cert_{idx:02d}_{safe_name}.crt"
            else:
                cert.filename = f"cert_{idx:02d}.crt"

            cert.save(self.output_dir / cert.filename)

        if progress_callback:
            progress_callback(f"Extracted {len(result)} unique certificate(s)", total, total)

        return result
