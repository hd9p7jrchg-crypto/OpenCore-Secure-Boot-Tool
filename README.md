# OpenCore 安全启动工具 (OpenCore Secure Boot Tool)

基于 PyQt6 开发的 UEFI Secure Boot 证书管理与 EFI 签名工具，专为 OpenCore 引导方案设计。支持密钥生成、EFI 文件签名、Windows 证书提取、签名数据库构建、BIOS 证书导入全流程操作。

## 功能概览

| 功能 | 说明 |
|------|------|
| 密钥生成 | 生成 RSA-2048 的 PK / KEK / ISK 密钥对（有效期 10 年） |
| EFI 文件签名 | 使用 ISK 密钥通过 sbsigntool 签名 .efi 文件，支持自动备份原始文件 |
| Windows 证书提取 | 从 Windows EFI 启动文件中提取 Authenticode 签名证书（PKCS#7 解析） |
| 签名数据库构建 | 构建 db / KEK / PK 的 ESL + P7 文件（含 Microsoft 证书和提取的证书） |
| BIOS 证书导入 | 通过 PowerShell `Set-SecureBootUEFI` 导入证书，自动识别 Setup Mode / User Mode |
| 分区挂载 | 手动选择磁盘分区并挂载 EFI 系统分区，自动检测 OC 和 Windows 启动目录 |
| 环境检测 | 启动时自动检测 WSL / sbsigntool / OpenSSL，缺失时提供一键安装 |

## 运行环境

### 必要依赖

- **Windows 10/11**（支持 UEFI Secure Boot）
- **Python 3.10+**
- **WSL**（Windows Subsystem for Linux，推荐 Ubuntu）
- **WSL 内工具**：`sbsigntool`、`efitools`、`openssl`、`uuid-runtime`

### Python 依赖

```
PyQt6>=6.5.0
cryptography>=41.0.0
```

## 安装步骤

### 1. 安装 WSL

以管理员身份打开 PowerShell，运行：

```powershell
wsl --install
```

重启电脑后，WSL 会自动安装 Ubuntu。

### 2. 安装 WSL 内工具

打开 WSL 终端，运行：

```bash
sudo apt-get update && sudo apt-get install -y sbsigntool efitools openssl uuid-runtime
```

> 也可在启动工具后，环境检测弹窗中点击"是"一键安装。

### 3. 安装 Python 依赖

双击运行 `安装依赖.bat`，或在终端执行：

```bash
pip install -r requirements.txt
```

## 使用方法

### 启动

双击 `启动工具.bat`（会自动请求管理员权限），或运行：

```bash
python main.py
```

### 操作流程

工具提供两种工作模式：

**模式一：挂载引导分区**
1. 选择磁盘和分区（EFI 系统分区）
2. 点击"挂载"按钮挂载分区
3. 工具自动检测 OC 目录和 Windows 启动目录
4. 勾选"签名前自动备份原始文件"
5. 点击"签名 OC"对 OpenCore 的 EFI 文件签名
6. 点击"提取 Win 证书"从 Windows 启动文件提取证书

**模式二：指定文件路径**
1. 将 OC 文件夹拖入或浏览选择
2. 将 Windows 启动文件夹拖入或浏览选择
3. 执行签名和证书提取

**证书构建与导入**
1. 在"密钥管理"面板生成 PK / KEK / ISK 密钥
2. 在"证书构建"面板构建 db / KEK / PK 的 ESL + P7 文件
3. 在"BIOS 导入"面板一键导入证书到 BIOS
4. 导入完成后重启电脑，Secure Boot 即激活

### BIOS 导入说明

工具自动检测 BIOS 处于 Setup Mode 还是 User Mode：

- **Setup Mode**（PK 为空）：按 db → KEK → PK 顺序导入，导入 PK 后 Secure Boot 激活
- **User Mode**（PK 已存在）：仅更新 db 和 KEK，PK 不可更改（需在 BIOS 中重置为 Setup Mode）

## 项目结构

```
OpenCore安全启动工具/
├── main.py                    # 程序入口，管理员权限检测
├── requirements.txt           # Python 依赖清单
├── 启动工具.bat                # Windows 启动脚本（自动提权）
├── 安装依赖.bat                # Python 依赖安装脚本
│
├── core/                      # 核心业务逻辑
│   ├── config.py              # 路径配置与全局常量
│   ├── key_manager.py         # PK/KEK/ISK 密钥生成与管理
│   ├── signer.py              # EFI 文件签名（sbsigntool）
│   ├── cert_extractor.py      # PE 文件 Authenticode 证书提取
│   ├── db_builder.py          # ESL/P7 签名数据库构建
│   ├── bios_import.py         # BIOS Secure Boot 证书导入
│   ├── partition_utils.py     # 磁盘分区检测与挂载
│   └── wsl_utils.py           # WSL 命令执行与路径转换
│
├── gui/                       # GUI 界面
│   ├── main_window.py         # 主窗口布局与事件逻辑
│   ├── styles.py              # QSS 样式表（白色主题）
│   ├── widgets.py             # 自定义组件（DropFrame/LogWidget）
│   ├── workers.py             # 后台线程（签名/提取/构建/导入/挂载/安装）
│   ├── dialogs.py             # 弹窗（管理员确认/日志查看）
│   └── assets/
│       └── check.svg           # 复选框勾选图标
│
├── keys/                      # 密钥文件目录（自动生成）
├── certs/                     # 证书输出目录（自动生成）
└── extracted/                 # 提取的证书目录（自动生成）
```

## 核心模块说明

### core/wsl_utils.py

WSL 命令执行的核心模块，所有与 WSL 的交互都通过此模块：

- `run_wsl(cmd, timeout)` — 在 WSL 中执行 bash 命令
- `win_to_wsl_path(path)` — Windows 路径转 WSL 路径（`C:\Users` → `/mnt/c/Users`）
- `check_wsl_available()` — 检测 WSL 是否可用
- `check_sbsigntool()` — 检测 sbsigntool + efitools 是否安装
- `check_openssl()` — 检测 OpenSSL 是否可用
- `install_dependencies()` — 一键安装 WSL 内依赖

### core/key_manager.py

密钥管理器，使用 OpenSSL 生成三组 RSA-2048 密钥对：

- **PK**（Platform Key）— 平台密钥，Secure Boot 的根证书
- **KEK**（Key Exchange Key）— 密钥交换密钥，用于签名 db
- **ISK**（Image Signing Key）— 镜像签名密钥，用于签名 EFI 文件

### core/signer.py

EFI 文件签名器，通过 WSL 调用 `sbsign` 和 `sbverify`：

- 递归查找目录下所有 `.efi` 文件
- 签名前自动备份原始文件到 `_backup_YYYYMMDD_HHMMSS` 目录
- 签名后使用 `sbverify` 验证签名有效性

### core/cert_extractor.py

证书提取器，从 Windows EFI 文件的 Authenticode 签名中提取 X.509 证书：

- 解析 PE 文件头定位证书表
- 解析 PKCS#7 SignedData 提取嵌入证书
- 按指纹去重并保存为 `.crt` 文件

### core/db_builder.py

签名数据库构建器，使用 efitools 的 `cert-to-efi-sig-list` 和 `sign-efi-sig-list`：

- **db** = ISK + Microsoft 证书（WinUEFICA2023、MicWinProPCA2011、MicCorUEFCA2011）+ 提取的 Windows 证书
- **KEK** = KEK 公钥证书
- **PK** = PK 公钥证书
- 每个变量生成 `.esl`（EFI Signature List）和 `.p7`（签名后的 P7 包）

### core/bios_import.py

BIOS 证书导入器，通过 PowerShell `Set-SecureBootUEFI` 写入 UEFI 变量：

- 自动检测 Setup Mode / User Mode
- Setup Mode：导入 db → KEK → PK（PK 锁定 Secure Boot）
- User Mode：仅更新 db 和 KEK

### core/partition_utils.py

磁盘分区管理，通过 PowerShell `Get-Disk` / `Get-Partition` / `Add-PartitionAccessPath` 操作：

- 列出所有物理磁盘和分区
- 手动挂载指定分区并分配盘符
- 自动检测挂载分区中的 OC 和 Windows 启动目录

## 技术要点

### 签名流程

```
ISK 密钥生成 (OpenSSL)
       │
       ▼
sbsign --key ISK.key --cert ISK.pem --output file.efi file.efi
       │
       ▼
sbverify --cert ISK.pem file.efi  (验证)
```

### 证书数据库结构

```
db.esl (签名数据库)
  ├── ISK 证书 (OpenCore 自签名)
  ├── Microsoft Windows Production PCA 2011
  ├── Microsoft UEFI CA 2011
  ├── Windows UEFI CA 2023
  └── 从 Windows EFI 文件提取的证书
         ↓ sign-efi-sig-list
db.p7 (KEK 签名的 P7 包)

KEK.esl → KEK.p7 (PK 签名)
PK.esl  → PK.p7  (PK 自签名)
```

### BIOS 导入顺序

```
Setup Mode (PK 为空):
  db  → Set-SecureBootUEFI db  -ContentFilePath db.esl  -SignedFilePath db.p7
  KEK → Set-SecureBootUEFI KEK -ContentFilePath KEK.esl -SignedFilePath KEK.p7
  PK  → Set-SecureBootUEFI PK  -ContentFilePath PK.esl  -SignedFilePath PK.p7
         ↑ 导入 PK 后 Secure Boot 激活
```

## 安全说明

- `keys/` 目录包含私钥文件（`.key`），切勿上传到公开仓库
- `.gitignore` 已配置忽略密钥和证书文件
- PK 导入后 BIOS 将锁定，修改需在 BIOS 中重置为 Setup Mode
- 建议在操作前备份现有 BIOS Secure Boot 配置

## 开发信息

- **GUI 框架**：PyQt6
- **线程模型**：QThread 子类化，所有耗时操作在后台线程执行
- **样式系统**：QSS（Qt Style Sheets），集中管理于 `gui/styles.py`
- **架构**：core/（业务逻辑）与 gui/（界面）完全分离

## 许可证

本项目仅供学习和个人使用。使用本工具修改 BIOS Secure Boot 配置可能导致系统无法启动，请确保了解相关风险并做好备份。
