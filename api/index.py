"""
Vercel Serverless 入口。
在导入 run:app 之前确保项目根目录在 path 里。
"""
import os
import sys
import traceback
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(str(project_root))

try:
    from run import app
except Exception:
    # 如果导入失败，创建一个最小 FastAPI 应用显示错误信息
    from fastapi import FastAPI
    from fastapi.responses import PlainTextResponse

    error_app = FastAPI()

    @error_app.get("/{path:path}")
    async def show_error(path: str):
        return PlainTextResponse(
            f"Import Error:\n\n{traceback.format_exc()}",
            status_code=500,
        )

    app = error_app
