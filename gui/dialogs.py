"""
自定义弹窗 — 管理员权限确认弹窗（带动效） + 日志查看弹窗 + 关于弹窗
"""
import sys
import os
import ctypes
import time
import tempfile
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QFrame, QTextEdit, QSizePolicy
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, pyqtProperty, QRectF
from PyQt6.QtGui import QFont, QIcon, QPixmap, QPainter, QPen, QColor, QPaintEvent
from PyQt6.QtSvg import QSvgRenderer

from gui.styles import DIALOG_QSS
from gui.widgets import LogWidget
from core.config import RESOURCE_DIR

# 主窗口标题（用于 FindWindow 检测）
MAIN_WINDOW_TITLE = "OpenCore 安全启动工具"


def _set_svg_icon(widget, svg_path: Path):
    """从 SVG 文件设置窗口图标。"""
    renderer = QSvgRenderer(str(svg_path))
    if renderer.isValid():
        icon = QIcon()
        for sz in (16, 32, 48, 64, 128, 256):
            pm = QPixmap(sz, sz)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            renderer.render(p)
            p.end()
            icon.addPixmap(pm)
        widget.setWindowIcon(icon)
    else:
        widget.setWindowIcon(QIcon(str(svg_path)))


class _Spinner(QWidget):
    """简易旋转圆环动画。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._size = 56
        self.setFixedSize(self._size + 20, self._size + 20)
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _tick(self):
        self._angle = (self._angle + 8) % 360
        self.update()

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self._size
        cx = self.width() / 2
        cy = self.height() / 2
        rect = QRectF(cx - w / 2, cy - w / 2, w, w)

        # 背景圆
        p.setPen(QPen(QColor("#e0e5ee"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(rect, 0, 360 * 16)

        # 旋转弧段
        n = 8
        for i in range(n):
            alpha = int(255 * (1.0 - i / n))
            color = QColor(74, 144, 217, alpha)
            p.setPen(QPen(color, 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            start = (self._angle + i * 45) * 16
            p.drawArc(rect, -int(start), int(40 * 16))
        p.end()


class AdminConfirmDialog(QDialog):
    """启动时的管理员权限确认弹窗 — 自定义美化 + 淡入动效 + 提权加载等待。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("需要管理员权限")
        self.setFixedSize(440, 400)
        self.setStyleSheet(DIALOG_QSS)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # 设置窗口图标（任务栏显示）
        icon_ico = RESOURCE_DIR / "gui" / "assets" / "icon.ico"
        icon_svg = RESOURCE_DIR / "gui" / "assets" / "icon.svg"
        if icon_ico.exists():
            self.setWindowIcon(QIcon(str(icon_ico)))
        elif icon_svg.exists():
            _set_svg_icon(self, icon_svg)

        self._choice = "exit"
        self._content_widget = None
        self._loading_widget = None
        self._poll_timer = None
        self._poll_count = 0
        self._start_time = 0

        # 进程间通信：信号文件路径（比 FindWindowW 更可靠）
        self._signal_file = os.path.join(
            tempfile.gettempdir(),
            f"sbt_ready_{os.getpid()}.tmp"
        )
        # 清理残留文件
        try:
            if os.path.exists(self._signal_file):
                os.remove(self._signal_file)
        except Exception:
            pass

        self._build_ui()

        # 淡入动效
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(350)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def _build_ui(self):
        # 外层容器（圆角白色背景）
        container = QFrame()
        container.setObjectName("adminContainer")
        container.setStyleSheet("""
            QFrame#adminContainer {
                background-color: #ffffff;
                border: 1px solid #d0d5dd;
                border-radius: 16px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(container)

        inner = QVBoxLayout(container)
        inner.setContentsMargins(28, 28, 28, 22)
        inner.setSpacing(14)

        # ===== 内容区域（可隐藏） =====
        self._content_widget = QWidget()
        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        icon_label = QLabel("🛡")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("font-size: 36pt;")
        content_layout.addWidget(icon_label)

        title = QLabel("需要管理员权限")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(title)

        desc = QLabel(
            "本工具需要管理员权限才能执行以下操作：\n\n"
            "  1. 读取和修改 EFI 系统分区（ESP）\n"
            "  2. 挂载 / 卸载引导分区\n"
            "  3. 向 BIOS 导入安全启动证书\n"
            "  4. 签名后的 EFI 文件写回系统分区\n\n"
            "拒绝则部分功能不可用，请放心使用。"
        )
        desc.setObjectName("desc")
        desc.setAlignment(Qt.AlignmentFlag.AlignLeft)
        desc.setWordWrap(True)
        content_layout.addWidget(desc)

        content_layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_exit = QPushButton("退出")
        btn_exit.setObjectName("secondary")
        btn_exit.clicked.connect(lambda: self._on_choice("exit"))
        btn_row.addWidget(btn_exit)

        btn_continue = QPushButton("继续（受限）")
        btn_continue.setObjectName("secondary")
        btn_continue.clicked.connect(lambda: self._on_choice("continue"))
        btn_row.addWidget(btn_continue)

        btn_elevate = QPushButton("以管理员身份重启")
        btn_elevate.setObjectName("primary")
        btn_elevate.clicked.connect(lambda: self._on_choice("elevate"))
        btn_row.addWidget(btn_elevate)

        content_layout.addLayout(btn_row)
        inner.addWidget(self._content_widget)

        # ===== 加载区域（初始隐藏） =====
        self._loading_widget = QWidget()
        loading_layout = QVBoxLayout(self._loading_widget)
        loading_layout.setContentsMargins(0, 0, 0, 0)
        loading_layout.setSpacing(16)

        # 顶部弹性空间 — 将内容推到垂直居中
        loading_layout.addStretch(1)

        self._spinner = _Spinner()
        loading_layout.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignCenter)

        self._loading_label = QLabel("正在启动管理员模式...")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setStyleSheet("color: #4A90D9; font-size: 11pt; font-weight: bold;")
        loading_layout.addWidget(self._loading_label, 0, Qt.AlignmentFlag.AlignCenter)

        self._loading_sub = QLabel("如有 UAC 请在 UAC 提示中点击「是」")
        self._loading_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_sub.setStyleSheet("color: #999999; font-size: 9pt;")
        loading_layout.addWidget(self._loading_sub, 0, Qt.AlignmentFlag.AlignCenter)

        # 底部弹性空间 — 将内容推到垂直居中
        loading_layout.addStretch(1)
        self._loading_widget.hide()
        inner.addWidget(self._loading_widget)

    def _switch_to_loading(self):
        """切换到加载动画模式。"""
        self._content_widget.hide()
        self._loading_widget.show()
        self._spinner.start()

    def _on_choice(self, choice: str):
        self._choice = choice

        if choice == "elevate":
            # 切换到加载模式
            self._switch_to_loading()
            self._start_time = time.time()

            # 启动提权进程，传递信号文件路径
            try:
                if getattr(sys, 'frozen', False):
                    params = f'--signal "{self._signal_file}"'
                    ctypes.windll.shell32.ShellExecuteW(
                        None, "runas", sys.executable, params, None, 1
                    )
                else:
                    app_root = Path(__file__).parent.parent
                    params = f'"{app_root / "main.py"}" --signal "{self._signal_file}"'
                    ctypes.windll.shell32.ShellExecuteW(
                        None, "runas", sys.executable,
                        params, None, 1
                    )
            except Exception as e:
                self._loading_label.setText("提权失败")
                self._loading_sub.setText(f"错误：{e}")
                self._spinner.stop()
                QTimer.singleShot(2000, self.reject)
                return

            # 开始轮询等待新进程就绪
            self._poll_count = 0
            self._poll_timer = QTimer(self)
            self._poll_timer.setInterval(500)  # 每 500ms 检测一次
            self._poll_timer.timeout.connect(self._poll_new_window)
            self._poll_timer.start()
        else:
            self.accept()

    def _poll_new_window(self):
        """轮询检测新进程是否已就绪 — 信号文件优先 + FindWindow 后备。"""
        self._poll_count += 1
        elapsed = time.time() - self._start_time

        # ===== 实时状态更新：基于经过时间显示当前阶段 =====
        if elapsed < 5:
            self._loading_label.setText("等待 UAC 授权...")
            self._loading_sub.setText("请在弹出的 Windows 提示中点击「是」")
        elif elapsed < 15:
            self._loading_label.setText("正在启动管理员进程...")
            self._loading_sub.setText("正在等待进程完成初始化")
        elif elapsed < 25:
            self._loading_label.setText("正在加载应用程序框架...")
            self._loading_sub.setText("正在导入 Qt 界面组件库")
        elif elapsed < 40:
            self._loading_label.setText("正在初始化安全启动组件...")
            self._loading_sub.setText("正在加载密钥管理和签名模块")
        elif elapsed < 55:
            self._loading_label.setText("正在准备用户界面...")
            self._loading_sub.setText("即将就绪，请稍候...")
        else:
            self._loading_label.setText("启动耗时较长，请耐心等待...")
            self._loading_sub.setText("正在完成最后的初始化工作")

        # 超时检查：最多等待 60 秒（120 * 500ms）
        if self._poll_count > 120:
            self._poll_timer.stop()
            self._spinner.stop()
            self._loading_label.setText("等待超时")
            self._loading_sub.setText("进程未在规定时间内启动，请重试")
            QTimer.singleShot(3000, self.reject)
            return

        # 方法 1：检查信号文件（最可靠 — 由新进程主动创建）
        if os.path.exists(self._signal_file):
            self._poll_timer.stop()
            self._loading_label.setText("启动成功！")
            self._loading_sub.setText("正在切换到主程序...")
            try:
                os.remove(self._signal_file)
            except Exception:
                pass
            QTimer.singleShot(800, self.accept)
            return

        # 方法 2：FindWindowW 后备检测
        hwnd = ctypes.windll.user32.FindWindowW(None, MAIN_WINDOW_TITLE)
        if hwnd != 0:
            self._poll_timer.stop()
            self._loading_label.setText("启动成功！")
            self._loading_sub.setText("正在切换到主程序...")
            try:
                os.remove(self._signal_file)
            except Exception:
                pass
            QTimer.singleShot(800, self.accept)

    def exec_and_get_choice(self) -> str:
        """返回 'elevate' / 'continue' / 'exit'"""
        self._choice = "exit"
        self.exec()
        return self._choice


class ResultDialog(QDialog):
    """通用结果弹窗 — 与 AdminConfirmDialog 同风格（圆角、淡入、无边框）。

    用法:
        ResultDialog.success(parent, "标题", "内容")
        ResultDialog.warning(parent, "标题", "内容")
        ResultDialog.error(parent, "标题", "内容")
    """

    _STYLES = {
        "success": {"icon": "✓", "icon_color": "#27ae60", "icon_bg": "#e8f8f0", "title_color": "#27ae60"},
        "warning": {"icon": "!", "icon_color": "#e67e22", "icon_bg": "#fef3e2", "title_color": "#e67e22"},
        "error":   {"icon": "✕", "icon_color": "#e74c3c", "icon_bg": "#fde8e7", "title_color": "#e74c3c"},
        "info":    {"icon": "i", "icon_color": "#4A90D9", "icon_bg": "#e8f0fc", "title_color": "#4A90D9"},
    }

    def __init__(self, dialog_type: str = "info", title: str = "", message: str = "",
                 parent=None, width: int = 420):
        super().__init__(parent)
        s = self._STYLES.get(dialog_type, self._STYLES["info"])
        self._icon = s["icon"]
        self._icon_color = s["icon_color"]
        self._icon_bg = s["icon_bg"]
        self._title_color = s["title_color"]
        self._title_text = title
        self._message = message
        self._fixed_width = width

        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # 设置窗口图标
        icon_ico = RESOURCE_DIR / "gui" / "assets" / "icon.ico"
        icon_svg = RESOURCE_DIR / "gui" / "assets" / "icon.svg"
        if icon_ico.exists():
            self.setWindowIcon(QIcon(str(icon_ico)))
        elif icon_svg.exists():
            _set_svg_icon(self, icon_svg)

        self._build_ui()

        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(300)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _build_ui(self):
        container = QFrame()
        container.setObjectName("resultContainer")
        container.setStyleSheet("""
            QFrame#resultContainer {
                background-color: #ffffff;
                border: 1px solid #d0d5dd;
                border-radius: 16px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(container)

        inner = QVBoxLayout(container)
        inner.setContentsMargins(28, 24, 28, 20)
        inner.setSpacing(12)
        inner.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 图标（彩色圆形）
        icon_label = QLabel(self._icon)
        icon_label.setFixedSize(56, 56)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet(f"""
            QLabel {{
                background-color: {self._icon_bg};
                color: {self._icon_color};
                border-radius: 28px;
                font-size: 24pt;
                font-weight: bold;
                font-family: 'Segoe UI', 'Microsoft YaHei';
            }}
        """)
        inner.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignCenter)

        # 标题
        title_label = QLabel(self._title_text)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(f"color: {self._title_color}; font-size: 13pt; font-weight: bold; background: transparent;")
        inner.addWidget(title_label)

        # 消息内容
        msg_label = QLabel(self._message)
        msg_label.setWordWrap(True)
        msg_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        msg_label.setStyleSheet("color: #555555; font-size: 10pt; line-height: 1.6; background: transparent;")
        msg_label.setMinimumWidth(self._fixed_width - 80)
        inner.addWidget(msg_label)

        inner.addSpacing(4)

        # 关闭按钮
        btn_close = QPushButton("确定")
        btn_close.setObjectName("primary")
        btn_close.setFixedWidth(120)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._title_color};
                color: #ffffff;
                font-weight: bold;
                border: none;
                padding: 8px 20px;
                font-size: 10pt;
                border-radius: 8px;
            }}
            QPushButton:hover {{ opacity: 0.85; }}
        """)
        btn_close.clicked.connect(self.accept)
        inner.addWidget(btn_close, 0, Qt.AlignmentFlag.AlignCenter)

        self.setFixedWidth(self._fixed_width)
        self.adjustSize()

    def showEvent(self, event):
        super().showEvent(event)
        self._anim.start()

    @staticmethod
    def success(parent=None, title: str = "成功", message: str = "", width: int = 420) -> int:
        dlg = ResultDialog("success", title, message, parent, width)
        return dlg.exec()

    @staticmethod
    def warning(parent=None, title: str = "警告", message: str = "", width: int = 420) -> int:
        dlg = ResultDialog("warning", title, message, parent, width)
        return dlg.exec()

    @staticmethod
    def error(parent=None, title: str = "错误", message: str = "", width: int = 420) -> int:
        dlg = ResultDialog("error", title, message, parent, width)
        return dlg.exec()

    @staticmethod
    def info(parent=None, title: str = "提示", message: str = "", width: int = 420) -> int:
        dlg = ResultDialog("info", title, message, parent, width)
        return dlg.exec()


class LogDialog(QDialog):
    """日志查看弹窗 — 点击按钮后弹出。"""

    def __init__(self, log_widget: LogWidget, parent=None):
        super().__init__(parent)
        self.setWindowTitle("运行日志")
        self.resize(640, 480)
        self.setMinimumSize(560, 360)
        self.setStyleSheet(DIALOG_QSS)

        # 设置窗口图标
        icon_ico = RESOURCE_DIR / "gui" / "assets" / "icon.ico"
        icon_svg = RESOURCE_DIR / "gui" / "assets" / "icon.svg"
        if icon_ico.exists():
            self.setWindowIcon(QIcon(str(icon_ico)))
        elif icon_svg.exists():
            _set_svg_icon(self, icon_svg)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        # 标题行
        title_row = QHBoxLayout()
        title = QLabel("📋 运行日志")
        title.setObjectName("title")
        title_row.addWidget(title)
        title_row.addStretch()
        btn_clear = QPushButton("清空")
        btn_clear.setObjectName("secondary")
        btn_clear.clicked.connect(log_widget.clear)
        title_row.addWidget(btn_clear)
        layout.addLayout(title_row)

        # 将外部 LogWidget 移入弹窗
        if log_widget.parent():
            log_widget.setParent(None)
        log_widget.setStyleSheet("""
            QTextEdit {
                background-color: #fafafa;
                border: 1px solid #d0d5dd;
                border-radius: 8px;
                padding: 8px;
                color: #333333;
                font-family: Consolas, 'Microsoft YaHei';
                font-size: 9pt;
            }
        """)
        log_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        log_widget.setMinimumHeight(200)
        log_widget.setVisible(True)
        log_widget.show()
        layout.addWidget(log_widget)

        # 关闭按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.setObjectName("primary")
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        # 淡入动效
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(250)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def showEvent(self, event):
        super().showEvent(event)
        self._anim.start()


class AboutDialog(QDialog):
    """关于弹窗 — 软件信息 + 作者信息，带动效。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于")
        self.setFixedSize(380, 440)
        self.setStyleSheet(DIALOG_QSS)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # 设置窗口图标
        icon_ico = RESOURCE_DIR / "gui" / "assets" / "icon.ico"
        icon_svg = RESOURCE_DIR / "gui" / "assets" / "icon.svg"
        if icon_ico.exists():
            self.setWindowIcon(QIcon(str(icon_ico)))
        elif icon_svg.exists():
            _set_svg_icon(self, icon_svg)

        self._build_ui()

        # 淡入动效
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(300)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _build_ui(self):
        container = QFrame()
        container.setObjectName("aboutContainer")
        container.setStyleSheet("""
            QFrame#aboutContainer {
                background-color: #ffffff;
                border: 1px solid #d0d5dd;
                border-radius: 16px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(container)

        inner = QVBoxLayout(container)
        inner.setContentsMargins(28, 28, 28, 22)
        inner.setSpacing(10)

        # 图标
        icon_path = str(RESOURCE_DIR / "gui" / "assets" / "icon.svg")
        renderer = QSvgRenderer(icon_path)
        if renderer.isValid():
            pm = QPixmap(72, 72)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            renderer.render(p)
            p.end()
            icon_label = QLabel()
            icon_label.setPixmap(pm)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inner.addWidget(icon_label)

        # 软件名称
        name = QLabel("OpenCore 安全启动工具")
        name.setObjectName("title")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner.addWidget(name)

        # 版本
        ver = QLabel("v1.0")
        ver.setStyleSheet("color: #999999; font-size: 9pt;")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner.addWidget(ver)

        # 分隔线
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #e0e5dd; margin: 4px 0;")
        inner.addWidget(sep)

        # 作者信息
        author_title = QLabel("作者")
        author_title.setStyleSheet("color: #4A90D9; font-size: 9pt; font-weight: bold;")
        inner.addWidget(author_title)

        author = QLabel("余生的客栈")
        author.setStyleSheet("color: #333333; font-size: 10pt;")
        inner.addWidget(author)

        # Bilibili
        bili_title = QLabel("Bilibili")
        bili_title.setStyleSheet("color: #4A90D9; font-size: 9pt; font-weight: bold;")
        inner.addWidget(bili_title)

        bili = QLabel("@余生的客栈")
        bili.setStyleSheet("color: #333333; font-size: 10pt;")
        inner.addWidget(bili)

        # 网站
        site_title = QLabel("网站")
        site_title.setStyleSheet("color: #4A90D9; font-size: 9pt; font-weight: bold;")
        inner.addWidget(site_title)

        site = QLabel("yskz.cn")
        site.setStyleSheet("color: #4A90D9; font-size: 10pt; text-decoration: underline;")
        inner.addWidget(site)

        inner.addStretch()

        # 关闭按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.setObjectName("primary")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        inner.addLayout(btn_row)

    def showEvent(self, event):
        super().showEvent(event)
        self._anim.start()
