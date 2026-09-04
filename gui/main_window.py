"""
主窗口 — 所有 UI 构建与事件处理
"""
import os
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QGroupBox, QFrame,
    QFileDialog, QMessageBox, QProgressBar, QSizePolicy,
    QTabWidget, QComboBox, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer

from core.config import APP_DIR, KEYS_DIR, CERTS_DIR, EXTRACTED_DIR, RESOURCE_DIR
from core.wsl_utils import check_wsl_available, check_sbsigntool, check_openssl
from core.key_manager import KeyManager
from core.signer import EfiSigner
from core.cert_extractor import CertExtractor
from core.db_builder import DatabaseBuilder
from core.bios_import import BIOSImporter
from core.partition_utils import (
    is_admin, get_oc_directory_from_partition, get_windows_boot_from_partition,
    format_size, list_disks, list_partitions
)

from gui.workers import (
    SignWorker, ExtractWorker, BuildWorker, ImportWorker, MountWorker,
    InstallWorker
)
from gui.widgets import DropFrame, LogWidget, LoadingOverlay
from gui.dialogs import AdminConfirmDialog, LogDialog, AboutDialog, ResultDialog
from gui.styles import (
    MAIN_WINDOW_QSS, ADMIN_BAR_QSS, LIMITED_BAR_QSS, ELEVATE_BTN_QSS,
    MOUNT_BTN_QSS, SIGN_BTN_QSS, EXTRACT_BTN_QSS, BUILD_BTN_QSS,
    IMPORT_BTN_QSS, LOG_BTN_QSS
)


class MainWindow(QMainWindow):
    def __init__(self, admin_mode: bool = False):
        super().__init__()
        self.admin_mode = admin_mode
        self.setWindowTitle("OpenCore 安全启动工具")
        self.setMinimumSize(640, 640)
        self.resize(660, 700)
        self.setStyleSheet(MAIN_WINDOW_QSS)

        # 设置窗口图标（优先 ICO，回退 SVG）
        icon_ico = RESOURCE_DIR / "gui" / "assets" / "icon.ico"
        icon_svg = RESOURCE_DIR / "gui" / "assets" / "icon.svg"
        if icon_ico.exists():
            self.setWindowIcon(QIcon(str(icon_ico)))
        elif icon_svg.exists():
            renderer = QSvgRenderer(str(icon_svg))
            if renderer.isValid():
                icon = QIcon()
                for sz in (16, 32, 48, 64, 128, 256):
                    pm = QPixmap(sz, sz)
                    pm.fill(Qt.GlobalColor.transparent)
                    p = QPainter(pm)
                    renderer.render(p)
                    p.end()
                    icon.addPixmap(pm)
                self.setWindowIcon(icon)
            else:
                self.setWindowIcon(QIcon(str(icon_svg)))

        # 核心对象
        self.key_manager = KeyManager()
        self.signer = EfiSigner()
        self.extractor = CertExtractor()
        self.builder = DatabaseBuilder()
        self.importer = BIOSImporter()

        # 日志组件（隐藏，通过弹窗显示）
        self.log_widget = LogWidget()
        self.log_widget.setVisible(False)
        self._log_dialog = None

        self._build_ui()
        self._update_status()
        self._env_ok = False

        # 加载遮罩（覆盖在 centralWidget 上）
        self._loading = LoadingOverlay(self.centralWidget())
        QTimer.singleShot(200, self._check_dependencies)

    # ============================================================
    # UI 构建
    # ============================================================
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(7)

        self._build_top_bar(main_layout)
        self._build_status_panel(main_layout)
        self._build_keys_panel(main_layout)
        self._build_sign_extract_tabs(main_layout)
        self._build_build_panel(main_layout)
        self._build_import_panel(main_layout)

        main_layout.addStretch()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_loading') and self._loading:
            self._loading.setGeometry(self.centralWidget().rect())

    def bring_to_front(self):
        """将主窗口置于桌面最前面。"""
        self.raise_()
        self.activateWindow()
        self.setWindowState(Qt.WindowState.WindowActive)
        # Windows API 强制置前
        try:
            import ctypes
            hwnd = int(self.winId())
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.BringWindowToTop(hwnd)
            # 如果被挡住，用 system param 强制
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        except Exception:
            pass

    def _build_top_bar(self, parent_layout):
        bar = QFrame()
        bar.setObjectName("topBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 6, 12, 6)

        if self.admin_mode:
            self.lbl_admin = QLabel("🛡  管理员模式 — 全部功能可用")
            self.lbl_admin.setStyleSheet(ADMIN_BAR_QSS)
        else:
            self.lbl_admin = QLabel("⚠  受限模式 — 自动检测/导入不可用")
            self.lbl_admin.setStyleSheet(LIMITED_BAR_QSS)
        bar_layout.addWidget(self.lbl_admin)

        # 环境检测状态（紧挨管理员状态，可点击重新查看）
        self._env_result_msg = ""
        self.lbl_env_status = QPushButton("环境：检查中...")
        self.lbl_env_status.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_env_status.setStyleSheet("""
            QPushButton {
                border: 1px solid #d0d5dd; font-weight: bold; font-size: 9pt;
                background: #f8f9fa; padding: 3px 10px; border-radius: 4px;
            }
            QPushButton:hover { background: #eef1f5; }
        """)
        self.lbl_env_status.clicked.connect(self._on_env_status_click)
        bar_layout.addWidget(self.lbl_env_status)

        bar_layout.addStretch()

        btn_about = QPushButton("关于")
        btn_about.setStyleSheet(LOG_BTN_QSS)
        btn_about.setFixedWidth(55)
        btn_about.clicked.connect(self._on_about)
        bar_layout.addWidget(btn_about)

        btn_elevate = QPushButton("获取管理员权限")
        btn_elevate.setStyleSheet(ELEVATE_BTN_QSS)
        btn_elevate.setFixedWidth(110)
        btn_elevate.clicked.connect(self._on_elevate)
        if self.admin_mode:
            btn_elevate.setEnabled(False)
            btn_elevate.setText("已获取权限")
        bar_layout.addWidget(btn_elevate)

        parent_layout.addWidget(bar)

    def _build_status_panel(self, parent_layout):
        group = QGroupBox("运行状态")
        layout = QHBoxLayout(group)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        self.lbl_keys_status = QLabel("密钥：检查中...")
        self.lbl_keys_status.setStyleSheet("font-weight: bold; font-size: 9pt;")
        layout.addWidget(self.lbl_keys_status)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #ccc;")
        sep.setFixedHeight(16)
        layout.addWidget(sep)

        self.lbl_bios_status = QLabel("BIOS：检查中...")
        self.lbl_bios_status.setStyleSheet("font-weight: bold; font-size: 9pt;")
        layout.addWidget(self.lbl_bios_status)

        self.lbl_sizes = QLabel("")
        self.lbl_sizes.setStyleSheet("color: #888888; font-size: 8pt;")
        layout.addWidget(self.lbl_sizes)

        layout.addStretch()

        btn_log = QPushButton("📋 日志")
        btn_log.setStyleSheet(LOG_BTN_QSS)
        btn_log.clicked.connect(self._on_show_log)
        layout.addWidget(btn_log)

        parent_layout.addWidget(group)

    def _build_keys_panel(self, parent_layout):
        group = QGroupBox("密钥管理")
        layout = QHBoxLayout(group)
        layout.setContentsMargins(10, 4, 10, 6)
        layout.setSpacing(8)

        btn_gen = QPushButton("生成新密钥")
        btn_gen.clicked.connect(self._on_generate_keys)
        layout.addWidget(btn_gen)

        btn_open_keys = QPushButton("打开密钥目录")
        btn_open_keys.clicked.connect(lambda: os.startfile(str(KEYS_DIR)))
        layout.addWidget(btn_open_keys)

        btn_backup = QPushButton("备份密钥...")
        btn_backup.clicked.connect(self._on_backup_keys)
        layout.addWidget(btn_backup)

        layout.addStretch()
        parent_layout.addWidget(group)

    def _build_sign_extract_tabs(self, parent_layout):
        tabs = QTabWidget()
        tabs.setStyleSheet("QTabWidget::pane { padding: 4px; }")

        mount_tab = QWidget()
        mount_layout = QVBoxLayout(mount_tab)
        mount_layout.setContentsMargins(4, 4, 4, 4)
        mount_layout.setSpacing(6)
        self._build_mount_mode_ui(mount_layout)
        tabs.addTab(mount_tab, "挂载引导分区模式")

        manual_tab = QWidget()
        manual_layout = QVBoxLayout(manual_tab)
        manual_layout.setContentsMargins(4, 4, 4, 4)
        manual_layout.setSpacing(6)
        self._build_manual_mode_ui(manual_layout)
        tabs.addTab(manual_tab, "指定文件模式")

        parent_layout.addWidget(tabs)

    def _build_mount_mode_ui(self, layout):
        # 顶部：磁盘/分区选择 + 挂载按钮
        mount_group = QGroupBox("挂载 EFI 引导分区")
        mount_layout = QVBoxLayout(mount_group)
        mount_layout.setContentsMargins(10, 4, 10, 8)
        mount_layout.setSpacing(6)

        sel_row = QHBoxLayout()
        sel_row.setSpacing(6)

        lbl_disk = QLabel("磁盘：")
        lbl_disk.setFixedWidth(40)
        lbl_disk.setStyleSheet("font-size: 9pt; color: #888888;")
        sel_row.addWidget(lbl_disk)

        self.cbo_disk = QComboBox()
        self.cbo_disk.setPlaceholderText("选择磁盘...")
        self.cbo_disk.currentIndexChanged.connect(self._on_disk_changed)
        sel_row.addWidget(self.cbo_disk, 2)

        lbl_part = QLabel("分区：")
        lbl_part.setFixedWidth(40)
        lbl_part.setStyleSheet("font-size: 9pt; color: #888888;")
        sel_row.addWidget(lbl_part)

        self.cbo_partition = QComboBox()
        self.cbo_partition.setPlaceholderText("选择分区...")
        sel_row.addWidget(self.cbo_partition, 2)

        self.btn_mount = QPushButton("挂载")
        self.btn_mount.setFixedWidth(50)
        self.btn_mount.setStyleSheet(MOUNT_BTN_QSS)
        self.btn_mount.clicked.connect(self._on_mount_button_clicked)
        sel_row.addWidget(self.btn_mount)

        mount_layout.addLayout(sel_row)

        self.lbl_mount_status = QLabel("未挂载 — 请选择磁盘和分区后点击「挂载」")
        self.lbl_mount_status.setStyleSheet("color: #888888; font-size: 9pt; padding: 3px;")
        self.lbl_mount_status.setWordWrap(True)
        mount_layout.addWidget(self.lbl_mount_status)

        self._mounted_drive = None

        layout.addWidget(mount_group)

        # 下方左右并排
        row = QHBoxLayout()
        row.setSpacing(8)

        # 左：OC 签名
        oc_group = QGroupBox("第一步：签名 OpenCore EFI")
        oc_layout = QVBoxLayout(oc_group)
        oc_layout.setContentsMargins(10, 4, 10, 8)
        oc_layout.setSpacing(6)

        self.lbl_oc_path = QLabel("OC 目录：未检测")
        self.lbl_oc_path.setStyleSheet("color: #888888; font-size: 8.5pt;")
        self.lbl_oc_path.setWordWrap(True)
        oc_layout.addWidget(self.lbl_oc_path)

        self.chk_backup_oc = QCheckBox("签名前自动备份原始文件")
        self.chk_backup_oc.setChecked(True)
        oc_layout.addWidget(self.chk_backup_oc)

        self.progress_sign = QProgressBar()
        self.progress_sign.setVisible(False)
        oc_layout.addWidget(self.progress_sign)

        btn_sign = QPushButton("签名所有 EFI 文件")
        btn_sign.setStyleSheet(SIGN_BTN_QSS)
        btn_sign.clicked.connect(self._on_sign_oc_mount)
        oc_layout.addWidget(btn_sign)

        oc_layout.addStretch()
        row.addWidget(oc_group, 1)

        # 右：Win 提取
        win_group = QGroupBox("第二步：提取 Windows 证书")
        win_layout = QVBoxLayout(win_group)
        win_layout.setContentsMargins(10, 4, 10, 8)
        win_layout.setSpacing(6)

        self.lbl_win_path = QLabel("Win 目录：未检测")
        self.lbl_win_path.setStyleSheet("color: #888888; font-size: 8.5pt;")
        self.lbl_win_path.setWordWrap(True)
        win_layout.addWidget(self.lbl_win_path)

        # 占位组件 — 与左侧复选框对齐
        _align_spacer = QWidget()
        _align_spacer.setFixedHeight(20)
        win_layout.addWidget(_align_spacer)

        self.progress_extract = QProgressBar()
        self.progress_extract.setVisible(False)
        win_layout.addWidget(self.progress_extract)

        btn_extract = QPushButton("提取并重建数据库")
        btn_extract.setStyleSheet(EXTRACT_BTN_QSS)
        btn_extract.clicked.connect(self._on_extract_mount)
        win_layout.addWidget(btn_extract)

        win_layout.addStretch()
        row.addWidget(win_group, 1)

        layout.addLayout(row)

        if not self.admin_mode:
            warn = QLabel("⚠  受限模式下无法挂载分区，请切换到「指定文件模式」或获取管理员权限")
            warn.setStyleSheet("color: #e67e22; font-size: 9pt; padding: 5px; background-color: #fff3cd; border-radius: 4px;")
            warn.setWordWrap(True)
            layout.addWidget(warn)

        if self.admin_mode:
            self._refresh_disk_lists()

    def _build_manual_mode_ui(self, layout):
        row = QHBoxLayout()
        row.setSpacing(8)

        # 左：OC 签名
        oc_group = QGroupBox("第一步：签名 OpenCore EFI")
        oc_layout = QVBoxLayout(oc_group)
        oc_layout.setContentsMargins(10, 4, 10, 8)
        oc_layout.setSpacing(6)

        self.drop_oc = DropFrame("拖拽 OC 文件夹到此处", "或点击下方浏览按钮选择", "#4A90D9")
        self.drop_oc.dropped.connect(self._on_oc_dropped)
        oc_layout.addWidget(self.drop_oc)

        path_row = QHBoxLayout()
        path_row.setSpacing(5)
        self.txt_oc_path = QLineEdit()
        self.txt_oc_path.setPlaceholderText("OC 目录路径...")
        self.txt_oc_path.setReadOnly(True)
        path_row.addWidget(self.txt_oc_path, 1)

        btn_browse = QPushButton("浏览")
        btn_browse.setFixedWidth(48)
        btn_browse.clicked.connect(self._on_browse_oc)
        path_row.addWidget(btn_browse)
        oc_layout.addLayout(path_row)

        self.chk_backup_oc_manual = QCheckBox("签名前自动备份原始文件")
        self.chk_backup_oc_manual.setChecked(True)
        oc_layout.addWidget(self.chk_backup_oc_manual)

        self.progress_sign_manual = QProgressBar()
        self.progress_sign_manual.setVisible(False)
        oc_layout.addWidget(self.progress_sign_manual)

        btn_sign = QPushButton("签名所有 EFI 文件")
        btn_sign.setStyleSheet(SIGN_BTN_QSS)
        btn_sign.clicked.connect(self._on_sign_oc_manual)
        oc_layout.addWidget(btn_sign)

        oc_layout.addStretch()
        row.addWidget(oc_group, 1)

        # 右：Win 提取
        win_group = QGroupBox("第二步：提取 Windows 证书")
        win_layout = QVBoxLayout(win_group)
        win_layout.setContentsMargins(10, 4, 10, 8)
        win_layout.setSpacing(6)

        self.drop_win = DropFrame("拖拽 Windows EFI 文件夹", "或点击下方浏览按钮选择", "#e67e22")
        self.drop_win.dropped.connect(self._on_win_dropped)
        win_layout.addWidget(self.drop_win)

        path_row2 = QHBoxLayout()
        path_row2.setSpacing(5)
        self.txt_win_path = QLineEdit()
        self.txt_win_path.setPlaceholderText("Windows EFI 目录路径...")
        self.txt_win_path.setReadOnly(True)
        path_row2.addWidget(self.txt_win_path, 1)

        btn_browse2 = QPushButton("浏览")
        btn_browse2.setFixedWidth(48)
        btn_browse2.clicked.connect(self._on_browse_win)
        path_row2.addWidget(btn_browse2)
        win_layout.addLayout(path_row2)

        # 占位组件 — 与左侧复选框对齐
        _align_spacer2 = QWidget()
        _align_spacer2.setFixedHeight(20)
        win_layout.addWidget(_align_spacer2)

        self.progress_extract_manual = QProgressBar()
        self.progress_extract_manual.setVisible(False)
        win_layout.addWidget(self.progress_extract_manual)

        btn_extract = QPushButton("提取并重建数据库")
        btn_extract.setStyleSheet(EXTRACT_BTN_QSS)
        btn_extract.clicked.connect(self._on_extract_manual)
        win_layout.addWidget(btn_extract)

        win_layout.addStretch()
        row.addWidget(win_group, 1)

        layout.addLayout(row)

    def _build_build_panel(self, parent_layout):
        group = QGroupBox("第三步：构建证书")
        layout = QHBoxLayout(group)
        layout.setContentsMargins(10, 4, 10, 6)
        layout.setSpacing(8)

        btn_build_all = QPushButton("构建全部（PK + KEK + db）")
        btn_build_all.setStyleSheet(BUILD_BTN_QSS)
        btn_build_all.clicked.connect(self._on_build_all)
        layout.addWidget(btn_build_all)

        btn_build_db = QPushButton("仅重建 db")
        btn_build_db.clicked.connect(self._on_build_db)
        layout.addWidget(btn_build_db)

        btn_open_certs = QPushButton("打开证书目录")
        btn_open_certs.clicked.connect(lambda: os.startfile(str(CERTS_DIR)))
        layout.addWidget(btn_open_certs)

        layout.addStretch()
        parent_layout.addWidget(group)

    def _build_import_panel(self, parent_layout):
        group = QGroupBox("第四步：导入到 BIOS")
        layout = QHBoxLayout(group)
        layout.setContentsMargins(10, 4, 10, 6)
        layout.setSpacing(12)

        btn_import = QPushButton("将证书导入 BIOS")
        btn_import.setStyleSheet(IMPORT_BTN_QSS)
        btn_import.clicked.connect(self._on_import_bios)
        if not self.admin_mode:
            btn_import.setEnabled(False)
            btn_import.setToolTip("需要管理员权限")
        layout.addWidget(btn_import)

        note = QLabel("完整导入需 Setup 模式\nBIOS → 安全 → 安全启动 → 重置为设置模式")
        note.setStyleSheet("color: #888888; font-size: 8pt;")
        note.setWordWrap(True)
        layout.addWidget(note, 1)

        layout.addStretch()
        parent_layout.addWidget(group)

    # ============================================================
    # 日志弹窗
    # ============================================================
    def _on_show_log(self):
        if self._log_dialog is None:
            self._log_dialog = LogDialog(self.log_widget, self)
        self._log_dialog.show()
        self._log_dialog.raise_()
        self._log_dialog.activateWindow()

    def _on_about(self):
        dlg = AboutDialog(self)
        dlg.exec()

    # ============================================================
    # 状态更新
    # ============================================================
    def _update_status(self):
        if self.key_manager.keys_exist():
            self.lbl_keys_status.setText("✓ 密钥：PK + KEK + ISK 就绪")
            self.lbl_keys_status.setStyleSheet("font-weight: bold; color: #27ae60; font-size: 9pt;")
        else:
            self.lbl_keys_status.setText("✗ 密钥：未生成")
            self.lbl_keys_status.setStyleSheet("font-weight: bold; color: #e74c3c; font-size: 9pt;")

        try:
            status = self.importer.get_status()
            if status.setup_mode:
                self.lbl_bios_status.setText("BIOS：设置模式（可导入）")
                self.lbl_bios_status.setStyleSheet("font-weight: bold; color: #e67e22; font-size: 9pt;")
            elif status.secure_boot_enabled:
                self.lbl_bios_status.setText("BIOS：安全启动已激活")
                self.lbl_bios_status.setStyleSheet("font-weight: bold; color: #27ae60; font-size: 9pt;")
            else:
                self.lbl_bios_status.setText("BIOS：用户模式（安全启动关闭）")
                self.lbl_bios_status.setStyleSheet("font-weight: bold; color: #e67e22; font-size: 9pt;")
            self.lbl_sizes.setText(f"PK: {status.pk_size}B | KEK: {status.kek_size}B | db: {status.db_size}B")
        except Exception:
            self.lbl_bios_status.setText("BIOS：无法查询")
            self.lbl_bios_status.setStyleSheet("font-weight: bold; color: #888888; font-size: 9pt;")

    def _do_env_check(self):
        """只检查环境并记录日志，不弹窗。"""
        self._env_wsl = check_wsl_available()
        self._env_openssl = False
        self._env_sbsigntool = False

        if self._env_wsl:
            self.log_widget.success("WSL 可用")
            self._env_openssl = check_openssl()
            self._env_sbsigntool = check_sbsigntool()

            if self._env_openssl:
                self.log_widget.success("OpenSSL 可用")
            else:
                self.log_widget.warning("未找到 OpenSSL")

            if self._env_sbsigntool:
                self.log_widget.success("sbsigntool + efitools 可用")
            else:
                self.log_widget.warning("未找到 sbsigntool")
        else:
            self.log_widget.error("未检测到 WSL")

        self._env_ok = self._env_wsl and self._env_openssl and self._env_sbsigntool
        self._update_env_status()

    def _update_env_status(self):
        """更新状态栏中的环境检测状态标签。"""
        if self._env_ok:
            self.lbl_env_status.setText("环境：✓ 全部正常")
            self.lbl_env_status.setStyleSheet("""
                QPushButton {
                    border: none; font-weight: bold; font-size: 9pt; color: #27ae60;
                    background: transparent; text-align: left; padding: 0px;
                }
                QPushButton:hover { text-decoration: underline; }
            """)
            self._env_result_msg = "环境检测通过，全部功能可用。"
        elif not self._env_wsl:
            self.lbl_env_status.setText("环境：✗ 未安装 WSL")
            self.lbl_env_status.setStyleSheet("""
                QPushButton {
                    border: none; font-weight: bold; font-size: 9pt; color: #e74c3c;
                    background: transparent; text-align: left; padding: 0px;
                }
                QPushButton:hover { text-decoration: underline; }
            """)
            self._env_result_msg = (
                "未检测到 WSL (Windows Subsystem for Linux)。\n\n"
                "安装步骤：\n"
                "  1. 以管理员身份打开 PowerShell\n"
                "  2. 运行：wsl --install\n"
                "  3. 重启电脑\n"
                "  4. 重新启动本工具"
            )
        else:
            missing = []
            if not self._env_sbsigntool:
                missing.append("sbsigntool + efitools")
            if not self._env_openssl:
                missing.append("openssl")
            self.lbl_env_status.setText(f"环境：⚠ 缺少 {'、'.join(missing)}")
            self.lbl_env_status.setStyleSheet("""
                QPushButton {
                    border: none; font-weight: bold; font-size: 9pt; color: #e67e22;
                    background: transparent; text-align: left; padding: 0px;
                }
                QPushButton:hover { text-decoration: underline; }
            """)
            self._env_result_msg = (
                f"WSL 已安装，但缺少以下组件：\n\n  {'、'.join(missing)}\n\n"
                "可在 WSL 中手动安装：\n"
                "  sudo apt-get update && sudo apt-get install -y sbsigntool efitools openssl\n\n"
                "或重新运行本工具点击「一键安装」。"
            )

    def _on_env_status_click(self):
        """点击环境状态标签 — 重新显示环境检测结果。"""
        if self._env_ok:
            ResultDialog.success(self, "环境检测", self._env_result_msg)
        elif not self._env_wsl:
            ResultDialog.error(self, "环境检测 — 未安装 WSL", self._env_result_msg)
        else:
            ResultDialog.warning(self, "环境检测 — 缺少组件", self._env_result_msg)

    def _check_dependencies(self):
        """启动时的环境检测 — 含弹窗提示和一键安装。"""
        import tempfile, os
        _diag = os.path.join(tempfile.gettempdir(), "sbt_diag.log")
        def _w(msg):
            with open(_diag, 'a', encoding='utf-8') as f:
                f.write(f"{msg}\n")

        _w("[_check_dependencies] 开始执行")
        self.log_widget.info("=" * 50)
        self.log_widget.info("正在检测运行环境...")
        self.log_widget.info(f"应用目录：{APP_DIR}")

        if self.admin_mode:
            self.log_widget.success("管理员权限已获取")
        else:
            self.log_widget.warning("当前为受限模式，部分功能不可用")

        try:
            _w("[_check_dependencies] 调用 _do_env_check()")
            self._do_env_check()
            _w(f"[_check_dependencies] 环境检测完成: wsl={self._env_wsl}, openssl={self._env_openssl}, sbsigntool={self._env_sbsigntool}")
        except Exception as e:
            _w(f"[_check_dependencies] _do_env_check 异常: {e}")
            import traceback
            with open(_diag, 'a', encoding='utf-8') as f:
                traceback.print_exc(file=f)
            return

        if not self._env_wsl:
            _w("[_check_dependencies] WSL 未安装，显示错误弹窗")
            try:
                ResultDialog.error(
                    self, "环境检测 — 未安装 WSL",
                    "本工具依赖 WSL (Windows Subsystem for Linux) 执行签名和证书操作。\n\n"
                    "安装步骤：\n"
                    "  1. 以管理员身份打开 PowerShell\n"
                    "  2. 运行：wsl --install\n"
                    "  3. 重启电脑\n"
                    "  4. 重新启动本工具\n\n"
                    "点击确定以受限模式继续。"
                )
            except Exception as e:
                _w(f"[_check_dependencies] ResultDialog 异常: {e}")
                import traceback
                with open(_diag, 'a', encoding='utf-8') as f:
                    traceback.print_exc(file=f)
            self.log_widget.warning("环境检测未通过，签名/提取/构建功能不可用。")
            _w("[_check_dependencies] 完成 (WSL 未安装)")
            return

        if not self._env_ok:
            _w("[_check_dependencies] 缺少组件，显示 QMessageBox")
            missing = []
            if not self._env_sbsigntool:
                missing.append("sbsigntool + efitools")
            if not self._env_openssl:
                missing.append("openssl")

            reply = QMessageBox.question(
                self, "环境检测 — 缺少必要组件",
                f"WSL 已安装，但缺少以下组件：\n\n  {'、'.join(missing)}\n\n"
                "是否自动安装所需组件？\n"
                "（需要在 WSL 中使用 sudo 权限）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._install_deps()
                return

        if self._env_ok:
            self.log_widget.success("环境检测通过，全部功能可用。")
        else:
            self.log_widget.warning("环境检测未通过，部分功能不可用。")

    def _install_deps(self):
        """后台安装 WSL 依赖组件。"""
        self.log_widget.info("=" * 50)
        self.log_widget.info("正在安装依赖组件（sbsigntool, efitools, openssl）...")
        self._loading.show_with_message("正在安装依赖组件...")

        self.install_worker = InstallWorker()
        self.install_worker.progress.connect(lambda msg: (self.log_widget.info(msg), self._loading.update_message(msg)))
        self.install_worker.finished.connect(self._on_install_finished)
        self.install_worker.start()

    def _on_install_finished(self, ok: bool, msg: str):
        self._loading.hide_overlay()
        if ok:
            self.log_widget.success("依赖组件安装成功！")
            ResultDialog.info(
                self, "安装成功",
                "依赖组件安装成功！\n现在可以使用全部功能。"
            )
            self._do_env_check()
            if self._env_ok:
                self.log_widget.success("环境检测通过，全部功能可用。")
        else:
            self.log_widget.error(f"安装失败：{msg}")
            ResultDialog.error(
                self, "安装失败",
                f"依赖组件安装失败。\n\n"
                "请手动在 WSL 中运行：\n"
                "  wsl -u root -- apt-get update && apt-get install -y sbsigntool efitools openssl\n\n"
                f"错误信息：{msg[:300]}"
            )
        self._update_status()

    # ============================================================
    # 权限
    # ============================================================
    def _on_elevate(self):
        reply = QMessageBox.question(
            self, "获取管理员权限",
            "将以管理员身份重新启动本工具。\n\n"
            "需要管理员权限的功能：\n"
            "  • 自动检测和挂载 EFI 分区\n"
            "  • 向 BIOS 导入安全启动证书\n"
            "  • 修改系统分区文件\n\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._elevate_to_admin()

    def _elevate_to_admin(self):
        import ctypes
        main_script = str(APP_DIR / "main.py")
        try:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{main_script}"', None, 1)
            sys.exit(0)
        except Exception as e:
            ResultDialog.error(self, "错误", f"无法获取管理员权限：\n{e}")

    # ============================================================
    # 密钥
    # ============================================================
    def _on_generate_keys(self):
        reply = QMessageBox.question(
            self, "确认",
            "将生成新的 PK、KEK 和 ISK 密钥。\n现有密钥会被覆盖。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.log_widget.info("正在生成新密钥...")
        self._loading.show_with_message("正在生成密钥...")
        ok = self.key_manager.generate_keys(
            progress_callback=lambda msg: self.log_widget.info(msg)
        )
        self._loading.hide_overlay()
        if ok:
            self.log_widget.success("密钥生成成功！")
            self._update_status()
            ResultDialog.success(
                self, "密钥生成成功",
                f"PK、KEK、ISK 密钥已生成并保存到：\n  {KEYS_DIR}\n\n"
                f"请妥善备份密钥文件，丢失后无法补发。"
            )
        else:
            self.log_widget.error("密钥生成失败，请查看日志。")
            ResultDialog.error(self, "密钥生成失败", "密钥生成过程中出错。\n\n请查看日志获取详细信息。")

    def _on_backup_keys(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "备份密钥", "secureboot_keys_backup.zip", "ZIP 文件 (*.zip)"
        )
        if path:
            if self.key_manager.backup_keys(path):
                self.log_widget.success(f"密钥已备份到：{path}")
                ResultDialog.success(self, "备份成功", f"密钥已备份到：\n  {path}")
            else:
                self.log_widget.error("备份失败")
                ResultDialog.error(self, "备份失败", "密钥备份过程中出错。")

    # ============================================================
    # 挂载分区模式
    # ============================================================
    def _refresh_disk_lists(self):
        try:
            disks = list_disks()
            self.cbo_disk.blockSignals(True)
            self.cbo_disk.clear()

            for disk in disks:
                label = f"磁盘 {disk['number']} - {format_size(disk['size'])}"
                if disk["model"]:
                    label += f"  ({disk['model'][:30]})"
                if disk["gpt"]:
                    label += " [GPT]"
                self.cbo_disk.addItem(label, disk["number"])

            self.cbo_disk.blockSignals(False)

            if disks:
                self.cbo_disk.setCurrentIndex(0)
                self._load_partitions_for_disk(disks[0]["number"])
        except Exception as e:
            self.log_widget.warning(f"获取磁盘列表失败：{e}")

    def _load_partitions_for_disk(self, disk_number: int):
        try:
            partitions = list_partitions(disk_number)
            self.cbo_partition.clear()

            for p in partitions:
                size_str = format_size(p["size"])
                label = f"分区 {p['number']} - {size_str}"
                is_efi = p["gpt_type"] and "c12a7328" in p["gpt_type"].lower()
                if is_efi:
                    label += " [EFI]"
                if p["drive_letter"]:
                    label += f"  ({p['drive_letter']})"
                self.cbo_partition.addItem(label, p)
        except Exception as e:
            self.log_widget.warning(f"获取分区列表失败：{e}")

    def _on_disk_changed(self, index: int):
        if index < 0:
            return
        disk_num = self.cbo_disk.currentData()
        if disk_num is not None:
            self._load_partitions_for_disk(disk_num)

    def _on_mount_button_clicked(self):
        """挂载/卸载按钮分发器。"""
        if self._mounted_drive:
            self._on_unmount_partition()
        else:
            self._on_mount_partition()

    def _on_unmount_partition(self):
        """卸载当前已挂载的分区。"""
        if not self.admin_mode:
            ResultDialog.warning(self, "提示", "卸载分区需要管理员权限。")
            return

        if not self._mounted_drive:
            return

        drive = self._mounted_drive
        self.btn_mount.setEnabled(False)
        self.btn_mount.setText("卸载中...")
        self.lbl_mount_status.setText(f"正在卸载 {drive}...")
        self.lbl_mount_status.setStyleSheet("color: #e67e22; font-size: 9pt; padding: 3px;")
        self._loading.show_with_message(f"正在卸载 {drive}...")

        self.log_widget.info(f"正在卸载分区 {drive}...")

        from gui.workers import UnmountWorker
        self.unmount_worker = UnmountWorker(drive)
        self.unmount_worker.finished.connect(self._on_unmount_finished)
        self.unmount_worker.start()

    def _on_unmount_finished(self, ok: bool, message: str):
        """卸载完成回调。"""
        self._loading.hide_overlay()
        self.btn_mount.setEnabled(True)

        if ok:
            drive = self._mounted_drive
            self.log_widget.success(f"分区 {drive} 已卸载")
            self._mounted_drive = None
            self._oc_mounted_path = None
            self._win_mounted_path = None

            # 重置 UI
            self.btn_mount.setText("挂载")
            self.btn_mount.setStyleSheet(MOUNT_BTN_QSS)
            self.lbl_mount_status.setText("未挂载 — 请选择磁盘和分区后点击「挂载」")
            self.lbl_mount_status.setStyleSheet("color: #888888; font-size: 9pt; padding: 3px;")
            self.lbl_oc_path.setText("OC 目录：未检测")
            self.lbl_oc_path.setStyleSheet("color: #888888; font-size: 8.5pt;")
            self.lbl_win_path.setText("Win 目录：未检测")
            self.lbl_win_path.setStyleSheet("color: #888888; font-size: 8.5pt;")

            # 刷新分区列表
            disk_num = self.cbo_disk.currentData()
            if disk_num is not None:
                self._load_partitions_for_disk(disk_num)

            ResultDialog.success(self, "卸载成功", f"分区 {drive} 已卸载。")
        else:
            self.btn_mount.setText("卸载")
            self.lbl_mount_status.setText(f"✗ 卸载失败：{message}")
            self.lbl_mount_status.setStyleSheet("color: #e74c3c; font-size: 9pt; padding: 3px;")
            self.log_widget.error(f"卸载失败：{message}")
            ResultDialog.error(self, "卸载失败", f"卸载分区失败：\n{message}")

    def _on_mount_partition(self):
        if not self.admin_mode:
            ResultDialog.warning(self, "提示", "挂载分区需要管理员权限。\n请先获取管理员权限。")
            return

        part_data = self.cbo_partition.currentData()
        if part_data is None:
            ResultDialog.warning(self, "警告", "请先选择分区！")
            return

        disk_num = self.cbo_disk.currentData()
        part_num = part_data["number"]

        if part_data["drive_letter"]:
            self._mounted_drive = part_data["drive_letter"]
            self.btn_mount.setText("卸载")
            self.btn_mount.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: #ffffff;
                    font-weight: bold;
                    border: none;
                    border-radius: 6px;
                    font-size: 9pt;
                }
                QPushButton:hover { background-color: #d44233; }
            """)
            self.log_widget.info(f"分区已有盘符 {part_data['drive_letter']}，正在检测路径...")

            # 简化分区下拉 — 只显示已挂载分区
            self.cbo_partition.clear()
            self.cbo_partition.addItem(f"分区 {self._mounted_drive}（已挂载）", {"number": 0, "drive_letter": self._mounted_drive})

            self._detect_paths_after_mount(part_data["drive_letter"])
            return

        self.btn_mount.setEnabled(False)
        self.btn_mount.setText("挂载中...")
        self.lbl_mount_status.setText("正在挂载分区...")
        self.lbl_mount_status.setStyleSheet("color: #e67e22; font-size: 9pt; padding: 3px;")

        self.log_widget.info(f"正在挂载分区（磁盘{disk_num} 分区{part_num}）...")
        self._loading.show_with_message("正在挂载分区...")

        self.mount_worker = MountWorker(disk_num, part_num)
        self.mount_worker.finished.connect(self._on_mount_finished)
        self.mount_worker.start()

    def _on_mount_finished(self, ok: bool, result: str):
        self._loading.hide_overlay()
        self.btn_mount.setEnabled(True)

        if ok:
            drive = result
            self._mounted_drive = drive
            self.log_widget.success(f"分区已挂载为 {drive}")
            self.lbl_mount_status.setText(f"✓ 已挂载为 {drive}，正在检测引导路径...")
            self.lbl_mount_status.setStyleSheet("color: #27ae60; font-size: 9pt; padding: 3px;")

            # 切换为卸载按钮
            self.btn_mount.setText("卸载")
            self.btn_mount.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: #ffffff;
                    font-weight: bold;
                    border: none;
                    border-radius: 6px;
                    font-size: 9pt;
                }
                QPushButton:hover { background-color: #d44233; }
            """)

            # 简化分区下拉 — 只显示已挂载分区
            self.cbo_partition.clear()
            part_text = f"分区 {self._mounted_drive}（已挂载）"
            self.cbo_partition.addItem(part_text, {"number": 0, "drive_letter": drive})

            self._detect_paths_after_mount(drive)
        else:
            self.btn_mount.setText("挂载")
            self.lbl_mount_status.setText(f"✗ 挂载失败：{result}")
            self.lbl_mount_status.setStyleSheet("color: #e74c3c; font-size: 9pt; padding: 3px;")
            self.log_widget.error(f"挂载失败：{result}")
            ResultDialog.error(self, "挂载失败", f"挂载分区失败：\n{result}")

    def _detect_paths_after_mount(self, drive: str):
        oc_dir = get_oc_directory_from_partition(drive)
        if oc_dir:
            self.lbl_oc_path.setText(f"OC 目录：{oc_dir}")
            self.lbl_oc_path.setStyleSheet("color: #27ae60; font-size: 8.5pt;")
            self._oc_mounted_path = oc_dir
            self.log_widget.success(f"检测到 OC 目录：{oc_dir}")
        else:
            self.lbl_oc_path.setText("OC 目录：未检测到")
            self.lbl_oc_path.setStyleSheet("color: #888888; font-size: 8.5pt;")
            self._oc_mounted_path = None
            self.log_widget.warning(f"在 {drive} 中未检测到 OC 目录")

        win_dir = get_windows_boot_from_partition(drive)
        if win_dir:
            self.lbl_win_path.setText(f"Win 目录：{win_dir}")
            self.lbl_win_path.setStyleSheet("color: #27ae60; font-size: 8.5pt;")
            self._win_mounted_path = win_dir
            self.log_widget.success(f"检测到 Windows 启动目录：{win_dir}")
        else:
            self.lbl_win_path.setText("Win 目录：未检测到")
            self.lbl_win_path.setStyleSheet("color: #888888; font-size: 8.5pt;")
            self._win_mounted_path = None
            self.log_widget.warning(f"在 {drive} 中未检测到 Windows 启动目录")

        if oc_dir or win_dir:
            self.lbl_mount_status.setText(f"✓ 已挂载为 {drive}，路径检测完成")
            self.lbl_mount_status.setStyleSheet("color: #27ae60; font-size: 9pt; padding: 3px;")
            parts = [f"分区已挂载为 {drive}"]
            if oc_dir:
                parts.append(f"\nOC 目录：{oc_dir}")
            if win_dir:
                parts.append(f"\nWin 目录：{win_dir}")
            ResultDialog.info(self, "挂载成功", "\n".join(parts))
        else:
            self.lbl_mount_status.setText(f"✓ 已挂载为 {drive}（未检测到引导目录）")
            self.lbl_mount_status.setStyleSheet("color: #e67e22; font-size: 9pt; padding: 3px;")

    def _log_config_patch(self, result):
        """在日志中输出 config.plist DisableSecurityPolicy 修补结果。"""
        patch = getattr(result, "config_patch", None)
        if patch is None:
            return
        if not patch.found:
            self.log_widget.warning(patch.message)
        elif patch.already_set:
            self.log_widget.info(f"config.plist: {patch.message}")
        elif patch.patched:
            self.log_widget.success(f"config.plist: {patch.message}")
        else:
            self.log_widget.error(f"config.plist: {patch.message}")

    def _on_sign_oc_mount(self):
        oc_path = getattr(self, "_oc_mounted_path", None)
        if not oc_path:
            ResultDialog.warning(self, "警告", "未检测到 OC 目录！\n请先挂载分区或切换到「指定文件模式」。")
            return
        if not self.key_manager.keys_exist():
            ResultDialog.warning(self, "警告", "未找到密钥！请先生成密钥。")
            return

        backup = self.chk_backup_oc.isChecked()
        self.log_widget.info("=" * 50)
        self.log_widget.info(f"开始签名 OC EFI 文件：{oc_path}")
        if backup:
            self.log_widget.info("已启用自动备份")

        self.progress_sign.setVisible(True)
        self.progress_sign.setValue(0)

        self._loading.show_with_message("正在签名 OC EFI 文件...")
        self.sign_worker = SignWorker(str(oc_path), backup=backup)
        self.sign_worker.progress.connect(self._on_sign_progress_mount)
        self.sign_worker.finished.connect(self._on_sign_finished_mount)
        self.sign_worker.start()

    def _on_sign_progress_mount(self, msg: str, current: int, total: int):
        self.log_widget.info(msg)
        self._loading.update_message(msg)
        if total > 0:
            self.progress_sign.setMaximum(total)
            self.progress_sign.setValue(current)

    def _on_sign_finished_mount(self, result):
        self._loading.hide_overlay()
        self.progress_sign.setVisible(False)
        self.log_widget.info("-" * 50)
        self.log_widget.info(f"签名完成：{result.signed} 个成功，{result.failed} 个失败")
        if result.backup_dir:
            self.log_widget.info(f"原始文件已备份到：{result.backup_dir}")
        self._log_config_patch(result)
        if result.success:
            self.log_widget.success("所有文件签名成功！")
        else:
            self.log_widget.error("部分文件签名失败，请查看上方日志。")
        self._popup_sign_result(result)

    def _popup_sign_result(self, result):
        """弹窗显示签名结果。"""
        patch = getattr(result, "config_patch", None)
        parts = [f"签名完成\n  成功：{result.signed} 个\n  失败：{result.failed} 个"]
        if result.backup_dir:
            parts.append(f"\n备份目录：\n  {result.backup_dir}")
        if patch:
            parts.append(f"\nconfig.plist：\n  {patch.message}")
        if result.success:
            ResultDialog.info(self, "签名结果", "\n".join(parts))
        elif result.failed == result.total:
            ResultDialog.error(self, "签名结果", "\n".join(parts))
        else:
            ResultDialog.warning(self, "签名结果", "\n".join(parts))

    def _on_extract_mount(self):
        win_path = getattr(self, "_win_mounted_path", None)
        if not win_path:
            ResultDialog.warning(self, "警告", "未检测到 Windows 启动目录！\n请先挂载分区或切换到「指定文件模式」。")
            return
        self._do_extract(str(win_path), self.progress_extract)

    # ============================================================
    # 指定文件模式
    # ============================================================
    def _on_oc_dropped(self, path: str):
        self.txt_oc_path.setText(path)
        self.log_widget.info(f"已选择 OC 文件夹：{path}")

    def _on_browse_oc(self):
        path = QFileDialog.getExistingDirectory(self, "选择 OC 目录")
        if path:
            self.txt_oc_path.setText(path)

    def _on_sign_oc_manual(self):
        path = self.txt_oc_path.text().strip()
        if not path:
            ResultDialog.warning(self, "警告", "请先选择 OC 目录！")
            return
        if not self.key_manager.keys_exist():
            ResultDialog.warning(self, "警告", "未找到密钥！请先生成密钥。")
            return

        backup = self.chk_backup_oc_manual.isChecked()
        self.log_widget.info("=" * 50)
        self.log_widget.info(f"开始签名 OC EFI 文件：{path}")
        if backup:
            self.log_widget.info("已启用自动备份")

        self.progress_sign_manual.setVisible(True)
        self.progress_sign_manual.setValue(0)

        self._loading.show_with_message("正在签名 OC EFI 文件...")
        self.sign_worker = SignWorker(path, backup=backup)
        self.sign_worker.progress.connect(self._on_sign_progress_manual)
        self.sign_worker.finished.connect(self._on_sign_finished_manual)
        self.sign_worker.start()

    def _on_sign_progress_manual(self, msg: str, current: int, total: int):
        self.log_widget.info(msg)
        self._loading.update_message(msg)
        if total > 0:
            self.progress_sign_manual.setMaximum(total)
            self.progress_sign_manual.setValue(current)

    def _on_sign_finished_manual(self, result):
        self._loading.hide_overlay()
        self.progress_sign_manual.setVisible(False)
        self.log_widget.info("-" * 50)
        self.log_widget.info(f"签名完成：{result.signed} 个成功，{result.failed} 个失败")
        if result.backup_dir:
            self.log_widget.info(f"原始文件已备份到：{result.backup_dir}")
        self._log_config_patch(result)
        if result.success:
            self.log_widget.success("所有文件签名成功！")
        else:
            self.log_widget.error("部分文件签名失败，请查看上方日志。")
        self._popup_sign_result(result)

    def _on_win_dropped(self, path: str):
        self.txt_win_path.setText(path)
        self.log_widget.info(f"已选择 Windows EFI 文件夹：{path}")

    def _on_browse_win(self):
        path = QFileDialog.getExistingDirectory(self, "选择 Windows EFI 启动目录")
        if path:
            self.txt_win_path.setText(path)

    def _on_extract_manual(self):
        path = self.txt_win_path.text().strip()
        if not path:
            ResultDialog.warning(self, "警告", "请先选择 Windows EFI 目录！")
            return
        self._do_extract(path, self.progress_extract_manual)

    def _do_extract(self, path: str, progress_bar: QProgressBar):
        self.log_widget.info("=" * 50)
        self.log_widget.info(f"正在提取 Windows 证书：{path}")

        progress_bar.setVisible(True)
        progress_bar.setValue(0)

        self._loading.show_with_message("正在提取 Windows 证书...")
        self.extract_worker = ExtractWorker(path)
        self.extract_worker.progress.connect(
            lambda msg, cur, total: self._on_extract_progress(msg, cur, total, progress_bar)
        )
        self.extract_worker.finished.connect(self._on_extract_finished)
        self.extract_worker.start()

    def _on_extract_progress(self, msg: str, current: int, total: int, progress_bar: QProgressBar):
        self.log_widget.info(msg)
        self._loading.update_message(msg)
        if total > 0:
            progress_bar.setMaximum(total)
            progress_bar.setValue(current)

    def _on_extract_finished(self, certs: list):
        self._loading.hide_overlay()
        self.progress_extract.setVisible(False)
        self.progress_extract_manual.setVisible(False)
        self.log_widget.info(f"已提取 {len(certs)} 个唯一证书")

        for cert in certs:
            self.log_widget.info(f"  - {cert.subject or cert.filename}")

        if certs:
            self.log_widget.success(f"证书已保存到：{EXTRACTED_DIR}")
            cert_list = "\n".join(f"  • {c.subject or c.filename}" for c in certs)
            ResultDialog.info(
                self, "提取结果",
                f"成功提取 {len(certs)} 个证书：\n\n{cert_list}\n\n"
                f"已保存到：{EXTRACTED_DIR}\n\n将自动重建 db。"
            )
            self.log_widget.info("正在使用提取的证书重建 db...")
            self._on_build_db()
        else:
            self.log_widget.warning("未提取到任何证书。")
            ResultDialog.warning(
                self, "提取结果",
                "未提取到任何证书。\n\n"
                "可能原因：\n"
                "  1. EFI 文件没有 Authenticode 签名\n"
                "  2. 证书解析失败\n\n"
                "请查看日志获取详细信息。"
            )

    # ============================================================
    # 构建
    # ============================================================
    def _on_build_all(self):
        if not self.key_manager.keys_exist():
            ResultDialog.warning(self, "警告", "未找到密钥！请先生成密钥。")
            return

        self.log_widget.info("=" * 50)
        self.log_widget.info("正在构建所有证书（PK + KEK + db）...")
        self._loading.show_with_message("正在构建证书...")
        self.build_worker = BuildWorker(build_all=True)
        self.build_worker.progress.connect(lambda msg: (self.log_widget.info(msg), self._loading.update_message(msg)))
        self.build_worker.finished.connect(self._on_build_finished)
        self.build_worker.start()

    def _on_build_db(self):
        if not self.key_manager.keys_exist():
            ResultDialog.warning(self, "警告", "未找到密钥！")
            return

        self.log_widget.info("正在构建 db...")
        self._loading.show_with_message("正在构建 db...")
        self.build_worker = BuildWorker(build_all=False)
        self.build_worker.progress.connect(lambda msg: (self.log_widget.info(msg), self._loading.update_message(msg)))
        self.build_worker.finished.connect(self._on_build_finished)
        self.build_worker.start()

    def _on_build_finished(self, ok: bool):
        self._loading.hide_overlay()
        if ok:
            sizes = self.builder.get_cert_sizes()
            self.log_widget.success("证书构建完成！")
            self.log_widget.info(f"  PK:  {sizes['PK_esl']}B (ESL) | {sizes['PK_p7']}B (P7)")
            self.log_widget.info(f"  KEK: {sizes['KEK_esl']}B (ESL) | {sizes['KEK_p7']}B (P7)")
            self.log_widget.info(f"  db:  {sizes['db_esl']}B (ESL) | {sizes['db_p7']}B (P7)")
            ResultDialog.info(
                self, "构建结果",
                f"证书构建完成！\n\n"
                f"  PK:  {sizes['PK_esl']}B (ESL) | {sizes['PK_p7']}B (P7)\n"
                f"  KEK: {sizes['KEK_esl']}B (ESL) | {sizes['KEK_p7']}B (P7)\n"
                f"  db:  {sizes['db_esl']}B (ESL) | {sizes['db_p7']}B (P7)\n\n"
                f"已保存到：{CERTS_DIR}"
            )
        else:
            self.log_widget.error("构建失败，请查看上方日志。")
            ResultDialog.error(self, "构建结果", "证书构建失败！\n\n请查看日志获取详细信息。")

    # ============================================================
    # 导入 BIOS
    # ============================================================
    def _on_import_bios(self):
        if not self.admin_mode:
            ResultDialog.warning(self, "提示", "导入 BIOS 需要管理员权限。\n请先点击「获取管理员权限」。")
            return

        for name in ["PK", "KEK", "db"]:
            esl = CERTS_DIR / f"{name}.esl"
            p7 = CERTS_DIR / f"{name}.p7"
            if not esl.exists() or not p7.exists():
                ResultDialog.warning(self, "警告", f"缺少 {name}.esl 或 {name}.p7！\n请先构建证书（第三步）。")
                return

        status = self.importer.get_status()
        if status.setup_mode:
            msg = (
                "BIOS 处于设置模式（PK 为空）。\n\n"
                "导入顺序：\n  1. db（签名数据库）\n  2. KEK（密钥交换密钥）\n  3. PK（平台密钥）\n\n"
                "导入完成后安全启动将被激活。\n\n是否继续？"
            )
        else:
            msg = (
                "BIOS 处于用户模式（PK 已设置）。\n\n"
                "用户模式无法更改 PK，将仅更新 db 和 KEK。\n\n"
                "如需替换 PK，请在 BIOS 中重置为设置模式。\n\n是否继续？"
            )

        reply = QMessageBox.question(self, "确认导入", msg,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.log_widget.info("=" * 50)
        self.log_widget.info("正在将证书导入 BIOS...")
        self._loading.show_with_message("正在导入证书到 BIOS...")

        self.import_worker = ImportWorker()
        self.import_worker.progress.connect(lambda msg: (self.log_widget.info(msg), self._loading.update_message(msg)))
        self.import_worker.finished.connect(self._on_import_finished)
        self.import_worker.start()

    def _on_import_finished(self, ok: bool, msg: str):
        self._loading.hide_overlay()
        if ok:
            self.log_widget.success(f"导入成功：{msg}")
            self._update_status()
            ResultDialog.info(self, "成功", "证书导入成功！\n\n请重启电脑以生效。")
        else:
            self.log_widget.error(f"导入失败：{msg}")
            ResultDialog.error(self, "错误", f"导入失败：\n{msg}")
