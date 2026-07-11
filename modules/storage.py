"""
蒙古国涉毒新闻情报爬虫 - 存储模块
===================================
负责情报数据的 JSON 文件读写、去重、审计日志记录。

存储文件：
- mongolia_drug_intel.json：结构化情报数据
- audit.log：抓取过程审计日志
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# 确保数据目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)

INTEL_FILE = DATA_DIR / "mongolia_drug_intel.json"
AUDIT_FILE = DATA_DIR / "audit.log"


def load_existing_intel() -> list[dict]:
    """
    从 JSON 文件加载已有情报数据。
    若文件不存在或损坏，返回空列表。
    """
    if not INTEL_FILE.exists():
        return []

    try:
        with open(INTEL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    return []


def save_intel(data: list[dict]):
    """
    保存情报数据到 JSON 文件。
    按 crawl_time 倒序排列（最新在前）。
    """
    # 按抓取时间倒序
    data.sort(key=lambda x: x.get("crawl_time", ""), reverse=True)

    with open(INTEL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_existing_urls(data: list[dict]) -> set[str]:
    """获取已有数据中的所有 URL（用于去重）"""
    return {item.get("source_url", "") for item in data if item.get("source_url")}


def merge_new_intel(existing: list[dict], new_items: list[dict]) -> tuple[list[dict], int]:
    """
    合并新情报到已有数据，按 source_url 去重。
    返回 (合并后的完整列表, 实际新增条数)
    """
    existing_urls = get_existing_urls(existing)
    new_count = 0

    for item in new_items:
        url = item.get("source_url", "")
        if url and url not in existing_urls:
            existing.append(item)
            existing_urls.add(url)
            new_count += 1
        elif not url:
            # 无 URL 的情报（罕见情况），仍添加
            existing.append(item)
            new_count += 1

    return existing, new_count


def write_audit_log(
    total_crawled: int,
    total_parsed: int,
    total_filtered: int,
    total_new: int,
    errors: Optional[list[str]] = None,
):
    """
    写入审计日志到 audit.log。
    记录抓取总量、解析成功数、过滤条数、新增入库条数。
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"=" * 60,
        f"采集时间: {now}",
        f"抓取总量: {total_crawled}",
        f"解析成功: {total_parsed}",
        f"过滤条数: {total_filtered}",
        f"新增入库: {total_new}",
    ]

    if errors:
        lines.append(f"错误信息:")
        for err in errors:
            lines.append(f"  - {err}")

    lines.append(f"=" * 60)
    lines.append("")

    with open(AUDIT_FILE, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def get_intel_stats() -> dict:
    """
    获取情报统计信息。
    返回总数、各语种数量、各来源数量、最近采集时间等。
    """
    data = load_existing_intel()

    if not data:
        return {
            "total": 0,
            "by_language": {},
            "by_source": {},
            "latest_crawl": None,
        }

    by_language = {}
    by_source = {}
    latest_crawl = None

    for item in data:
        # 语种统计
        lang = item.get("language", "unknown")
        by_language[lang] = by_language.get(lang, 0) + 1

        # 来源统计
        source = item.get("source_name", "unknown")
        by_source[source] = by_source.get(source, 0) + 1

        # 最新采集时间
        crawl_time = item.get("crawl_time", "")
        if crawl_time and (latest_crawl is None or crawl_time > latest_crawl):
            latest_crawl = crawl_time

    return {
        "total": len(data),
        "by_language": by_language,
        "by_source": by_source,
        "latest_crawl": latest_crawl,
    }
