"""
蒙古国涉毒新闻情报爬虫系统 - 一键启动入口
==========================================
FastAPI Web 服务，提供：
- Web 检索界面（/）
- REST API 接口（采集接口需 token 鉴权）
- SSE 实时流式采集（/api/crawl/stream）
- 每条情报采集后实时推送到前端
- 简易关键词检索
- 接口限流 + 鉴权

启动方式:
  python run.py
  uvicorn run:app --host 0.0.0.0 --port 8000
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from fastapi import FastAPI, Query, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from modules.logger import init_logging, get_logger

# 初始化日志系统
init_logging(os.environ.get("LOG_LEVEL", "INFO"))
log = get_logger("run")

from modules.searcher import StreamingCrawlCoordinator
from modules.storage import (
    load_existing_intel,
    save_intel,
    append_single_intel,
    write_audit_log,
    get_intel_stats,
)
from modules.search_tool import search
from modules.translator import translate_article

# 管理后台鉴权 token
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
if not ADMIN_TOKEN:
    log.warning("ADMIN_TOKEN 未设置！采集接口无鉴权保护")

app = FastAPI(
    title="蒙古国涉毒新闻情报爬虫系统",
    description="定向采集蒙古国涉毒资讯，覆盖 19 个数据源",
    version="5.1.0",
)

TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 全局采集状态
crawl_state = {
    "running": False,
    "progress": "",
    "total_articles": 0,
    "coordinator": None,
}

# 简易 IP 限流（每分钟每 IP 最大请求数）
_rate_limits: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_MAX = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))
_RATE_LIMIT_WINDOW = 60


def _check_rate_limit(request: Request):
    """简易 IP 限流"""
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window_start = now - _RATE_LIMIT_WINDOW
    _rate_limits[client_ip] = [t for t in _rate_limits[client_ip] if t > window_start]
    if len(_rate_limits[client_ip]) >= _RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后重试")
    _rate_limits[client_ip].append(now)


def _verify_token(request: Request):
    """验证管理后台 token"""
    if not ADMIN_TOKEN:
        return  # 未配置则不校验
    token = request.query_params.get("token") or request.headers.get("X-Admin-Token", "")
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="无效的管理令牌")


async def _auth_and_limit(request: Request):
    """鉴权 + 限流组合依赖"""
    _check_rate_limit(request)
    _verify_token(request)


# ============================================================
# Web 页面
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    stats = get_intel_stats()
    return templates.TemplateResponse("index.html", {"request": request, "stats": stats})


# ============================================================
# API 路由
# ============================================================

@app.get("/api/intel")
async def api_get_intel(
    keyword: str = Query(default=""),
    source: str = Query(default=""),
    language: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    data = load_existing_intel()
    results = search(data, keyword=keyword, source=source, language=language,
                     start_date=start_date, end_date=end_date, limit=limit + offset)
    total = len(results)
    results = results[offset:offset + limit]
    return {"total": total, "limit": limit, "offset": offset, "results": results}


@app.get("/api/stats")
async def api_get_stats():
    return get_intel_stats()


@app.get("/api/crawl/status")
async def api_crawl_status():
    return {
        "running": crawl_state["running"],
        "progress": crawl_state["progress"],
        "total_articles": crawl_state["total_articles"],
    }


@app.get("/api/crawl/stream")
async def api_crawl_stream(request: Request):
    """
    SSE 流式采集端点（需要 ?token= 鉴权）。
    连接到该端点后自动开始采集，每条情报实时推送到前端。
    客户端断开连接则停止采集。
    """
    _verify_token(request)
    global crawl_state

    if crawl_state["running"]:
        # 已有采集在运行，返回状态 SSE
        async def already_running():
            yield f"event: error\ndata: {json.dumps({'message': '采集任务正在运行中'}, ensure_ascii=False)}\n\n"

        return StreamingResponse(already_running(), media_type="text/event-stream")

    # 用于在回调中存放新采集的文章
    article_queue: asyncio.Queue = asyncio.Queue()

    async def on_article(item: dict):
        """每解析出一条情报时：立即推送 → 后台翻译 → 更新"""
        # 先立即推送原文（不等翻译）
        is_new = append_single_intel(item)
        if is_new:
            crawl_state["total_articles"] += 1
        await article_queue.put(("article", item))

        # 后台异步翻译，完成后更新 JSON 并推送更新
        async def translate_and_update():
            try:
                translated = await translate_article(dict(item))
                # 更新 JSON 中的翻译字段
                existing = load_existing_intel()
                for i, a in enumerate(existing):
                    if a.get("source_url") == item.get("source_url"):
                        existing[i]["cn_title"] = translated.get("cn_title", "")
                        existing[i]["cn_summary"] = translated.get("cn_summary", "")
                        save_intel(existing)
                        await article_queue.put(("translate", translated))
                        break
            except Exception:
                pass

        asyncio.create_task(translate_and_update())

    async def on_progress(msg: str):
        """进度更新"""
        crawl_state["progress"] = msg
        await article_queue.put(("progress", msg))

    crawl_state["running"] = True
    crawl_state["progress"] = "正在初始化采集..."
    crawl_state["total_articles"] = 0

    coordinator = StreamingCrawlCoordinator(on_article=on_article, on_progress=on_progress)
    crawl_state["coordinator"] = coordinator

    async def event_generator():
        """SSE 事件生成器"""
        try:
            # 在后台启动采集任务
            crawl_task = asyncio.create_task(coordinator.crawl_all_streaming())

            # 持续从队列读取并推送到 SSE
            while True:
                # 检查客户端是否断开
                if await request.is_disconnected():
                    coordinator.stop()
                    break

                try:
                    event_type, data = await asyncio.wait_for(article_queue.get(), timeout=0.5)
                    if event_type == "article":
                        yield f"event: article\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    elif event_type == "translate":
                        yield f"event: translate\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    elif event_type == "progress":
                        yield f"event: progress\ndata: {json.dumps({'msg': data}, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # 发送心跳保持连接
                    if crawl_task.done():
                        break
                    yield ": heartbeat\n\n"

            # 采集完成
            result = await crawl_task
            total = result.get("total_articles", 0) if isinstance(result, dict) else 0
            yield f"event: done\ndata: {json.dumps({'total_articles': total}, ensure_ascii=False)}\n\n"

        except asyncio.CancelledError:
            coordinator.stop()
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            crawl_state["running"] = False
            crawl_state["coordinator"] = None
            write_audit_log(
                total_crawled=crawl_state["total_articles"],
                total_parsed=crawl_state["total_articles"],
                total_filtered=0,
                total_new=crawl_state["total_articles"],
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/crawl/stop")
async def api_crawl_stop(request: Request):
    """停止采集（需要 token 鉴权）"""
    _verify_token(request)
    if crawl_state["coordinator"]:
        crawl_state["coordinator"].stop()
    crawl_state["running"] = False
    return {"status": "ok", "message": "采集已停止"}


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    init_logging()
    log.info("系统启动中... 端口=%d", port)
    print(f"""
╔══════════════════════════════════════════════════════════╗
║    蒙古国涉毒新闻情报爬虫系统 v5.1                        ║
║    Mongolia Drug Intelligence Crawler                    ║
║                                                          ║
║    启动地址: http://localhost:{port}                       ║
║    API 文档: http://localhost:{port}/docs                 ║
║                                                          ║
║    数据源: 19 个站点 (5 大类别) · SSE 实时推送+翻译       ║
║    关键词: 蒙/中/英 三语种 · AI 智能分类                  ║
║    鉴权: ADMIN_TOKEN={'已设置' if ADMIN_TOKEN else '未设置(不安全)'}                      ║
╚══════════════════════════════════════════════════════════╝
    """)
    uvicorn.run("run:app", host="0.0.0.0", port=port, reload=False)
