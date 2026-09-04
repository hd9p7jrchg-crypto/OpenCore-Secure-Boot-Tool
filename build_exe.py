"""
OpenCore 安全启动工具 (OpenCore Secure Boot Tool) — 打包脚本
1. 将 SVG 图标转为 ICO
2. 使用 PyInstaller 打包为单文件 exe
"""
import os
import sys
import subprocess
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).parent


def svg_to_ico(svg_path: str, ico_path: str):
    """将 SVG 渲染为多尺寸 ICO（使用临时 PNG 文件中转）"""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtSvg import QSvgRenderer
    from PyQt6.QtGui import QPixmap, QPainter
    from PyQt6.QtCore import Qt
    from PIL import Image

    print("[1/2] 转换 SVG -> ICO ...")
    # QSvgRenderer 需要 QApplication 实例
    app = QApplication.instance() or QApplication(sys.argv)
    renderer = QSvgRenderer(svg_path)
    if not renderer.isValid():
        print(f"  错误：无法加载 SVG ({svg_path})")
        sys.exit(1)

    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    images = []
    tmp_dir = Path(tempfile.mkdtemp())

    try:
        for i, (w, h) in enumerate(sizes):
            pm = QPixmap(w, h)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            renderer.render(p)
            p.end()
            # 保存到临时 PNG 文件，再用 Pillow 打开
            png_path = str(tmp_dir / f"icon_{i}.png")
            pm.toImage().save(png_path, "PNG")
            img = Image.open(png_path).convert("RGBA")
            images.append(img)

        images[0].save(ico_path, format="ICO", sizes=sizes, append_images=images[1:])
        print(f"  ICO 已保存：{ico_path}")

        # 同时保存到 gui/assets/ 供打包后运行时加载
        assets_ico = APP_DIR / "gui" / "assets" / "icon.ico"
        images[0].save(str(assets_ico), format="ICO", sizes=sizes, append_images=images[1:])
        print(f"  ICO 副本已保存：{assets_ico}")
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_pyinstaller(ico_path: str):
    """运行 PyInstaller"""
    print("\n[2/2] 运行 PyInstaller 打包 ...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "OpenCore安全启动工具",
        "--add-data", f"gui/assets{os.pathsep}gui/assets",
        "--icon", ico_path,
        "--hidden-import", "PyQt6.QtSvg",
        "--hidden-import", "PyQt6.QtSvgWidgets",
        "--noconfirm",
        "--clean",
        "main.py",
    ]
    print(f"  命令：{' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(APP_DIR))
    if result.returncode != 0:
        print("\n打包失败！请检查上面的错误信息。")
        sys.exit(1)
    exe_path = APP_DIR / "dist" / "OpenCore安全启动工具.exe"
    print(f"\n打包完成！")
    print(f"  输出文件：{exe_path}")
    print(f"  文件大小：{exe_path.stat().st_size / 1024 / 1024:.1f} MB")
    return exe_path


if __name__ == "__main__":
    svg = str(APP_DIR / "gui" / "assets" / "icon.svg")
    ico = str(APP_DIR / "icon.ico")

    svg_to_ico(svg, ico)
    exe = run_pyinstaller(ico)

    # 清理临时文件
    spec = APP_DIR / "OpenCore安全启动工具.spec"
    if spec.exists():
        spec.unlink()
    build_dir = APP_DIR / "build"
    if build_dir.exists():
        import shutil
        shutil.rmtree(build_dir)
    if Path(ico).exists():
        Path(ico).unlink()

    print("\n临时文件已清理。")
