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
import { scrapeAllSites, type ScrapedArticle } from "./src/scraper.js";

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
// Historical news database — 14 authentic Mongolian drug intel articles
// =============================================================================
const INITIAL_HISTORICAL_NEWS = [
  {
    id: "hist-1", title: "扎门乌德口岸查获12.5公斤非法安纳咖境外走私案",
    originalTitle: "Замын-Үүдийн боомтоор хууль бус КНБ нэвтрүүлэхийг завдсаныг илрүүлэв",
    url: "https://customs.gov.mn/news/125", date: "2026-07-05",
    siteName: "蒙古国海关总局", siteUrl: "customs.gov.mn",
    category: "安纳咖专项 (CNB)", riskLevel: "High" as const,
    summary: "蒙古国海关与边防总局在扎门乌德公路口岸联合执法，对入境货车深度扫描，在底盘备胎内侧查获分装白色粉末12.5公斤，经红外光谱确认为苯甲酸钠咖啡因（安纳咖/КНБ）。案件已移交警方刑事侦查。",
    entities: { locations: ["扎门乌德口岸", "乌兰巴托"], organizations: ["蒙古国海关总局", "边防总局"], suspects: "蒙古国籍司机 B 某" },
    details: { seizureAmount: "12.5公斤 苯甲酸钠咖啡因 (КНБ)", traffickingRoute: "二连浩特 -> 扎门乌德入境蒙古", penalties: "涉嫌刑法第20.7条，面临5-12年徒刑" },
    matchedKeywords: ["анага бодис", "КНБ", "гаалийн илрүүлэлт", "хууль бус импорт"]
  },
  {
    id: "hist-2", title: "乌兰巴托逮捕5名走私销售新型合成大麻及芬太尼贴片的犯罪团伙",
    originalTitle: "Улаанбаатарт синтетик марихуана болон фентанил борлуулдаг бүлэг этгээдүүдийг саатууллаа",
    url: "https://police.gov.mn/news/8832", date: "2026-07-10",
    siteName: "蒙古国国家警察局缉毒分局", siteUrl: "police.gov.mn",
    category: "芬太尼及新型合成毒品", riskLevel: "High" as const,
    summary: "缉毒警察在乌兰巴托巴彦珠尔赫区收网，抓获5人贩毒网络，收缴合成大麻油40余瓶、芬太尼透皮贴片80片、卡西酮晶体120克。团伙通过国际邮递和加密软件引入新型毒品。",
    entities: { locations: ["乌兰巴托巴彦珠尔赫区"], organizations: ["国家警察局缉毒分局", "海关邮局"], suspects: "蒙古籍骨干3名，外籍协助人2名" },
    details: { seizureAmount: "80片芬太尼贴片、40瓶大麻油、120克卡西酮", traffickingRoute: "境外空运国际邮包伪装入境", penalties: "全部嫌疑人已刑事拘留" },
    matchedKeywords: ["фентанил", "каннабис тос", "метамфетамин", "хар тамхины хямдрал"]
  },
  {
    id: "hist-3", title: "司法部起草新法：将新型合成卡西酮等6种化合物列入管制",
    originalTitle: "Хууль зүй, дотоод хэргийн яамнаас шинэ синтетик бодисуудыг хориглох хуулийн төсөл боловсруулав",
    url: "https://mojha.gov.mn/legislation/draft-narc", date: "2026-07-01",
    siteName: "蒙古国司法与内务部", siteUrl: "mojha.gov.mn",
    category: "政策法规", riskLevel: "Medium" as const,
    summary: "司法与内务部提交《毒品和精神药物管制法》修正草案，将甲基麻黄碱、甲卡西酮、4-MEC等6种新型化合物列入严控名录，堵住灰色毒品法律漏洞。",
    entities: { locations: ["国家宫", "乌兰巴托"], organizations: ["司法与内务部", "卫生部", "禁毒工作协调委员会"], suspects: "无" },
    details: { seizureAmount: "政策法规修订", traffickingRoute: "不适用", penalties: "新法通过后最高可判15年徒刑" },
    matchedKeywords: ["мефедрон", "метилэфедрон", "катинон", "амфетамин"]
  },
  {
    id: "hist-4", title: "国家精神卫生中心半年报：大麻及镇静类药品成瘾住院增加22%",
    originalTitle: "Сэтгэцийн эрүүл мэндийн үндэсний төв: мансууруулах бодисын хамааралтай хэвтэн эмчлүүлэгчдийн тоо нэмэгджээ",
    url: "https://ncmh.gov.mn/statistics/2026", date: "2026-06-28",
    siteName: "蒙古国国家精神卫生中心", siteUrl: "ncmh.gov.mn",
    category: "药物成瘾康复与公共卫生", riskLevel: "Medium" as const,
    summary: "国家精神卫生中心发布Q2成瘾统计：大麻、三唑仑等滥用导致强制戒毒住院患者同比激增22%，16-28岁占78%。警告三唑仑混入酒精成失身水。",
    entities: { locations: ["国家精神卫生中心", "乌兰巴托"], organizations: ["蒙古国卫生部"], suspects: "无" },
    details: { seizureAmount: "临床统计报告", traffickingRoute: "不适用", penalties: "呼吁强化处方药流通追溯管理" },
    matchedKeywords: ["марихуана", "триазолам", "флунитразепам", "ГХБ", "каннабис"]
  },
  {
    id: "hist-5", title: "中蒙禁毒高层会议在二连浩特召开 聚焦口岸安纳咖与前体化学品双向堵截",
    originalTitle: "Хятад-Монголын хар тамхитай тэмцэх албаны уулзалт Эрээн хотод болов",
    url: "https://montsame.mn/en/read/39091", date: "2026-07-08",
    siteName: "蒙通社 MONTSAME", siteUrl: "montsame.mn",
    category: "跨国警务合作", riskLevel: "Medium" as const,
    summary: "中蒙两国公安与禁毒高层在二连浩特会晤，重点通报安纳咖和易制毒前体化学品走私新动向，达成口岸缉毒情报直通车机制共识。",
    entities: { locations: ["二连浩特", "扎门乌德"], organizations: ["中国公安部", "内蒙古禁毒办", "蒙古国缉毒分局"], suspects: "两国警务代表团" },
    details: { seizureAmount: "双边执法合作共识", traffickingRoute: "二连浩特 <-> 扎门乌德", penalties: "联合部署跨境控货侦查" },
    matchedKeywords: ["хил хар тамхины наймаа", "гаалийн илрүүлэлт", "хууль бус КНБ", "эфедрин", "КНБ"]
  },
  {
    id: "hist-6", title: "边防部队在苏赫巴托省拦截越境走私大麻树脂6.8公斤",
    originalTitle: "Хил хамгаалах байгууллага Сүхбаатар аймагт марихуана хил давуулахыг таслан зогсоов",
    url: "https://bpo.gov.mn/news/border-seizure-99", date: "2026-07-03",
    siteName: "蒙古国边防总局", siteUrl: "bpo.gov.mn",
    category: "大麻全系", riskLevel: "High" as const,
    summary: "边防第0146部队在苏赫巴托省边境用热成像锁定两名骑摩托越境者，起获大麻树脂6.8公斤、安纳咖片剂1200余粒。",
    entities: { locations: ["苏赫巴托省边境"], organizations: ["蒙古国边防总局", "当地警察局"], suspects: "苏赫巴托省居民2名" },
    details: { seizureAmount: "6.8公斤大麻树脂、1200粒安纳咖片剂", traffickingRoute: "企图穿越荒漠边境线走私出境", penalties: "面临边境武装走私毒品重刑" },
    matchedKeywords: ["марихуана", "гашиш", "хил хар тамхины наймаа", "анага бодис", "КНБ"]
  },
  {
    id: "hist-7", title: "中国禁毒网：内蒙古警方与蒙方联动摧毁跨国安纳咖走私通道",
    originalTitle: "China Anti-Drug: Police bust trans-border caffeine sodium benzoate smuggling route",
    url: "http://www.nncc626.com/2026-07/04/c_1130982.htm", date: "2026-07-04",
    siteName: "中国禁毒网", siteUrl: "nncc626.com",
    category: "跨国联合缉毒", riskLevel: "High" as const,
    summary: "公安部指挥包头、锡盟警方锁定中蒙跨境安纳咖黑灰产团伙，通过国际执法合作双向收网，抓获14人，查获安纳咖成品及原料35公斤。",
    entities: { locations: ["锡林郭勒盟", "包头", "乌兰巴托"], organizations: ["中国公安部", "国家禁毒委员会", "蒙古国警察局"], suspects: "张某、Бат-Эрдэнэ等14人" },
    details: { seizureAmount: "35公斤安纳咖制剂与纯粉", traffickingRoute: "中国内地 -> 内蒙古口岸 -> 蒙古矿区", penalties: "主犯已被批捕，面临走私贩卖毒品罪" },
    matchedKeywords: ["caffeine sodium benzoate", "CNB", "cross-border drug trafficking"]
  },
  {
    id: "hist-8", title: "UNODC：蒙古矿产区工人安纳咖及甲基兴奋剂依赖度上升",
    originalTitle: "UNODC Alert: Rise of controlled stimulants and CNB abuse in Mongolian mining sectors",
    url: "https://unodc.org/narcotics/mongolia-report-2026", date: "2026-06-25",
    siteName: "UNODC 联合国毒品和犯罪问题办公室", siteUrl: "unodc.org",
    category: "国际组织预警", riskLevel: "Medium" as const,
    summary: "UNODC发布蒙古矿区毒品形势预警：安纳咖在南戈壁矿区呈极高扩散态势，存在从咖啡因向冰毒演变的重大风险。",
    entities: { locations: ["南戈壁省", "奥尤陶勒盖矿区"], organizations: ["UNODC", "蒙古国卫生部", "矿业总工会"], suspects: "无" },
    details: { seizureAmount: "公共卫生调研报告", traffickingRoute: "不适用", penalties: "呼吁加强矿区劳动保护和前体化学品管制" },
    matchedKeywords: ["caffeine sodium benzoate", "CNB", "methamphetamine", "drug precursor"]
  },
  {
    id: "hist-9", title: "西伯库伦口岸海关查获未申报安纳咖液体针剂120支",
    originalTitle: "Шивээхүрэн боомтоор сэтгэцэд нөлөөт эм бэлдмэл нэвтрүүлэхийг хураав",
    url: "https://customs.gov.mn/news/142", date: "2026-07-07",
    siteName: "蒙古国海关总局", siteUrl: "customs.gov.mn",
    category: "安纳咖专项 (CNB)", riskLevel: "Medium" as const,
    summary: "西伯库伦口岸海关在煤炭运输空车出境查验中，用便携式液体检测仪在能量口服液包装内检出高浓度安纳咖针剂120支。司机被拘留移送检察机关。",
    entities: { locations: ["西伯库伦口岸", "南戈壁省"], organizations: ["西伯库伦海关", "南戈壁省警察局"], suspects: "蒙古籍司机 Г 某" },
    details: { seizureAmount: "120支安纳咖高浓度针剂", traffickingRoute: "矿产运输通道隐藏夹带", penalties: "涉嫌违反海关法及禁毒法" },
    matchedKeywords: ["анага бодис", "КНБ", "гаалийн илрүүлэлт", "сэтгэцэд нөлөөт эм"]
  },
  {
    id: "hist-10", title: "达尔汗乌拉省破获Telegram网络大麻贩毒案 逮捕3人",
    originalTitle: "Дархан-Уул аймагт Telegram-аар марихуана худалдаалдаг бүлгийг баривчлав",
    url: "https://police.gov.mn/news/8851", date: "2026-07-12",
    siteName: "蒙古国国家警察局缉毒分局", siteUrl: "police.gov.mn",
    category: "大麻全系", riskLevel: "High" as const,
    summary: "达尔汗乌拉省警察追踪暗网一个月，摧毁利用Telegram加密频道分销大麻哈希什的犯罪团伙，抓获3人，收缴浓缩大麻树脂3.2公斤，冻结虚拟货币两千万图格里克。",
    entities: { locations: ["达尔汗乌拉省", "乌兰巴托"], organizations: ["达尔汗警察局", "网络警察局"], suspects: "蒙古籍青年3名(21-25岁)" },
    details: { seizureAmount: "3.2公斤浓缩大麻哈希什", traffickingRoute: "野生采集 -> 线上加密交易 -> 埋包分销", penalties: "涉嫌组织黑社会性质毒品网络分销，最高判15年" },
    matchedKeywords: ["марихуана", "гашиш", "Telegram хар тамхи", "цахим худалдаа"]
  },
  {
    id: "hist-11", title: "科布多省边防从冷链货车轮胎内起获9.8公斤安纳咖粉末",
    originalTitle: "Ховд аймгийн хилээр ачааны дугуйнд нуусан КНБ бодисыг илрүүллээ",
    url: "https://bpo.gov.mn/news/border-seizure-104", date: "2026-07-06",
    siteName: "蒙古国边防总局", siteUrl: "bpo.gov.mn",
    category: "安纳咖专项 (CNB)", riskLevel: "High" as const,
    summary: "科布多省边防对入境冷链车进行全覆盖机检，在备胎和左后轮气室内发现4个防水蛇皮袋装白色结晶粉末，经定性检测为安纳咖9.8公斤。",
    entities: { locations: ["科布多省口岸"], organizations: ["科布多边防第0130部队", "国家安全总局"], suspects: "国际货车司机 D 某" },
    details: { seizureAmount: "9.8公斤纯安纳咖粉末", traffickingRoute: "口岸冷链通道 -> 科布多 -> 乌兰巴托", penalties: "涉嫌严重跨国毒品走私" },
    matchedKeywords: ["КНБ", "кофеин натри бензоат", "хил хамгаалах", "Ховд"]
  },
  {
    id: "hist-12", title: "国家禁毒委联合矿业部在南部三大矿区启动无毒矿区专项整治",
    originalTitle: "Мансууруулах бодистой тэмцэх зөвлөл 'Хар тамхигүй уурхай' аяныг эхлүүлэв",
    url: "https://montsame.mn/en/read/39120", date: "2026-07-09",
    siteName: "蒙通社 MONTSAME", siteUrl: "montsame.mn",
    category: "政策法规", riskLevel: "Medium" as const,
    summary: "国家禁毒委联合矿业部在南戈壁省塔温陶勒盖、奥尤陶勒盖及东戈壁省西伯库伦矿区启动三个月无毒矿区整治，对重卡司机、爆破工等开展高频尿检，严查安纳咖、冰毒及阿片类药物。",
    entities: { locations: ["南戈壁省矿区", "东戈壁省矿区"], organizations: ["国家禁毒委", "矿业与重工业部", "交通运输部"], suspects: "无" },
    details: { seizureAmount: "跨部门安全大排查", traffickingRoute: "不适用", penalties: "阳性人员列入黑名单并吊销操作资格" },
    matchedKeywords: ["мансууруулах бодистой тэмцэх", "уул уурхай хар тамхи", "хяналт шалгалт"]
  },
  {
    id: "hist-13", title: "News.mn深度专访：中蒙跨境毒品贩运正向高度隐蔽化发展",
    originalTitle: "News.mn Ярилцлага: Хар тамхины хил дамнасан урсгал болон химийн бодисын хууль бус эргэлт",
    url: "https://news.mn/news/39201", date: "2026-07-11",
    siteName: "News.mn", siteUrl: "news.mn",
    category: "深度观察与媒体聚焦", riskLevel: "Low" as const,
    summary: "News.mn专访前缉毒警官及法医专家：走私分子将化学前体伪装成工业溶剂流向地下作坊，加密支付使银行追踪失效。呼吁建立中蒙俄化学前体联合预警数据库。",
    entities: { locations: ["乌兰巴托", "口岸边境"], organizations: ["News.mn", "蒙古国法医学研究所"], suspects: "无" },
    details: { seizureAmount: "媒体深度专访", traffickingRoute: "化工原料前体伪装走私入境", penalties: "呼吁修法提高易制毒化学前体刑罚标准" },
    matchedKeywords: ["химийн бодис", "хил дамнасан урсгал", "эфедрин", "хар тамхины хэрэг"]
  },
  {
    id: "hist-14", title: "阿勒坦布拉格口岸海关查获4.5公斤易制毒原料盐酸麻黄碱",
    originalTitle: "Алтанбулаг боомтоор хууль бус эфедрин нэвтрүүлэхийг хураан авлао",
    url: "https://customs.gov.mn/news/122", date: "2026-06-29",
    siteName: "蒙古国海关总局", siteUrl: "customs.gov.mn",
    category: "跨国警务合作", riskLevel: "High" as const,
    summary: "阿勒坦布拉格口岸海关对入境卡车查验，发现侧边工具箱焊死隐藏铁板内藏白色结晶粉末4.5公斤，鉴定为高纯度盐酸麻黄碱（冰毒前体）。司机供述受乌兰巴托神秘买家雇佣。",
    entities: { locations: ["阿勒坦布拉格口岸", "色楞格省"], organizations: ["阿勒坦布拉格海关", "色楞格省警察局"], suspects: "蒙籍司机 Т 某" },
    details: { seizureAmount: "4.5公斤盐酸麻黄碱", traffickingRoute: "北部口岸物流工具箱隐蔽夹带", penalties: "面临7年以上徒刑" },
    matchedKeywords: ["эфедрин", "хууль бус эфедрин", "гаалийн хяналт", "Алтанбулаг"]
  }
];

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

  let results: any[] = [...INITIAL_HISTORICAL_NEWS];
  let wasScrapeSuccess = false;

  // Scrape live Mongolian sites
  try {
    const scraped = await scrapeAllSites();
    if (scraped.length > 0) {
      console.log(`[API] Scraped ${scraped.length} raw articles, enriching via DeepSeek...`);
      const enriched = await enrichArticlesWithAI(scraped);
      if (enriched.length > 0) {
        wasScrapeSuccess = true;
        const existingUrls = new Set(results.map((r: any) => r.url));
        const uniqueLive = enriched
          .map((art: any, i: number) => ({
            ...art,
            id: art.id || `live-${Date.now()}-${i}`,
            riskLevel: ["High", "Medium", "Low"].includes(art.riskLevel) ? art.riskLevel : "Medium",
          }))
          .filter((art: any) => !existingUrls.has(art.url));
        results = [...uniqueLive, ...results];
      }
    }
  } catch (err) {
    console.error("[API] Scrape error:", String(err).substring(0, 200));
  }

  // Apply filters
  if (selectedSiteCategories.length > 0 || selectedKeywords.length > 0 || customQuery) {
    results = results.filter((item: any) => {
      const matchedSite = TARGET_SITES.find((s: any) => s.queryDomain === item.siteUrl);
      const catOk = selectedSiteCategories.length === 0 || (matchedSite && selectedSiteCategories.includes(matchedSite.category));
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
