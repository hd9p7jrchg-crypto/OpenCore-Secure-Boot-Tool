"""
OpenCore 安全启动工具 — 程序入口
基于 PyQt6 开发，模块化设计
"""
import sys
import os
import tempfile

# ===== 诊断日志：必须在所有其他 import 之前设置 =====
_DIAG_LOG = os.path.join(tempfile.gettempdir(), "sbt_diag.log")
try:
    _diag_fh = open(_DIAG_LOG, 'w', encoding='utf-8')
except Exception:
    _diag_fh = None

def _diag(msg):
    """写入诊断日志。"""
    if _diag_fh:
        try:
            _diag_fh.write(f"{msg}\n")
            _diag_fh.flush()
        except Exception:
            pass

def _excepthook(exc_type, exc_value, exc_tb):
    """捕获未处理的异常并写入日志 + 弹窗提示。"""
    import traceback
    _diag("\n=== 未捕获的异常 ===")
    if _diag_fh:
        traceback.print_exception(exc_type, exc_value, exc_tb, file=_diag_fh)
        _diag_fh.flush()
    # 尝试弹出错误对话框
    try:
        from PyQt6.QtWidgets import QMessageBox, QApplication
        if QApplication.instance() is None:
            app = QApplication(sys.argv)
        tb_short = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb)[-2:])
        msg = f"{exc_type.__name__}: {exc_value}\n\n{tb_short}\n\n完整日志：\n{_DIAG_LOG}"
        QMessageBox.critical(None, "启动错误", msg)
    except Exception:
        pass
    sys.exit(1)

sys.excepthook = _excepthook

# 重定向 stderr 到日志文件（fd 级别，捕获 C 层输出）
if _diag_fh:
    try:
        os.dup2(_diag_fh.fileno(), 2)
        sys.stderr = _diag_fh
    except Exception:
        pass

_diag(f"=== 进程启动 PID={os.getpid()} ===")
_diag(f"argv={sys.argv}")
_diag(f"executable={sys.executable}")
_diag(f"cwd={os.getcwd()}")

# ===== 正式导入 =====
try:
    from pathlib import Path
    _diag("import pathlib OK")

    if getattr(sys, 'frozen', False):
        APP_ROOT = Path(sys._MEIPASS)
        _diag(f"frozen mode, APP_ROOT={APP_ROOT}")
    else:
        APP_ROOT = Path(__file__).parent
        sys.path.insert(0, str(APP_ROOT))
        _diag(f"script mode, APP_ROOT={APP_ROOT}")
        _diag(f"sys.path[0]={sys.path[0]}")

    from PyQt6.QtWidgets import QApplication, QMessageBox
    _diag("import PyQt6.QtWidgets OK")

    from PyQt6.QtGui import QFont, QIcon
    _diag("import PyQt6.QtGui OK")

    from core.partition_utils import is_admin
    _diag("import core.partition_utils OK")

    from core.config import RESOURCE_DIR
    _diag(f"import core.config OK, RESOURCE_DIR={RESOURCE_DIR}")

    from gui.main_window import MainWindow
    _diag("import gui.main_window OK")

    from gui.dialogs import AdminConfirmDialog
    _diag("import gui.dialogs OK")

except Exception as e:
    import traceback
    _diag(f"\n=== 导入失败 ===")
    if _diag_fh:
        traceback.print_exc(file=_diag_fh)
        _diag_fh.flush()
    # 尝试用 ctypes 弹窗（不依赖 PyQt6）
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            f"导入模块失败：\n{e}\n\n完整日志：\n{_DIAG_LOG}",
            "启动错误",
            0x10  # MB_ICONERROR
        )
    except Exception:
        pass
    sys.exit(1)

_diag("所有模块导入完成，开始执行 main()")


def main():
    try:
        # Windows 任务栏图标分组
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("yskz.cn.OpenCoreSecureBootTool")
        _diag("AppUserModelID 已设置")

        # 解析 --signal 参数（用于非管理员进程检测本进程已就绪）
        signal_file = None
        argv = sys.argv[1:]
        i = 0
        while i < len(argv):
            if argv[i] == '--signal' and i + 1 < len(argv):
                signal_file = argv[i + 1]
                break
            i += 1
        _diag(f"signal_file={signal_file}")

        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        _diag("QApplication 已创建")

        font = QFont("Microsoft YaHei", 9)
        app.setFont(font)

        # 设置应用级图标
        icon_ico = RESOURCE_DIR / "gui" / "assets" / "icon.ico"
        icon_svg = RESOURCE_DIR / "gui" / "assets" / "icon.svg"
        if icon_ico.exists():
            app.setWindowIcon(QIcon(str(icon_ico)))
        elif icon_svg.exists():
            app.setWindowIcon(QIcon(str(icon_svg)))
        _diag("应用图标已设置")

        admin = is_admin()
        _diag(f"is_admin={admin}")

        if not admin:
            dlg = AdminConfirmDialog()
            choice = dlg.exec_and_get_choice()
            _diag(f"AdminConfirmDialog choice={choice}")

            if choice == "elevate":
                sys.exit(0)
            elif choice == "exit":
                sys.exit(0)
            else:
                admin = False
        else:
            admin = True

        _diag("开始创建 MainWindow...")
        window = MainWindow(admin_mode=admin)
        _diag("MainWindow 已创建")

        window.show()
        _diag("MainWindow 已 show")

        window.bring_to_front()
        _diag("bring_to_front 已调用")

        # 创建信号文件通知非管理员进程（本进程已就绪）
        if signal_file:
            try:
                Path(signal_file).touch()
                _diag(f"信号文件已创建: {signal_file}")
            except Exception as e:
                _diag(f"信号文件创建失败: {e}")

        _diag("进入事件循环")
        sys.exit(app.exec())

    except SystemExit:
        raise
    except Exception as e:
        import traceback
        _diag(f"\n=== main() 异常 ===")
        if _diag_fh:
            traceback.print_exc(file=_diag_fh)
            _diag_fh.flush()
        try:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "运行错误", f"{e}\n\n完整日志：\n{_DIAG_LOG}")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
