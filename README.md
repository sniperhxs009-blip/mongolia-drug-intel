# 蒙古国涉毒新闻情报爬虫系统

定向采集蒙古国涉毒资讯的 Python 情报爬虫系统，覆盖 17 个数据源站点，支持蒙语/中文/英语三语种检索。

## 数据源覆盖（5 大类 17 站点）

| 类别 | 站点 | 语种 |
|------|------|------|
| 蒙古禁毒执法机构 | 海关总署、MMRA、总检察院、司法部、国安总局 | 蒙语 |
| 国际驻蒙机构 | UNODC 蒙古站、联合国蒙古办事处、国际刑警组织 NCB | 英语 |
| 蒙古主流媒体 | MONTSAME、IKON、GOGO、News.mn、UB Post、See.mn、Gobimedia | 蒙/英/中 |
| 中方跨境平台 | 中国禁毒网、中新网内蒙古频道 | 中文 |
| 民间调研 NGO | IRIM 独立调研机构 | 蒙语 |

## 环境依赖

- Python 3.10+

## 安装步骤

```bash
# 1. 克隆项目
git clone <repo-url>
cd mongolia-drug-intel

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动服务
python run.py
```

## 启动命令

```bash
# 开发模式（默认 8000 端口）
python run.py

# 自定义端口
PORT=8080 python run.py

# 或使用 uvicorn
uvicorn run:app --host 0.0.0.0 --port 8000
```

启动后访问:
- Web 界面: http://localhost:8000
- API 文档: http://localhost:8000/docs

## 使用教程

### 1. 执行采集

点击 Web 界面「开始采集」按钮，或调用 API:

```bash
curl -X POST http://localhost:8000/api/crawl/start
```

### 2. 检索情报

**Web 界面**: 在搜索框输入关键词，支持语种、时间区间筛选。

**API 调用**:
```bash
# 关键词搜索
curl "http://localhost:8000/api/intel?keyword=芬太尼&limit=20"

# 按语种筛选
curl "http://localhost:8000/api/intel?language=zh"

# 按时间区间
curl "http://localhost:8000/api/intel?start_date=2024-10-01&end_date=2024-12-31"
```

**命令行工具**:
```bash
python -m modules.search_tool --keyword 扎门乌德
python -m modules.search_tool --keyword 口岸 --language zh --limit 20
python -m modules.search_tool --keyword fentanyl --source UNODC
```

### 3. 查看统计

```bash
curl http://localhost:8000/api/stats
```

## 项目结构

```
mongolia-drug-intel/
├── run.py                          # 一键启动入口 (FastAPI)
├── requirements.txt                # Python 依赖
├── render.yaml                     # Render 部署配置
├── config/
│   ├── sites.json                  # 17 站点配置清单
│   └── keywords.json               # 蒙/中/英 三语关键词库
├── modules/
│   ├── searcher.py                 # 搜索抓取模块
│   ├── parser.py                   # HTML 解析模块
│   ├── filter_module.py            # 过滤模块（宽松策略）
│   ├── storage.py                  # JSON 存储 + 审计日志
│   └── search_tool.py              # CLI 关键词检索工具
├── templates/
│   └── index.html                  # Web 检索界面
└── data/
    ├── mongolia_drug_intel.json    # 结构化情报数据
    └── audit.log                   # 采集审计日志
```

## 情报字段说明

| 字段 | 说明 |
|------|------|
| news_title | 新闻完整标题 |
| publish_time | 发布日期 (YYYY-MM-DD) |
| source_url | 新闻原始链接 |
| source_name | 来源机构/媒体名称 |
| content_summary | 正文摘要 (≥80字) |
| language | 语种标签 (mn/zh/en) |
| keyword_hit | 命中关键词 |
| crawl_time | 抓取时间 |

## 核心规则

- **无优先级隔离**: 所有站点平等分配资源，不因国别跳过
- **极度宽松过滤**: 仅 95%+ 纯内地无关内容拦截，口岸快讯全部放行
- **弱词准入**: 「口岸+海关+查获」+ 蒙古地理锚点即可入库
- **DOM 精简清洗**: 仅删除 script/style/noscript，保留侧边栏/页脚快讯
- **反爬优化**: 0.3s 基础延迟 + 0.5s 随机抖动，UA 池轮换
- **死锁兜底**: 采集锁 15 分钟自动释放
