@echo off
echo 启动后端 (端口 8000)...
start "Backend" cmd /k "cd backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 8000"

echo 启动前端 (端口 5173)
start "Frontend" cmd /k "cd frontend && npm run dev"


echo 前后端启动命令已执行，请查看对应窗口。
echo 等待 3 秒，让服务初始化...
timeout /t 3 /nobreak >nul
@echo 正在打开前端网页...
start http://localhost:5173
