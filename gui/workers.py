"""
后台工作线程类 — 所有 QThread 子类集中管理
"""
from PyQt6.QtCore import QThread, pyqtSignal

from core.signer import EfiSigner
from core.cert_extractor import CertExtractor
from core.db_builder import DatabaseBuilder
from core.bios_import import BIOSImporter


class SignWorker(QThread):
    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal(object)

    def __init__(self, directory: str, backup: bool = True):
        super().__init__()
        self.directory = directory
        self.backup = backup

    def run(self):
        signer = EfiSigner()
        result = signer.sign_directory(
            self.directory,
            backup=self.backup,
            progress_callback=lambda msg, cur, total: self.progress.emit(msg, cur, total)
        )
        self.finished.emit(result)


class ExtractWorker(QThread):
    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal(list)

    def __init__(self, directory: str):
        super().__init__()
        self.directory = directory

    def run(self):
        extractor = CertExtractor()
        certs = extractor.extract_from_directory(
            self.directory,
            progress_callback=lambda msg, cur, total: self.progress.emit(msg, cur, total)
        )
        self.finished.emit(certs)


class BuildWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, build_all: bool = True):
        super().__init__()
        self.build_all = build_all

    def run(self):
        builder = DatabaseBuilder()
        if self.build_all:
            ok = builder.build_all(
                progress_callback=lambda msg: self.progress.emit(msg)
            )
        else:
            ok = builder.build_db(
                progress_callback=lambda msg: self.progress.emit(msg)
            )
        self.finished.emit(ok)


class ImportWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def run(self):
        importer = BIOSImporter()
        ok, msg = importer.import_certificates(
            progress_callback=lambda msg: self.progress.emit(msg)
        )
        self.finished.emit(ok, msg)


class MountWorker(QThread):
    """后台执行分区挂载，避免 UI 卡死。"""
    finished = pyqtSignal(bool, str)

    def __init__(self, disk_number: int, partition_number: int):
        super().__init__()
        self.disk_number = disk_number
        self.partition_number = partition_number

    def run(self):
        from core.partition_utils import mount_partition
        ok, result = mount_partition(self.disk_number, self.partition_number)
        self.finished.emit(ok, result)


class UnmountWorker(QThread):
    """后台执行分区卸载，避免 UI 卡死。"""
    finished = pyqtSignal(bool, str)

    def __init__(self, drive_letter: str):
        super().__init__()
        self.drive_letter = drive_letter

    def run(self):
        from core.partition_utils import unmount_partition
        ok, result = unmount_partition(self.drive_letter)
        self.finished.emit(ok, result)


class InstallWorker(QThread):
    """后台执行 WSL 依赖安装。"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def run(self):
        from core.wsl_utils import install_dependencies
        ok, output = install_dependencies()
        self.progress.emit(output)
        self.finished.emit(ok, output)
