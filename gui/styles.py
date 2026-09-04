"""
全局样式表 — 集中管理所有 QSS（白色主题）
"""
import sys
from pathlib import Path

# 获取 check.svg 的绝对路径（适配 PyInstaller 冻结模式）
if getattr(sys, 'frozen', False):
    _check_svg = str(Path(sys._MEIPASS) / "gui" / "assets" / "check.svg").replace("\\", "/")
else:
    _check_svg = str(Path(__file__).parent / "assets" / "check.svg").replace("\\", "/")

# 主窗口样式 — 白色清爽
MAIN_WINDOW_QSS = """
QMainWindow {
    background-color: #ffffff;
}

QWidget#central {
    background-color: #ffffff;
}

QGroupBox {
    font-weight: bold;
    font-size: 9pt;
    border: 1px solid #d0d5dd;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 6px;
    background-color: #ffffff;
    color: #333333;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #4A90D9;
}

QPushButton {
    padding: 5px 14px;
    border-radius: 6px;
    border: 1px solid #d0d5dd;
    background-color: #f0f4f8;
    color: #333333;
    font-size: 9pt;
    min-height: 22px;
}
QPushButton:hover {
    background-color: #e0e8f0;
    border-color: #4A90D9;
}
QPushButton:pressed {
    background-color: #d0dae8;
}
QPushButton:disabled {
    color: #aaaaaa;
    background-color: #f5f5f5;
    border-color: #e0e0e0;
}

QLineEdit {
    padding: 4px 8px;
    border: 1px solid #ccc;
    border-radius: 6px;
    background-color: #ffffff;
    color: #333333;
    font-size: 9pt;
    min-height: 22px;
}
QLineEdit:focus {
    border-color: #4A90D9;
}

QLabel {
    color: #333333;
    font-size: 9pt;
}

QProgressBar {
    border: 1px solid #d0d5dd;
    border-radius: 6px;
    text-align: center;
    height: 16px;
    background-color: #f5f5f5;
    font-size: 8pt;
    color: #666666;
}
QProgressBar::chunk {
    background-color: #4A90D9;
    border-radius: 4px;
}

QComboBox {
    padding: 3px 8px;
    border: 1px solid #ccc;
    border-radius: 6px;
    background-color: #ffffff;
    color: #333333;
    font-size: 9pt;
    min-height: 22px;
}
QComboBox:hover {
    border-color: #4A90D9;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #4A90D9;
    width: 0;
    height: 0;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #d0d5dd;
    selection-background-color: #4A90D9;
    selection-color: #ffffff;
    outline: none;
    padding: 4px;
}

QTabWidget::pane {
    border: 1px solid #d0d5dd;
    border-radius: 8px;
    top: -1px;
    background-color: #ffffff;
}
QTabBar::tab {
    padding: 5px 16px;
    border: 1px solid #d0d5dd;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    background-color: #f5f5f5;
    color: #888888;
    font-size: 9pt;
}
QTabBar::tab:selected {
    background-color: #ffffff;
    color: #4A90D9;
    font-weight: bold;
    border-bottom: 2px solid #4A90D9;
}
QTabBar::tab:hover:!selected {
    background-color: #e8edf5;
    color: #555555;
}

QCheckBox {
    color: #444444;
    font-size: 8.5pt;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1.5px solid #ccc;
    border-radius: 4px;
    background-color: #ffffff;
}
QCheckBox::indicator:hover {
    border-color: #4A90D9;
}
QCheckBox::indicator:checked {
    border-color: #4A90D9;
    background-color: #ffffff;
    image: url("%(check_svg)s");
}
QCheckBox::indicator:disabled {
    border-color: #e0e0e0;
    background-color: #f5f5f5;
}
QFrame#topBar {
    background-color: #f5f7fa;
    border: 1px solid #d0d5dd;
    border-radius: 8px;
}

QScrollBar:vertical {
    background: #f5f5f5;
    width: 8px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #c0c0c0;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QToolTip {
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #d0d5dd;
    border-radius: 4px;
    padding: 4px;
}
""" % {"check_svg": _check_svg}

# 顶部管理员状态条 — 管理员模式
ADMIN_BAR_QSS = "color: #27ae60; font-weight: bold; font-size: 9pt;"

# 顶部管理员状态条 — 受限模式
LIMITED_BAR_QSS = "color: #e67e22; font-weight: bold; font-size: 9pt;"

# 管理员按钮
ELEVATE_BTN_QSS = """
QPushButton {
    background-color: #4A90D9;
    color: #ffffff;
    border: none;
    padding: 5px 12px;
    font-size: 9pt;
    font-weight: bold;
    border-radius: 6px;
}
QPushButton:hover { background-color: #3a7bc8; }
QPushButton:disabled {
    background-color: #e0e0e0;
    color: #999999;
}
"""

# 绿色挂载按钮
MOUNT_BTN_QSS = """
QPushButton {
    background-color: #27ae60;
    color: #ffffff;
    font-weight: bold;
    border: none;
    border-radius: 6px;
    font-size: 9pt;
}
QPushButton:hover { background-color: #229954; }
QPushButton:disabled { background-color: #e0e0e0; color: #999999; }
"""

# 蓝色签名按钮
SIGN_BTN_QSS = """
QPushButton {
    background-color: #4A90D9;
    color: #ffffff;
    font-weight: bold;
    padding: 6px;
    border: none;
    border-radius: 6px;
    font-size: 9pt;
}
QPushButton:hover { background-color: #3a7bc8; }
QPushButton:disabled { background-color: #e0e0e0; color: #999999; }
"""

# 橙色提取按钮
EXTRACT_BTN_QSS = """
QPushButton {
    background-color: #e67e22;
    color: #ffffff;
    font-weight: bold;
    padding: 6px;
    border: none;
    border-radius: 6px;
    font-size: 9pt;
}
QPushButton:hover { background-color: #cf6f1e; }
QPushButton:disabled { background-color: #e0e0e0; color: #999999; }
"""

# 绿色构建按钮
BUILD_BTN_QSS = """
QPushButton {
    background-color: #27ae60;
    color: #ffffff;
    font-weight: bold;
    padding: 6px 16px;
    border: none;
    border-radius: 6px;
    font-size: 9.5pt;
}
QPushButton:hover { background-color: #229954; }
"""

# 红色导入按钮
IMPORT_BTN_QSS = """
QPushButton {
    background-color: #e74c3c;
    color: #ffffff;
    font-weight: bold;
    padding: 8px 20px;
    border: none;
    border-radius: 6px;
    font-size: 9.5pt;
}
QPushButton:hover { background-color: #d44233; }
QPushButton:disabled { background-color: #e0e0e0; color: #999999; }
"""

# 日志按钮
LOG_BTN_QSS = """
QPushButton {
    background-color: #f0f4f8;
    color: #333333;
    border: 1px solid #d0d5dd;
    padding: 5px 14px;
    font-size: 9pt;
    border-radius: 6px;
}
QPushButton:hover {
    background-color: #e0e8f0;
    border-color: #4A90D9;
    color: #4A90D9;
}
"""

# 弹窗样式（白色主题）
DIALOG_QSS = """
QDialog {
    background-color: #ffffff;
}
QLabel {
    color: #333333;
    font-size: 10pt;
}
QLabel#title {
    color: #4A90D9;
    font-size: 13pt;
    font-weight: bold;
}
QLabel#desc {
    color: #666666;
    font-size: 9.5pt;
}
QPushButton#primary {
    background-color: #4A90D9;
    color: #ffffff;
    font-weight: bold;
    border: none;
    padding: 8px 20px;
    font-size: 10pt;
    border-radius: 6px;
}
QPushButton#primary:hover { background-color: #3a7bc8; }
QPushButton#secondary {
    background-color: #f0f4f8;
    color: #333333;
    border: 1px solid #d0d5dd;
    padding: 8px 20px;
    font-size: 10pt;
    border-radius: 6px;
}
QPushButton#secondary:hover { background-color: #e0e8f0; }
QPushButton#danger {
    background-color: #e74c3c;
    color: #ffffff;
    font-weight: bold;
    border: none;
    padding: 8px 20px;
    font-size: 10pt;
    border-radius: 6px;
}
QPushButton#danger:hover { background-color: #d44233; }
QTextEdit#logView {
    background-color: #fafafa;
    border: 1px solid #d0d5dd;
    border-radius: 8px;
    padding: 8px;
    color: #333333;
    font-family: Consolas, 'Microsoft YaHei';
    font-size: 9pt;
}
"""
