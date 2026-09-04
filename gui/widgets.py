"""
自定义组件 — DropFrame, LogWidget, LoadingOverlay
"""
from PyQt6.QtWidgets import QFrame, QTextEdit, QLabel, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRectF, QPointF
from PyQt6.QtGui import QFont, QColor, QDragEnterEvent, QDropEvent, QPainter, QPen, QBrush, QPaintEvent


class DropFrame(QFrame):
    """支持文件/文件夹拖拽的面板。"""
    dropped = pyqtSignal(str)

    def __init__(self, title: str, subtitle: str = "", color: str = "#4A90D9"):
        super().__init__()
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedHeight(64)
        self.color = color
        self._hover = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(1)

        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setStyleSheet(f"color: {color};")
        layout.addWidget(self.title_label)

        if subtitle:
            self.sub_label = QLabel(subtitle)
            self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sub_label.setStyleSheet("color: #999999; font-size: 8pt;")
            layout.addWidget(self.sub_label)

        self._update_style()

    def _update_style(self):
        if self._hover:
            self.setStyleSheet(f"""
                DropFrame {{
                    border: 2px dashed {self.color};
                    border-radius: 8px;
                    background-color: {self.color}15;
                }}
            """)
        else:
            self.setStyleSheet("""
                DropFrame {
                    border: 2px dashed #ccc;
                    border-radius: 8px;
                    background-color: #fafafa;
                }
            """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._hover = True
            self._update_style()

    def dragLeaveEvent(self, event):
        self._hover = False
        self._update_style()

    def dropEvent(self, event: QDropEvent):
        self._hover = False
        self._update_style()
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self.dropped.emit(path)


class LogWidget(QTextEdit):
    """日志输出组件，可嵌入弹窗或主界面。"""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 9))
        self.setStyleSheet("""
            QTextEdit {
                background-color: #fafafa;
                border: 1px solid #d0d5dd;
                border-radius: 6px;
                padding: 8px;
                color: #333333;
            }
        """)

    def log(self, message: str, color: str = "#333333"):
        self.setTextColor(QColor(color))
        self.append(message)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def info(self, message: str):
        self.log(f"[信息] {message}", "#4A90D9")

    def success(self, message: str):
        self.log(f"[成功] {message}", "#27ae60")

    def error(self, message: str):
        self.log(f"[失败] {message}", "#e74c3c")

    def warning(self, message: str):
        self.log(f"[警告] {message}", "#e67e22")


class LoadingOverlay(QWidget):
    """半透明加载遮罩 — 旋转圆环 + 消息文本。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.hide()

        self._angle = 0
        self._message = "正在处理..."

        # 动画定时器
        self._timer = QTimer(self)
        self._timer.setInterval(30)  # ~33fps
        self._timer.timeout.connect(self._on_tick)

        # 布局 — 用居中容器确保垂直水平双向居中
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # 弹性空间（顶部）— 将内容推到中间
        layout.addStretch(1)

        # spinner 区域（用 paintEvent 绘制）
        self._spinner_size = 56
        self._spinner_widget = QWidget()
        self._spinner_widget.setFixedSize(self._spinner_size + 20, self._spinner_size + 20)
        self._spinner_widget.paintEvent = self._paint_spinner
        layout.addWidget(self._spinner_widget, 0, Qt.AlignmentFlag.AlignCenter)

        # 消息文本
        self._msg_label = QLabel(self._message)
        self._msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._msg_label.setStyleSheet("color: #4A90D9; font-size: 10pt; font-weight: bold; background: transparent;")
        layout.addWidget(self._msg_label, 0, Qt.AlignmentFlag.AlignCenter)

        # 弹性空间（底部）— 将内容推到中间
        layout.addStretch(1)

    # -- public --
    def show_with_message(self, message: str = "正在处理..."):
        self._message = message
        self._msg_label.setText(message)
        self._resize_to_parent()
        self.raise_()
        self.show()
        self._timer.start()

    def update_message(self, message: str):
        self._message = message
        self._msg_label.setText(message)

    def hide_overlay(self):
        self._timer.stop()
        self.hide()

    # -- internal --
    def _resize_to_parent(self):
        if self.parent():
            self.setGeometry(self.parent().rect())

    def _on_tick(self):
        self._angle = (self._angle + 8) % 360
        self._spinner_widget.update()

    def _paint_spinner(self, event: QPaintEvent):
        p = QPainter(self._spinner_widget)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self._spinner_size
        cx = self._spinner_widget.width() / 2
        cy = self._spinner_widget.height() / 2
        rect = QRectF(cx - w / 2, cy - w / 2, w, w)

        # 背景圆
        p.setPen(QPen(QColor("#e0e5ee"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(rect, 0, 360 * 16)

        # 旋转弧段 — 渐变透明度
        n_segments = 8
        for i in range(n_segments):
            alpha = int(255 * (1.0 - i / n_segments))
            color = QColor(74, 144, 217, alpha)  # #4A90D9
            p.setPen(QPen(color, 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            start = (self._angle + i * 45) * 16
            p.drawArc(rect, -int(start), int(40 * 16))  # 每段 ~40°

        p.end()

    def paintEvent(self, event: QPaintEvent):
        """绘制半透明背景。"""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(255, 255, 255, 180))
        p.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
