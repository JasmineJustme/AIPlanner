# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Audit Coworker.

Usage:
    pyinstaller audit_coworker.spec
"""

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None
ROOT = os.path.abspath(".")

# Automatically collect all submodules for packages that use lazy/dynamic imports
hidden = []
for pkg in [
    "uvicorn",
    "fastapi",
    "starlette",
    "pydantic",
    "pydantic_core",
    "pydantic_settings",
    "sqlalchemy",
    "aiosqlite",
    "httpx",
    "httpcore",
    "apscheduler",
    "sse_starlette",
    "anyio",
    "h11",
    "sniffio",
    "orjson",
    "loguru",
    "dotenv",
    "multipart",
]:
    hidden += collect_submodules(pkg)

# Also grab data files that some packages ship (e.g. pydantic schemas, certifi certs)
extra_datas = []
for pkg in ["certifi", "httpcore", "httpx", "pydantic"]:
    try:
        extra_datas += collect_data_files(pkg)
    except Exception:
        pass

a = Analysis(
    ["run.py"],
    pathex=[os.path.join(ROOT, "backend")],
    binaries=[],
    datas=[
        # Bundle the entire backend application package (imported at runtime via sys.path)
        (os.path.join(ROOT, "backend", "app"), os.path.join("backend", "app")),
        # Bundle the pre-built frontend
        (os.path.join(ROOT, "frontend", "dist"), "frontend_dist"),
    ] + extra_datas,
    hiddenimports=hidden + [
        "encodings",
        "encodings.idna",
        "encodings.utf_8",
        "email.mime.text",
        "email.mime.multipart",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "cv2",
        "test",
        "unittest",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AuditCoworker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AuditCoworker",
)
