"""
Audit Coworker — single-file launcher.

When frozen by PyInstaller the embedded uvicorn serves both the API
and the pre-built frontend.  When run from source it behaves the same
as ``uvicorn app.main:app`` inside the backend/ folder.
"""

import os
import sys
import traceback
import webbrowser
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# Explicit imports so PyInstaller's Analysis can trace them.
# These are the top-level packages used by backend/app at runtime.
# ---------------------------------------------------------------------------
import fastapi             # noqa: F401
import starlette           # noqa: F401
import sqlalchemy          # noqa: F401
import pydantic            # noqa: F401
import pydantic_settings   # noqa: F401
import uvicorn             # noqa: F401
import aiosqlite           # noqa: F401
import httpx               # noqa: F401
import apscheduler         # noqa: F401
import sse_starlette       # noqa: F401
import loguru              # noqa: F401
import orjson              # noqa: F401
import dotenv              # noqa: F401
import multipart           # noqa: F401
import anyio               # noqa: F401
import h11                 # noqa: F401
import sniffio             # noqa: F401


def _get_data_dir() -> Path:
    """
    Writable directory that holds the SQLite database and .env overrides.
    - Frozen (exe): same folder as the exe  (portable)
    - Development:   backend/
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent / "backend"


def _bootstrap_env() -> None:
    data_dir = _get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    env_file = data_dir / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)

    db_path = data_dir / "audit_coworker.db"
    os.environ.setdefault(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
    )

    if getattr(sys, "frozen", False):
        os.environ.setdefault("LOG_LEVEL", "WARNING")


def _open_browser(port: int) -> None:
    """Open the default browser after a short delay."""
    import time
    time.sleep(2.0)
    webbrowser.open(f"http://127.0.0.1:{port}")


def main() -> None:
    _bootstrap_env()

    if getattr(sys, "frozen", False):
        bundle_dir = getattr(sys, "_MEIPASS", "")
        sys.path.insert(0, os.path.join(bundle_dir, "backend"))
        os.chdir(bundle_dir)

    port = int(os.environ.get("PORT", "8000"))

    threading.Thread(target=_open_browser, args=(port,), daemon=True).start()

    print(f"Audit Coworker is starting on http://127.0.0.1:{port} ...")
    print("(关闭此窗口将停止服务)")
    print()
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=port,
        log_level="warning" if getattr(sys, "frozen", False) else "info",
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        print()
        print("=" * 50)
        print("  程序启动失败，请查看上方错误信息。")
        print("=" * 50)
        input("按回车键退出 ...")
