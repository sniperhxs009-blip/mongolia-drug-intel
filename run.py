"""
蒙古国涉毒新闻情报爬虫系统 - 一键启动入口
==========================================
FastAPI Web 服务，提供：
- Web 检索界面（/）
- REST API 接口
- 一键触发全站采集
- 简易关键词检索
- 情报数据浏览

启动方式:
  python run.py
  uvicorn run:app --host 0.0.0.0 --port 8000

首次使用：
  1. 启动服务后访问 http://localhost:8000
  2. 点击「开始采集」触发首次数据抓取
  3. 在搜索框输入关键词检索情报
"""

import asyncio
import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# 确保项目根目录在 sys.path 中
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from modules.searcher import CrawlCoordinator
from modules.parser import parse_all_results
from modules.filter_module import apply_filters
from modules.storage import (
    load_existing_intel,
    save_intel,
    merge_new_intel,
    write_audit_log,
    get_intel_stats,
)
from modules.search_tool import search

# ============================================================
# FastAPI 应用初始化
# ============================================================
app = FastAPI(
    title="蒙古国涉毒新闻情报爬虫系统",
    description="定向采集蒙古国涉毒资讯，覆盖蒙古官方禁毒机构、国际驻蒙禁毒单位、蒙古主流媒体、中方跨境禁毒平台",
    version="2.0.0",
)

# 模板目录
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# 数据目录
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 全局采集状态
crawl_status = {
    "running": False,
    "progress": "",
    "last_crawl_time": None,
    "last_error": None,
    "total_crawled": 0,
    "total_parsed": 0,
    "total_filtered": 0,
    "total_new": 0,
}


# ============================================================
# Web 页面路由
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """情报检索主页面"""
    stats = get_intel_stats()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "stats": stats,
    })


# ============================================================
# API 路由
# ============================================================

@app.get("/api/intel")
async def api_get_intel(
    keyword: str = Query(default="", description="搜索关键词"),
    source: str = Query(default="", description="来源机构"),
    language: str = Query(default="", description="语种 (mn/zh/en)"),
    start_date: str = Query(default="", description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(default="", description="结束日期 YYYY-MM-DD"),
    limit: int = Query(default=100, ge=1, le=1000, description="返回条数上限"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
):
    """
    检索情报数据。
    支持多条件组合筛选：关键词、来源、语种、时间区间。
    """
    data = load_existing_intel()
    results = search(data, keyword=keyword, source=source, language=language,
                     start_date=start_date, end_date=end_date,
                     limit=limit + offset)

    # 分页
    total = len(results)
    results = results[offset:offset + limit]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": results,
    }


@app.get("/api/stats")
async def api_get_stats():
    """获取情报统计信息"""
    return get_intel_stats()


@app.get("/api/crawl/status")
async def api_crawl_status():
    """获取采集任务状态"""
    return crawl_status


@app.post("/api/crawl/start")
async def api_crawl_start():
    """
    一键启动全站采集。
    异步执行采集任务，立即返回状态。
    """
    global crawl_status

    if crawl_status["running"]:
        return {"status": "error", "message": "采集任务正在运行中，请等待完成后再试。"}

    # 在新线程中启动异步采集
    crawl_status["running"] = True
    crawl_status["progress"] = "正在初始化..."
    crawl_status["last_error"] = None

    thread = threading.Thread(target=_run_crawl_in_thread, daemon=True)
    thread.start()

    return {"status": "ok", "message": "采集任务已启动"}


def _run_crawl_in_thread():
    """在后台线程中执行采集任务"""
    global crawl_status

    try:
        # 创建新的事件循环用于线程
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        coordinator = CrawlCoordinator()

        # 自定义进度回调
        def progress_callback(stage, site_name, current, total):
            crawl_status["progress"] = f"正在采集 [{current}/{total}]: {site_name}"

        crawl_status["progress"] = "正在抓取网页..."
        raw_results = loop.run_until_complete(coordinator.crawl_all_sites(progress_callback))

        total_crawled = len(raw_results)
        crawl_status["total_crawled"] = total_crawled
        crawl_status["progress"] = f"抓取完成，共 {total_crawled} 条，正在解析..."

        # 解析
        parsed = parse_all_results(raw_results)
        total_parsed = len(parsed)
        crawl_status["total_parsed"] = total_parsed
        crawl_status["progress"] = f"解析完成，共 {total_parsed} 条，正在过滤..."

        # 过滤
        filtered, filtered_count = apply_filters(parsed)
        crawl_status["total_filtered"] = filtered_count
        crawl_status["progress"] = f"过滤完成，保留 {len(filtered)} 条，正在存储..."

        # 合并存储
        existing = load_existing_intel()
        merged, new_count = merge_new_intel(existing, filtered)
        save_intel(merged)
        crawl_status["total_new"] = new_count

        # 审计日志
        write_audit_log(
            total_crawled=total_crawled,
            total_parsed=total_parsed,
            total_filtered=filtered_count,
            total_new=new_count,
        )

        crawl_status["progress"] = f"采集完成！共抓取 {total_crawled} 条，新增 {new_count} 条入库。"
        crawl_status["last_crawl_time"] = datetime.now().isoformat()

        loop.close()

    except Exception as e:
        crawl_status["progress"] = f"采集出错: {str(e)}"
        crawl_status["last_error"] = str(e)
    finally:
        crawl_status["running"] = False


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    print(f"""
╔══════════════════════════════════════════════════════════╗
║    蒙古国涉毒新闻情报爬虫系统 v2.0                        ║
║    Mongolia Drug Intelligence Crawler                    ║
║                                                          ║
║    启动地址: http://localhost:{port}                       ║
║    API 文档: http://localhost:{port}/docs                 ║
║                                                          ║
║    数据源: 17 个站点 (5 大类别)                           ║
║    关键词: 蒙/中/英 三语种                                ║
╚══════════════════════════════════════════════════════════╝
    """)
    uvicorn.run("run:app", host="0.0.0.0", port=port, reload=False)
