<div align="center">

# OpenCore 安全启动工具

# OpenCore Secure Boot Tool

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-blue.svg)](https://developer.microsoft.com/windows)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![GUI: PyQt6](https://img.shields.io/badge/GUI-PyQt6-41CD52.svg)](https://www.riverbankcomputing.com/software/pyqt/)

UEFI Secure Boot 证书管理与 EFI 签名工具，专为 OpenCore 引导方案设计

A UEFI Secure Boot certificate management and EFI signing tool designed for OpenCore boot configurations

</div>

---

## 目录 / Table of Contents

- [功能概览 / Features](#功能概览--features)
- [运行环境 / Requirements](#运行环境--requirements)
- [安装步骤 / Installation](#安装步骤--installation)
- [使用方法 / Usage](#使用方法--usage)
- [项目结构 / Project Structure](#项目结构--project-structure)
- [核心模块 / Core Modules](#核心模块--core-modules)
- [技术要点 / Technical Details](#技术要点--technical-details)
- [安全说明 / Security Notes](#安全说明--security-notes)
- [开发信息 / Development](#开发信息--development)
- [许可证 / License](#许可证--license)
- [致谢 / Credits](#致谢--credits)

---

## 功能概览 / Features

| 功能 / Feature | 说明 / Description |
|---|---|
| 密钥生成 / Key Generation | 生成 RSA-2048 的 PK / KEK / ISK 密钥对（有效期 10 年）<br>Generate RSA-2048 PK / KEK / ISK key pairs (10-year validity) |
| EFI 文件签名 / EFI Signing | 使用 ISK 密钥通过 sbsigntool 签名 .efi 文件，支持自动备份<br>Sign .efi files with ISK key via sbsigntool, with automatic backup |
| Windows 证书提取 / Windows Cert Extraction | 从 Windows EFI 启动文件中提取 Authenticode 签名证书（PKCS#7 解析）<br>Extract Authenticode signature certificates from Windows EFI boot files |
| 签名数据库构建 / Database Building | 构建 db / KEK / PK 的 ESL + P7 文件（含 Microsoft 证书和提取的证书）<br>Build ESL + P7 files for db / KEK / PK (includes Microsoft certs and extracted certs) |
| BIOS 证书导入 / BIOS Import | 通过 PowerShell `Set-SecureBootUEFI` 导入证书，自动识别 Setup Mode / User Mode<br>Import certificates via PowerShell `Set-SecureBootUEFI`, auto-detect Setup Mode / User Mode |
| 分区挂载 / Partition Mounting | 手动选择磁盘分区并挂载 EFI 系统分区，自动检测 OC 和 Windows 启动目录<br>Mount EFI system partition with manual disk/partition selection, auto-detect OC and Windows boot directories |
| 环境检测 / Environment Check | 启动时自动检测 WSL / sbsigntool / OpenSSL，缺失时提供一键安装<br>Auto-detect WSL / sbsigntool / OpenSSL at startup, with one-click install for missing components |
| config.plist 补丁 / config.plist Patcher | 签名时自动设置 `DisableSecurityPolicy=true`<br>Automatically set `DisableSecurityPolicy=true` during signing |

---

## 运行环境 / Requirements

### 必要依赖 / Prerequisites

| 依赖 / Dependency | 说明 / Description |
|---|---|
| **Windows 10/11** | 支持 UEFI Secure Boot / UEFI Secure Boot support required |
| **Python 3.10+** | 运行源码所需 / Required for running from source |
| **WSL** | Windows Subsystem for Linux，推荐 Ubuntu / Recommended: Ubuntu |
| **WSL 内工具 / WSL Tools** | `sbsigntool`、`efitools`、`openssl`、`uuid-runtime` |

### Python 依赖 / Python Dependencies

```
PyQt6>=6.5.0
cryptography>=41.0.0
```

---

## 安装步骤 / Installation

### 1. 安装 WSL / Install WSL

以管理员身份打开 PowerShell，运行 / Open PowerShell as Administrator and run:

```powershell
wsl --install
```

重启电脑后，WSL 会自动安装 Ubuntu / Reboot your computer, WSL will install Ubuntu automatically.

### 2. 安装 WSL 内工具 / Install WSL Tools

打开 WSL 终端，运行 / Open WSL terminal and run:

```bash
sudo apt-get update && sudo apt-get install -y sbsigntool efitools openssl uuid-runtime
```

> 也可在启动工具后，环境检测弹窗中点击「是」一键安装<br>Alternatively, click "Yes" in the environment check dialog when the tool starts

### 3. 安装 Python 依赖 / Install Python Dependencies

双击运行 `安装依赖.bat`，或在终端执行 / Double-click `安装依赖.bat`, or run:

```bash
pip install -r requirements.txt
```

---

## 使用方法 / Usage

### 启动 / Launch

双击 `启动工具.bat`（会自动请求管理员权限），或运行 / Double-click `启动工具.bat` (auto-elevates to admin), or run:

```bash
python main.py
```

### 操作流程 / Workflow

工具提供两种工作模式 / The tool provides two working modes:

**模式一：挂载引导分区 / Mode 1: Mount Boot Partition**

1. 选择磁盘和分区（EFI 系统分区） / Select disk and partition (EFI System Partition)
2. 点击「挂载」按钮挂载分区 / Click "Mount" to mount the partition
3. 工具自动检测 OC 目录和 Windows 启动目录 / Tool auto-detects OC and Windows boot directories
4. 勾选「签名前自动备份原始文件」 / Check "Auto-backup before signing"
5. 点击「签名 OC」对 OpenCore 的 EFI 文件签名 / Click "Sign OC" to sign OpenCore EFI files
6. 点击「提取 Win 证书」从 Windows 启动文件提取证书 / Click "Extract Win Certs" to extract certificates

**模式二：指定文件路径 / Mode 2: Specify File Paths**

1. 将 OC 文件夹拖入或浏览选择 / Drag-drop or browse for OC folder
2. 将 Windows 启动文件夹拖入或浏览选择 / Drag-drop or browse for Windows boot folder
3. 执行签名和证书提取 / Execute signing and certificate extraction

**证书构建与导入 / Certificate Building & Import**

1. 在「密钥管理」面板生成 PK / KEK / ISK 密钥 / Generate PK / KEK / ISK keys in "Key Management"
2. 在「证书构建」面板构建 db / KEK / PK 的 ESL + P7 文件 / Build ESL + P7 files in "Database Building"
3. 在「BIOS 导入」面板一键导入证书到 BIOS / One-click import to BIOS in "BIOS Import"
4. 导入完成后重启电脑，Secure Boot 即激活 / Reboot after import, Secure Boot will be activated

### BIOS 导入说明 / BIOS Import Notes

工具自动检测 BIOS 处于 Setup Mode 还是 User Mode / The tool auto-detects BIOS mode:

- **Setup Mode**（PK 为空 / PK is empty）：按 db → KEK → PK 顺序导入，导入 PK 后 Secure Boot 激活 / Import in db → KEK → PK order; Secure Boot activates after PK import
- **User Mode**（PK 已存在 / PK exists）：仅更新 db 和 KEK，PK 不可更改 / Only update db and KEK; PK cannot be changed (reset to Setup Mode in BIOS to change PK)

---

## 项目结构 / Project Structure

```
OpenCore安全启动工具/
├── main.py                    # 程序入口，管理员权限检测 / Entry point, admin privilege check
├── build_exe.py               # PyInstaller 打包脚本 / PyInstaller build script
├── requirements.txt           # Python 依赖清单 / Python dependencies
├── 启动工具.bat                # Windows 启动脚本（自动提权）/ Windows launcher (auto-elevate)
├── 安装依赖.bat                # Python 依赖安装脚本 / Python dependency installer
│
├── core/                      # 核心业务逻辑 / Core business logic
│   ├── config.py              # 路径配置与全局常量 / Path config & global constants
│   ├── key_manager.py         # PK/KEK/ISK 密钥生成 / Key generation
│   ├── signer.py              # EFI 文件签名 / EFI file signing
│   ├── cert_extractor.py      # PE 文件证书提取 / PE certificate extraction
│   ├── db_builder.py          # ESL/P7 签名数据库构建 / ESL/P7 database building
│   ├── bios_import.py         # BIOS 证书导入 / BIOS certificate import
│   ├── config_patcher.py      # config.plist 补丁 / config.plist patcher
│   ├── partition_utils.py     # 磁盘分区检测与挂载 / Disk partition detection & mounting
│   └── wsl_utils.py           # WSL 命令执行 / WSL command execution
│
├── gui/                       # GUI 界面 / GUI interface
│   ├── main_window.py         # 主窗口布局与事件 / Main window layout & events
│   ├── styles.py              # QSS 样式表 / QSS stylesheets
│   ├── widgets.py             # 自定义组件 / Custom widgets
│   ├── workers.py             # 后台线程 / Background worker threads
│   ├── dialogs.py             # 弹窗 / Dialogs
│   └── assets/
│       ├── icon.svg           # 应用图标 / App icon
│       └── check.svg          # 复选框图标 / Checkbox icon
│
├── keys/                      # 密钥文件目录（自动生成）/ Keys directory (auto-generated)
├── certs/                     # 证书输出目录（自动生成）/ Certificates (auto-generated)
└── extracted/                 # 提取的证书目录（自动生成）/ Extracted certs (auto-generated)
```

---

## 核心模块 / Core Modules

### core/wsl_utils.py

WSL 命令执行的核心模块 / Core module for WSL interaction:

| 函数 / Function | 说明 / Description |
|---|---|
| `run_wsl(cmd, timeout)` | 在 WSL 中执行 bash 命令 / Execute bash command in WSL |
| `win_to_wsl_path(path)` | Windows 路径转 WSL 路径 / Convert Windows path to WSL path |
| `check_wsl_available()` | 检测 WSL 是否可用 / Check if WSL is available |
| `check_sbsigntool()` | 检测 sbsigntool + efitools / Check sbsigntool + efitools |
| `check_openssl()` | 检测 OpenSSL 是否可用 / Check if OpenSSL is available |
| `install_dependencies()` | 一键安装 WSL 内依赖 / One-click install dependencies |

### core/key_manager.py

密钥管理器，使用 OpenSSL 生成三组 RSA-2048 密钥对 / Key manager, generates three RSA-2048 key pairs using OpenSSL:

- **PK**（Platform Key）— 平台密钥，Secure Boot 的根证书 / Platform Key, root certificate of Secure Boot
- **KEK**（Key Exchange Key）— 密钥交换密钥，用于签名 db / Key Exchange Key, used to sign db
- **ISK**（Image Signing Key）— 镜像签名密钥，用于签名 EFI 文件 / Image Signing Key, used to sign EFI files

### core/signer.py

EFI 文件签名器，通过 WSL 调用 `sbsign` 和 `sbverify` / EFI signer, calls `sbsign` and `sbverify` via WSL:

- 递归查找目录下所有 `.efi` 文件 / Recursively find all `.efi` files
- 签名前自动备份原始文件到 `_backup_YYYYMMDD_HHMMSS` 目录 / Auto-backup to timestamped directory
- 签名后使用 `sbverify` 验证签名有效性 / Verify signature with `sbverify`

### core/cert_extractor.py

证书提取器，从 Windows EFI 文件的 Authenticode 签名中提取 X.509 证书 / Certificate extractor, extracts X.509 certificates from Authenticode signatures:

- 解析 PE 文件头定位证书表 / Parse PE file header to locate certificate table
- 解析 PKCS#7 SignedData 提取嵌入证书 / Parse PKCS#7 SignedData to extract embedded certificates
- 按指纹去重并保存为 `.crt` 文件 / Deduplicate by fingerprint, save as `.crt`

### core/db_builder.py

签名数据库构建器，使用 efitools 的 `cert-to-efi-sig-list` 和 `sign-efi-sig-list` / Database builder using efitools:

- **db** = ISK + Microsoft 证书（WinUEFICA2023、MicWinProPCA2011、MicCorUEFCA2011）+ 提取的 Windows 证书 / ISK + Microsoft certs + extracted Windows certs
- **KEK** = KEK 公钥证书 / KEK public key certificate
- **PK** = PK 公钥证书 / PK public key certificate
- 每个变量生成 `.esl`（EFI Signature List）和 `.p7`（签名后的 P7 包）/ Each variable generates `.esl` and `.p7` files

### core/config_patcher.py

config.plist 补丁器，在签名过程中自动修改 OpenCore 配置 / config.plist patcher, automatically modifies OpenCore config during signing:

- 设置 `DisableSecurityPolicy=true`（UEFI → Quirks）/ Set `DisableSecurityPolicy=true` (UEFI → Quirks)
- 签名前自动备份原始 config.plist / Auto-backup original config.plist before patching

---

## 技术要点 / Technical Details

### 签名流程 / Signing Flow

```
ISK 密钥生成 / Key Generation (OpenSSL)
       │
       ▼
sbsign --key ISK.key --cert ISK.pem --output file.efi file.efi
       │
       ▼
sbverify --cert ISK.pem file.efi  (验证 / Verify)
```

### 证书数据库结构 / Certificate Database Structure

```
db.esl (签名数据库 / Signature Database)
  ├── ISK 证书 / ISK Certificate (OpenCore 自签名 / Self-signed)
  ├── Microsoft Windows Production PCA 2011
  ├── Microsoft UEFI CA 2011
  ├── Windows UEFI CA 2023
  └── 从 Windows EFI 文件提取的证书 / Extracted from Windows EFI files
         ↓ sign-efi-sig-list
db.p7 (KEK 签名的 P7 包 / KEK-signed P7 package)

KEK.esl → KEK.p7 (PK 签名 / PK-signed)
PK.esl  → PK.p7  (PK 自签名 / PK self-signed)
```

### BIOS 导入顺序 / BIOS Import Order

```
Setup Mode (PK 为空 / PK is empty):
  db  → Set-SecureBootUEFI db  -ContentFilePath db.esl  -SignedFilePath db.p7
  KEK → Set-SecureBootUEFI KEK -ContentFilePath KEK.esl -SignedFilePath KEK.p7
  PK  → Set-SecureBootUEFI PK  -ContentFilePath PK.esl  -SignedFilePath PK.p7
         ↑ 导入 PK 后 Secure Boot 激活 / Secure Boot activates after PK import
```

---

## 安全说明 / Security Notes

- `keys/` 目录包含私钥文件（`.key`），切勿上传到公开仓库 / The `keys/` directory contains private keys (`.key`), never upload to public repositories
- `.gitignore` 已配置忽略密钥和证书文件 / `.gitignore` is configured to exclude keys and certificates
- PK 导入后 BIOS 将锁定，修改需在 BIOS 中重置为 Setup Mode / After PK import, BIOS locks; to modify, reset to Setup Mode in BIOS
- 建议在操作前备份现有 BIOS Secure Boot 配置 / Recommend backing up existing BIOS Secure Boot configuration before proceeding
- 使用本工具修改 BIOS Secure Boot 配置可能导致系统无法启动，请确保了解相关风险 / Modifying BIOS Secure Boot configuration may cause boot failure; ensure you understand the risks

---

## 开发信息 / Development

| 项目 / Item | 说明 / Description |
|---|---|
| GUI 框架 / GUI Framework | PyQt6 |
| 线程模型 / Threading Model | QThread 子类化，所有耗时操作在后台线程执行 / QThread subclassing, all heavy operations in background threads |
| 样式系统 / Styling | QSS（Qt Style Sheets），集中管理于 `gui/styles.py` / QSS, centralized in `gui/styles.py` |
| 架构 / Architecture | core/（业务逻辑）与 gui/（界面）完全分离 / core/ (business logic) and gui/ (UI) fully separated |
| 打包 / Packaging | PyInstaller 单文件 EXE / PyInstaller single-file EXE |

### 从源码构建 / Build from Source

```bash
# 安装依赖 / Install dependencies
pip install -r requirements.txt

# 打包为 EXE / Package as EXE
python build_exe.py
```

---

## 许可证 / License

本项目基于 [MIT 许可证](LICENSE) 开源 / This project is licensed under the [MIT License](LICENSE).

```
MIT License

Copyright (c) 2026 余生的客栈 (yskz.cn) @bilibli&余生的客栈

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 致谢 / Credits

- **作者 / Author**: [余生的客栈@bilibili](https://space.bilibili.com/) | [yskz.cn](https://yskz.cn)
- **技术栈 / Tech Stack**: PyQt6, PyInstaller, WSL, sbsigntool, efitools, OpenSSL
- **灵感来源 / Inspired by**: [OpenCore-and-UEFI-Secure-Boot]([https://github.com/acidanthera/OpenCorePkg](https://github.com/perez987/OpenCore-and-UEFI-Secure-Boot/tree/main)) 

---

<div align="center">

如果这个项目对你有帮助，请考虑给个 Star / If this project helps you, please consider giving it a Star

</div>
