# Audit Coworker — 打包与安装指南

## 概览

本项目支持两种分发方式：

| 方式 | 输出 | 适用场景 |
|------|------|----------|
| **便携版** | `dist/AuditCoworker/` 文件夹 | 直接复制到目标机器运行 |
| **安装程序** | `AuditCoworker_Setup_x.x.x.exe` | 带桌面快捷方式的 Windows 安装包 |

---

## 前置依赖（打包机器需要）

| 工具 | 版本 | 用途 |
|------|------|------|
| **Python** | >= 3.12 | 后端运行时 + PyInstaller |
| **Node.js** | >= 20 LTS | 前端构建 |
| **PyInstaller** | latest | Python 打包（build.bat 会自动安装） |
| **Inno Setup** *(可选)* | >= 6.0 | 生成 Windows 安装程序 |

---

## 一键打包

```bat
build.bat
```

脚本会自动执行以下步骤：
1. 构建前端（`npm install` + `npm run build`）→ `frontend/dist/`
2. 安装后端 Python 依赖
3. 使用 PyInstaller 打包 → `dist/AuditCoworker/`

打包完成后 `dist/AuditCoworker/` 可以直接压缩为 zip 分发。

---

## 生成 Windows 安装程序（可选）

1. 安装 [Inno Setup](https://jrsoftware.org/isinfo.php)
2. 打开 `installer.iss`
3. 点击 **Build → Compile**（或按 Ctrl+F9）
4. 输出文件位于 `installer_output/AuditCoworker_Setup_1.0.0.exe`

---

## 目标机器上使用

### 便携版

1. 将 `dist/AuditCoworker/` 文件夹拷贝到目标电脑
2. 双击 `AuditCoworker.exe`
3. 程序启动后会自动打开浏览器访问 `http://127.0.0.1:8000`

### 安装版

1. 运行 `AuditCoworker_Setup_1.0.0.exe`
2. 按向导安装
3. 从桌面快捷方式或开始菜单启动

### 数据存储

- SQLite 数据库 `audit_coworker.db` 保存在 exe 同级目录下
- 可在 exe 同级目录放置 `.env` 文件覆盖配置项

### 可配置的环境变量（.env）

```env
DATABASE_URL=sqlite+aiosqlite:///./audit_coworker.db
ENCRYPTION_KEY=your-32-byte-key-here
LOG_LEVEL=WARNING
PORT=8000
```

---

## 项目文件说明

| 文件 | 说明 |
|------|------|
| `run.py` | PyInstaller 入口 — 启动 uvicorn 并打开浏览器 |
| `audit_coworker.spec` | PyInstaller 打包配置 |
| `build.bat` | 一键打包脚本 |
| `installer.iss` | Inno Setup 安装程序脚本 |
| `start.bat` | 开发模式启动脚本（前后端分别运行） |
