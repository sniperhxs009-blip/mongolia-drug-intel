"""
DeepSeek 联网搜索 — 蒙古国月度涉毒情报全量检索
==============================================
使用 DeepSeek API 的联网搜索能力，按 7 大类信源完整检索
过去 30 天的蒙古国涉毒新闻，导出结构化 JSON 结果。
"""
import json, os, sys, time
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
if not DEEPSEEK_API_KEY:
    print("错误: 未设置 DEEPSEEK_API_KEY 环境变量")
    sys.exit(1)

from modules.logger import init_logging, get_logger
init_logging("INFO")
log = get_logger("deepseek_search")

CUTOFF_DATE = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

SEARCH_PROMPT = f"""你是蒙古国毒品情报OSINT分析师。请使用联网搜索功能，检索过去30天（{CUTOFF_DATE} 至今）的蒙古国涉毒新闻。

## 检索要求

请按以下7大类，分别搜索并返回具体新闻条目：

### 1. 蒙古国禁毒执法机构动态
搜索: site:montsame.mn 毒品 OR 缉毒 OR мансууруулах OR хар тамхи OR narcotics
搜索: site:customs.gov.mn мансууруулах OR хар тамхи OR drug seizure
搜索: site:bpo.gov.mn хар тамхи OR мансууруулах

### 2. 蒙古国司法监管
搜索: site:mojha.gov.mn мансууруулах OR хар тамхи
搜索: site:parliament.mn мансууруулах OR narcotics

### 3. 蒙古国卫健&戒毒
搜索: site:mohs.mn мансууруулах OR хар тамхи OR drug addiction Mongolia

### 4. 蒙古国主流媒体（重点）
搜索: site:montsame.mn хар тамхи OR мансууруулах OR наркотик
搜索: site:ikon.mn хар тамхи OR мансууруулах
搜索: site:news.mn хар тамхи OR мансууруулах
搜索: site:shuum.mn хар тамхи OR мансууруулах
搜索: site:gogo.mn хар тамхи OR мансууруулах

### 5. 中蒙跨境缉毒
搜索: site:nncc.org.cn 蒙古 OR 中蒙边境 OR 扎门乌德
搜索: site:chinanews.com.cn 蒙古 毒品 OR 缉毒
搜索: site:people.com.cn 蒙古 毒品 OR 中蒙 禁毒

### 6. 国际禁毒组织
搜索: site:unodc.org Mongolia drug OR narcotics
搜索: site:interpol.int Mongolia drug

### 7. 区域毒品态势
搜索: Mongolia drug trafficking report 2026
搜索: China Mongolia border drug seizure 2026

## 输出格式

请为每个搜索类别返回具体的新闻条目。每条包含：
- title: 新闻标题（原文+中文翻译）
- url: 新闻链接
- date: 发布日期
- source: 来源网站
- summary: 简要摘要（中文，50字内）
- category: 所属大类（1-7）

只返回 JSON 数组格式：
[{{"title": "...", "url": "...", "date": "...", "source": "...", "summary": "...", "category": "..."}}, ...]

如果没有找到任何结果，返回空数组 []。

## 重要约束
- 只搜索过去30天内的内容
- 优先返回官方来源和权威媒体
- 去重：同一事件多网站报道只保留一条
- 不编造任何信息，搜索无结果就返回空
"""


def call_deepseek_search(prompt: str) -> str:
    """调用 DeepSeek API 联网搜索"""
    import httpx

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是一个专业的OSINT情报分析师，擅长使用搜索引擎检索全球公开信息。请启用联网搜索功能。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 8000,
        "stream": False,
    }

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                "https://api.deepseek.com/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return content
            else:
                log.error("DeepSeek API 错误: %d %s", resp.status_code, resp.text[:200])
                return ""
    except Exception as e:
        log.error("DeepSeek API 异常: %s", e)
        return ""


def extract_json_from_response(text: str) -> list[dict]:
    """从 DeepSeek 回复中提取 JSON 数组"""
    import re

    # 尝试直接解析
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # 尝试提取 JSON 数组块
    json_match = re.search(r'\[[\s\S]*\]', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # 尝试逐个提取 JSON 对象
    results = []
    for match in re.finditer(r'\{[^{}]*"title"[^{}]*\}', text):
        try:
            results.append(json.loads(match.group()))
        except json.JSONDecodeError:
            continue

    return results


def main():
    print(f"开始 DeepSeek 联网检索... 日期范围: {CUTOFF_DATE} 至今")
    print("=" * 60)

    raw_response = call_deepseek_search(SEARCH_PROMPT)

    if not raw_response:
        print("DeepSeek API 未返回结果。可能联网搜索不可用。")
        print("请确认 DeepSeek 账户已开通联网搜索功能。")
        sys.exit(1)

    results = extract_json_from_response(raw_response)
    output = {
        "search_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date_range": f"{CUTOFF_DATE} 至今",
        "total_found": len(results),
        "raw_response_length": len(raw_response),
        "articles": results,
        "raw_response_snippet": raw_response[:500],
    }

    # 保存结果
    output_dir = BASE_DIR / "data" / "deepseek_search"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"检索完成: 找到 {len(results)} 条结果")
    print(f"结果已保存: {output_path}")

    # 也保存原始回复供人工审核
    raw_path = output_dir / f"raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(raw_response)
    print(f"原始回复: {raw_path}")

    return results


if __name__ == "__main__":
    main()
