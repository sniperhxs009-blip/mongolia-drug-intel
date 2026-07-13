"""
Vercel Serverless 入口。
在导入 run:app 之前确保项目根目录在 path 里。
"""
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(str(project_root))

from run import app
