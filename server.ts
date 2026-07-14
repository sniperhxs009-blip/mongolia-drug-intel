/**
 * Mongolia Drug Intelligence Monitoring System
 * Express + React SPA with DeepSeek AI for narcotics intelligence analysis.
 * Scrapes Mongolian news sites for drug-related articles.
 */
import express from "express";
import path from "path";
import { createServer as createViteServer } from "vite";
import OpenAI from "openai";
import dotenv from "dotenv";
import { TARGET_SITES } from "./src/data/sites.js";
import { scrapeAllSites, searchWithSerper, searchWithScrapingbee, searchAllSitesDirectly, fetchAllRSS, type ScrapedArticle } from "./src/scraper.js";

dotenv.config();

const app = express();
const PORT = process.env.PORT ? parseInt(process.env.PORT) : 3000;

app.use(express.json({ limit: "5mb" }));

// Initialize DeepSeek API client (OpenAI-compatible)
const apiKey = process.env.DEEPSEEK_API_KEY;
const ai = apiKey
  ? new OpenAI({
      apiKey,
      baseURL: "https://api.deepseek.com/v1",
    })
  : null;

if (ai) {
  console.log("[Server] DeepSeek API initialized");
} else {
  console.log("[Server] No DEEPSEEK_API_KEY — offline mode with curated data");
}

// =============================================================================
// DeepSeek AI: article enrichment & classification
// =============================================================================
async function enrichArticlesWithAI(scraped: ScrapedArticle[]): Promise<any[]> {
  if (!ai || scraped.length === 0) return scraped;

  try {
    const inputData = scraped.map((a) => ({
      title: a.title,
      originalTitle: a.originalTitle,
      url: a.url,
      date: a.date,
      siteName: a.siteName,
      siteUrl: a.siteUrl,
      summary: (a.summary || a.title).substring(0, 500),
    }));

    const response = await ai.chat.completions.create({
      model: "deepseek-chat",
      messages: [
        {
          role: "system",
          content:
            "You are an expert narcotics intelligence analyst. Only reply with valid JSON. Never fabricate articles. If clearly NOT drug-related, include it but set riskLevel=Low and category=非毒品.",
        },
        {
          role: "user",
          content: `Classify and enrich ${scraped.length} Mongolian news articles. For each:
- title: Chinese translation of the headline
- category: 安纳咖专项 / 大麻全系 / 冰毒合成毒品 / 芬太尼全谱系 / 管制精神药品 / 易制毒化学品 / 政策法规 / 跨国警务合作 / 药物成瘾康复 / 深度观察 / 非毒品
- riskLevel: High (major seizure/death/cross-border) | Medium (local arrest/policy) | Low (education/general)
- summary: 100-200 char Chinese analyst summary (who/what/where/amounts)
- entities: {locations, organizations, suspects}
- details: {seizureAmount, traffickingRoute, penalties}
- matchedKeywords: array of Mongolian/English/Russian drug keywords found

Input articles:
${JSON.stringify(inputData, null, 2)}

Return ONLY: [{...}, {...}] JSON array.`,
        },
      ],
      temperature: 0.3,
      max_tokens: 4096,
    });

    const text = response.choices[0]?.message?.content || "";
    const jsonMatch = text.match(/\[[\s\S]*\]/);
    if (jsonMatch) {
      const enriched = JSON.parse(jsonMatch[0]);
      console.log(`[AI] DeepSeek enriched ${enriched.length} articles`);
      return enriched;
    }
    return scraped;
  } catch (err) {
    console.error("[AI] Enrichment failed:", String(err).substring(0, 200));
    return scraped;
  }
}

// =============================================================================
// POST /api/search — Search drug news
// =============================================================================
app.post("/api/search", async (req, res) => {
  const { selectedSiteCategories = [], selectedKeywords = [], timeRange = "month", customQuery = "" } = req.body;

  console.log(`[API] Search: cats=[${selectedSiteCategories}], kws=[${selectedKeywords.slice(0, 3)}...]`);

  let results: any[] = [];
  let wasScrapeSuccess = false;

  // Scrape real Mongolian sites via Serper.dev + RSS
  try {
    const scraped = await scrapeAllSites();
    console.log(`[API] Scraped ${scraped.length} raw articles, enriching via DeepSeek...`);
    if (scraped.length > 0) {
      const enriched = await enrichArticlesWithAI(scraped);
      if (enriched.length > 0) {
        wasScrapeSuccess = true;
        results = scraped
          .map((s: any, i: number) => ({
            ...s,
            ...(enriched[i] || {}),
            id: enriched[i]?.id || s.id || `live-${Date.now()}-${i}`,
            riskLevel: ["High", "Medium", "Low"].includes(enriched[i]?.riskLevel) ? enriched[i].riskLevel : s.riskLevel || "Medium",
          }));
      } else {
        results = scraped;
      }
    }
  } catch (err) {
    console.error("[API] Scrape error:", String(err).substring(0, 200));
  }

  // Apply time range filter
  const now = new Date();
  let cutoffDate: Date | null = null;
  if (timeRange === "day") {
    cutoffDate = new Date(now.getTime() - 24 * 60 * 60 * 1000);
  } else if (timeRange === "week") {
    cutoffDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  } else if (timeRange === "month") {
    cutoffDate = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
  }

  if (cutoffDate) {
    results = results.filter((item: any) => {
      try {
        const d = new Date(item.date);
        return !isNaN(d.getTime()) && d >= cutoffDate!;
      } catch {
        return true; // keep if date unparseable
      }
    });
  }

  // Apply category / keyword filters
  if (selectedSiteCategories.length > 0 || selectedKeywords.length > 0 || customQuery) {
    results = results.filter((item: any) => {
      const matchedSite = TARGET_SITES.find((s: any) => s.queryDomain === item.siteUrl);
      // Allow articles from sites not in TARGET_SITES (e.g. thediplomat.com, incb.org)
      const catOk = selectedSiteCategories.length === 0 || !matchedSite || selectedSiteCategories.includes(matchedSite.category);
      let kwOk = selectedKeywords.length === 0;
      if (selectedKeywords.length > 0 && item.matchedKeywords) {
        kwOk = item.matchedKeywords.some((kw: string) =>
          selectedKeywords.some((sk: string) => kw.toLowerCase().includes(sk.toLowerCase()) || sk.toLowerCase().includes(kw.toLowerCase()))
        );
      }
      let cqOk = true;
      if (customQuery && customQuery.trim()) {
        const cq = customQuery.toLowerCase();
        cqOk = [item.title, item.originalTitle, item.summary, item.siteName].some((s: string) => (s || "").toLowerCase().includes(cq));
      }
      return (catOk && kwOk) || (cqOk && customQuery.trim() !== "");
    });
  }

  results.sort((a: any, b: any) => new Date(b.date).getTime() - new Date(a.date).getTime());

  res.json({ success: true, count: results.length, articles: results, isLive: wasScrapeSuccess, isQuotaExceeded: false });
});

// =============================================================================
// POST /api/intelligence-report — Generate AI intelligence report
// =============================================================================
app.post("/api/intelligence-report", async (req, res) => {
  const { articles = [] } = req.body;
  if (articles.length === 0) return res.status(400).json({ success: false, message: "No articles to analyze." });

  const getOfflineReport = (prefix = "") =>
    `${prefix}# 蒙古国及中蒙跨境涉毒情报监控研判报告

## 一、总体态势与核心威胁
本周期共录得涉毒情报 **${articles.length}** 起。
1. **安纳咖（CNB）走私** 属中蒙双向执法最核心痛点。
2. **大麻类毒品** 本地高发，边境流转活跃。
3. **新型精神药物** 加速向乌兰巴托矿产区渗透。

## 二、关键查获与打击热点
* 口岸重大安纳咖走私案：海关与边防查获多起藏匿夹带
* 中蒙跨境执法联动：联合打击跨国走私供应链
* 乌兰巴托新型毒品网络：网络邮递贩毒新手法

## 三、风险漏洞
* 矿产劳动人群刚性需求：矿区滥用安纳咖刺激剂现象突出
* 法规滞后：新型合成化合物通过化学改性逃避管制
* 网络支付去中心化使传统追踪失效

## 四、针对性建议
1. 中蒙口岸协同化红外化查缉
2. 化学前体与管制药品全流向追溯
3. 矿区公共卫生与劳动强度干预
4. 加密通讯与虚拟货币联合监测`;

  if (!ai) return res.json({ success: true, report: getOfflineReport(), isLive: false });

  try {
    console.log(`[API] Generating intelligence report for ${articles.length} articles...`);
    const summary = articles.map((a: any, i: number) =>
      `[${i + 1}] ${a.title} | ${a.siteName} | ${a.date} | ${a.category} | ${a.riskLevel}\n${a.summary}\n${JSON.stringify(a.details || {})}\n${(a.matchedKeywords || []).join(", ")}`
    ).join("\n\n");

    const response = await ai.chat.completions.create({
      model: "deepseek-chat",
      messages: [
        { role: "system", content: "You are a professional narcotics intelligence analyst. Write exhaustive, structured Chinese reports with military/police analytical tone. Use Markdown." },
        {
          role: "user",
          content: `Based on these Mongolia drug-related intelligence articles, write a comprehensive 蒙古国及中蒙跨境涉毒情报监控研判报告 with:
1. 总体态势与核心威胁 (statistics, drug categories, risk breakdown, CNB focus)
2. 关键查获与打击热点事件 (major seizures, operations, routes, international collaboration)
3. 风险漏洞与协同监控盲区 (miner/trucker stimulant abuse, legal loopholes, mail/online risks)
4. 针对性打击与监控策略建议 (customs, policy, law enforcement, healthcare)

Intelligence data:\n${summary}`,
        },
      ],
      temperature: 0.5,
      max_tokens: 4096,
    });

    res.json({ success: true, report: response.choices[0]?.message?.content || getOfflineReport(), isLive: true });
  } catch (error) {
    console.error("[API] Report error:", String(error).substring(0, 200));
    const errStr = String(error);
    const isQuota = errStr.includes("429") || errStr.includes("quota") || errStr.includes("Insufficient");
    res.json({ success: true, report: getOfflineReport(isQuota ? "> **[降级通报]** DeepSeek API配额超限，已启动离线决策保护。\n\n" : "> **[降级通报]** API连接异常，已启用本地专家级研判模板。\n\n"), isLive: false, isQuotaExceeded: isQuota });
  }
});

// =============================================================================
// GET /api/debug-direct — Capture raw context per link from direct search
// =============================================================================
app.get("/api/debug-direct", async (_req, res) => {
  const results: Record<string, any> = {};

  const USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36";
  const DRUG_KW = ["хар тамхи", "мансууруулах", "наркотик", "фентанил", "психотроп", "каннабис", "drug", "narcotic"];

  const sites = [
    { name: "ikon.mn", url: "https://ikon.mn/search?q=" + encodeURIComponent("хар тамхи"), pattern: /href="(\/n\/[^"]+)"/g },
    { name: "montsame.mn", url: "https://montsame.mn/mn/search?q=" + encodeURIComponent("хар тамхи"), pattern: /href="(\/mn\/read\/[^"]+)"/g },
  ];

  for (const site of sites) {
    try {
      const resp = await fetch(site.url, {
        headers: { "User-Agent": USER_AGENT },
        signal: AbortSignal.timeout(15000),
      });
      const html = await resp.text();

      const links: any[] = [];
      const seen = new Set<string>();
      let match: RegExpExecArray | null;
      site.pattern.lastIndex = 0;

      while ((match = site.pattern.exec(html)) !== null && links.length < 5) {
        const href = match[1].replace(/#.*$/, "");
        if (seen.has(href)) continue;
        seen.add(href);

        const ctxStart = Math.max(0, match.index - 300);
        const ctxEnd = Math.min(html.length, match.index + 400);
        const context = html.substring(ctxStart, ctxEnd)
          .replace(/<script[\s\S]*?<\/script>/gi, "")
          .replace(/<style[\s\S]*?<\/style>/gi, "")
          .replace(/<img[^>]*>/gi, "")
          .replace(/<[^>]*>/g, " ")
          .replace(/&[a-z]+;/gi, " ")
          .replace(/\s+/g, " ")
          .trim();

        const hasKW = DRUG_KW.some(kw => context.toLowerCase().includes(kw.toLowerCase()));

        links.push({
          href,
          ctxLen: context.length,
          ctxStart100: context.substring(0, 100),
          ctxEnd100: context.substring(Math.max(0, context.length - 100)),
          hasKW,
        });
      }

      results[site.name] = { status: resp.status, htmlLen: html.length, links };
    } catch (e: any) {
      results[site.name] = { error: String(e).substring(0, 200) };
    }
  }

  res.json(results);
});

// =============================================================================
// GET /api/debug — Diagnose individual search methods
// =============================================================================
app.get("/api/debug", async (_req, res) => {
  const results: Record<string, any> = {};
  const startTime = Date.now();

  // Test each scraper method independently
  const serperStart = Date.now();
  try {
    const r = await searchWithSerper();
    results.serper = { ok: true, count: r.length, ms: Date.now() - serperStart, sample: r.slice(0, 2).map((x) => x.link) };
  } catch (e: any) {
    results.serper = { ok: false, error: String(e).substring(0, 200), ms: Date.now() - serperStart };
  }

  const sbStart = Date.now();
  try {
    const r = await searchWithScrapingbee();
    results.scrapingbee = { ok: true, count: r.length, ms: Date.now() - sbStart };
  } catch (e: any) {
    results.scrapingbee = { ok: false, error: String(e).substring(0, 200), ms: Date.now() - sbStart };
  }

  const directStart = Date.now();
  try {
    const r = await searchAllSitesDirectly();
    results.directSearch = { ok: true, count: r.length, ms: Date.now() - directStart, sample: r.slice(0, 2).map((x) => x.link) };
  } catch (e: any) {
    results.directSearch = { ok: false, error: String(e).substring(0, 200), ms: Date.now() - directStart };
  }

  const rssStart = Date.now();
  try {
    const r = await fetchAllRSS();
    results.rss = { ok: true, count: r.length, ms: Date.now() - rssStart, sample: r.slice(0, 2).map((x) => x.link) };
  } catch (e: any) {
    results.rss = { ok: false, error: String(e).substring(0, 200), ms: Date.now() - rssStart };
  }

  results.totalMs = Date.now() - startTime;
  results.env = {
    hasSerperKey: !!process.env.SERPER_API_KEY,
    hasScrapingbeeKey: !!process.env.SCRAPINGBEE_API_KEY,
    hasDeepseekKey: !!process.env.DEEPSEEK_API_KEY,
  };

  res.json(results);
});

// =============================================================================
// Start server
// =============================================================================
async function startServer() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({ server: { middlewareMode: true }, appType: "spa" });
    app.use(vite.middlewares);
    console.log("[Server] Vite dev middleware mounted");
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (_req, res) => res.sendFile(path.join(distPath, "index.html")));
    console.log("[Server] Static build mode enabled");
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`[Server] Mongolia Drug Intel System — http://0.0.0.0:${PORT}`);
  });
}

try {
  startServer();
} catch (err) {
  console.error("[Server] Boot failed:", err);
}
