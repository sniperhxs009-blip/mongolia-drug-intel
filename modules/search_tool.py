"""
蒙古国涉毒新闻情报爬虫 - 简易关键词检索工具
============================================
命令行工具，支持按地名、毒品词、来源等条件筛选情报数据。

用法：
  python -m modules.search_tool --keyword 芬太尼
  python -m modules.search_tool --keyword 扎门乌德 --source 蒙通社
  python -m modules.search_tool --language zh --limit 20
  python -m modules.search_tool --keyword 口岸 --start-date 2024-10-01 --end-date 2024-12-31
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INTEL_FILE = DATA_DIR / "mongolia_drug_intel.json"


def load_data() -> list[dict]:
    """加载情报数据"""
    if not INTEL_FILE.exists():
        print(f"[错误] 数据文件不存在: {INTEL_FILE}")
        print("请先运行 run.py 执行采集。")
        sys.exit(1)

    with open(INTEL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def search(
    data: list[dict],
    keyword: str = "",
    source: str = "",
    language: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 50,
) -> list[dict]:
    """
    多条件组合检索。
    - keyword: 在标题和摘要中搜索
    - source: 按来源机构筛选
    - language: 按语种筛选 (mn/zh/en)
    - start_date / end_date: 时间区间 (YYYY-MM-DD)
    - limit: 返回条数上限
    """
    results = []

    for item in data:
        # 关键词筛选
        if keyword:
            kw_lower = keyword.lower()
            title = item.get("news_title", "").lower()
            summary = item.get("content_summary", "").lower()
            kw_hit = item.get("keyword_hit", "").lower()
            if kw_lower not in title and kw_lower not in summary and kw_lower not in kw_hit:
                continue

        # 来源筛选
        if source and source.lower() not in item.get("source_name", "").lower():
            continue

        # 语种筛选
        if language and item.get("language", "") != language:
            continue

        # 时间区间筛选
        pub_time = item.get("publish_time", "")
        if start_date and pub_time < start_date:
            continue
        if end_date and pub_time > end_date:
            continue

        results.append(item)

        if len(results) >= limit:
            break

    return results


def print_results(results: list[dict]):
    """格式化输出检索结果"""
    if not results:
        print("\n未找到匹配的情报记录。")
        return

    print(f"\n找到 {len(results)} 条匹配记录:\n")

    for i, item in enumerate(results, 1):
        print(f"{'─' * 70}")
        print(f"[{i}] {item.get('news_title', '(无标题)')}")
        print(f"    发布时间: {item.get('publish_time', '未知')}")
        print(f"    来源: {item.get('source_name', '未知')}")
        print(f"    语种: {item.get('language', '未知')}")
        print(f"    链接: {item.get('source_url', '')}")
        print(f"    命中词: {item.get('keyword_hit', '')}")
        summary = item.get('content_summary', '')
        if len(summary) > 150:
            summary = summary[:150] + "..."
        print(f"    摘要: {summary}")
    print(f"{'─' * 70}")


def main():
    parser = argparse.ArgumentParser(
        description="蒙古国涉毒情报简易检索工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python -m modules.search_tool --keyword 芬太尼
  python -m modules.search_tool --keyword 扎门乌德 --source 蒙通社
  python -m modules.search_tool --language zh --limit 20
  python -m modules.search_tool --keyword 口岸 --start-date 2024-10-01
        """,
    )

    parser.add_argument("--keyword", "-k", type=str, default="", help="搜索关键词（地名/毒品词）")
    parser.add_argument("--source", "-s", type=str, default="", help="来源机构/媒体名称")
    parser.add_argument("--language", "-l", type=str, default="", choices=["mn", "zh", "en"], help="语种筛选")
    parser.add_argument("--start-date", type=str, default="", help="开始日期 (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default="", help="结束日期 (YYYY-MM-DD)")
    parser.add_argument("--limit", "-n", type=int, default=50, help="返回条数上限 (默认 50)")

    args = parser.parse_args()

    data = load_data()
    results = search(
        data,
        keyword=args.keyword,
        source=args.source,
        language=args.language,
        start_date=args.start_date,
        end_date=args.end_date,
        limit=args.limit,
    )
    print_results(results)


if __name__ == "__main__":
    main()
