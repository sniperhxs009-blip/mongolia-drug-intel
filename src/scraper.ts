/**
 * Mongolia Drug Intel — Real Article Discovery
 * Strategies: Serper.dev Google Search + RSS feed parsing.
 * Zero fabricated data. Every article has a real, verifiable URL.
 */
import axios from "axios";

const USER_AGENT =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

// ── Drug keywords in Mongolian / English / Chinese ──────────────────────────
const DRUG_KEYWORDS_MN = [
  "мансууруулах", "хар тамхи", "наркотик", "фентанил", "психотроп",
  "каннабис", "марихуана", "кокаин", "метамфетамин", "амфетамин",
  "катинон", "мефедрон", "гашиш", "КНБ", "анага бодис",
  "кофеин натри бензоат", "эфедрин", "хууль бус эргэлт",
  "гаалийн илрүүлэлт", "хил хамгаалах",
];

const DRUG_KEYWORDS_EN = [
  "drug", "narcotic", "drug trafficking", "smuggling",
  "opioid", "fentanyl", "meth", "cocaine", "heroin", "cannabis",
  "cartel", "anti-drug",
  "UNODC", "interpol", "methamphetamine", "ecstasy",
  "crystal meth", "drug smuggl", "drug bust", "narcotic traffick",
  "synthetic drug", "illicit drug", "illicit traffick",
  "drug lord", "drug dealer", "drug network",
];

// Ambiguous keywords: only count if another strong drug keyword is also present
const WEAK_KEYWORDS_EN = new Set(["trafficking", "seizure", "illicit", "arrest", "raid", "bust"]);

const DRUG_KEYWORDS_ZH = [
  "毒品", "贩毒", "缉毒", "禁毒", "走私毒品", "跨境贩毒",
  "吸毒", "海洛因", "冰毒", "吗啡", "摇头丸", "查获", "缴获",
  "安纳咖", "苯甲酸钠咖啡因", "海关", "边防",
];

// ── RSS feed URLs ───────────────────────────────────────────────────────────
const RSS_FEEDS = [
  "https://montsame.mn/en/rss",
  "https://montsame.mn/mn/rss",
  "https://news.mn/rss",
  "https://ikon.mn/rss",
];

// ── Types ───────────────────────────────────────────────────────────────────
export interface ScrapedArticle {
  title: string;
  originalTitle: string;
  url: string;
  date: string;
  siteName: string;
  siteUrl: string;
  summary: string;
  category: string;
  riskLevel: "High" | "Medium" | "Low";
  entities: {
    locations: string[];
    organizations: string[];
    suspects: string;
  };
  details: {
    seizureAmount: string;
    traffickingRoute: string;
    penalties: string;
  };
  matchedKeywords: string[];
}

interface SerperResult {
  title: string;
  link: string;
  snippet: string;
  date?: string;
  source?: string;
}

// ── Keyword matching ────────────────────────────────────────────────────────
function hasDrugKeyword(text: string): boolean {
  const lower = text.toLowerCase();

  // Strong keywords (Mongolian, Chinese, or explicit drug terms in English)
  const hasStrong =
    DRUG_KEYWORDS_MN.some((kw) => lower.includes(kw)) ||
    DRUG_KEYWORDS_ZH.some((kw) => lower.includes(kw)) ||
    DRUG_KEYWORDS_EN.some((kw) => lower.includes(kw));

  if (hasStrong) return true;

  // Weak keywords only count if accompanied by another weak keyword
  // (prevents "child trafficking" or "cultural seizure" false positives)
  const weakHits = [...WEAK_KEYWORDS_EN].filter((kw) => lower.includes(kw));
  return weakHits.length >= 2;
}

function extractDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function extractMatchedKeywords(text: string): string[] {
  const lower = text.toLowerCase();
  const matched: string[] = [];
  for (const kw of [...DRUG_KEYWORDS_MN, ...DRUG_KEYWORDS_EN, ...DRUG_KEYWORDS_ZH]) {
    if (lower.includes(kw)) matched.push(kw);
  }
  return matched.slice(0, 10);
}

// ── Domain filtering ────────────────────────────────────────────────────────
// Known Mongolian second-level domains (to distinguish .mn Mongolia from .mn Minnesota)
const MONGOLIAN_SLD = new Set([
  "montsame.mn", "news.mn", "gogo.mn", "ikon.mn", "unuudur.mn",
  "24tsag.mn", "itoim.mn", "eguur.mn", "olloo.mn", "ubn.mn",
  "time.mn", "fact.mn", "shuum.mn", "zaluu.mn", "assa.mn",
  "customs.gov.mn", "police.gov.mn", "bpo.gov.mn", "mojha.gov.mn",
  "nema.gov.mn", "nfa.gov.mn", "mongolia.gov.mn", "parliament.mn",
  "ncmh.gov.mn", "mohs.mn", "moe.gov.mn",
]);

// International domains that publish Mongolia drug-related content
const INTL_DRUG_DOMAINS = [
  "unodc.org", "interpol.int", "nncc626.com", "mps.gov.cn",
  "thediplomat.com", "unesco.org", "ocindex.net",
  "incb.org", "state.gov",
];

// Social media / video — cannot crawl content, skip
const SKIP_DOMAINS = new Set([
  "facebook.com", "youtube.com", "youtu.be",
  "twitter.com", "x.com", "instagram.com",
  "reddit.com", "linkedin.com",
]);

function isMongoliaRelevant(url: string, title: string, snippet: string): boolean {
  try {
    const host = new URL(url).hostname.replace(/^www\./, "");

    // Skip social media / video sites — cannot crawl for content
    for (const skip of SKIP_DOMAINS) {
      if (host === skip || host.endsWith("." + skip)) return false;
    }

    // Check if it's a known Mongolian domain
    if (MONGOLIAN_SLD.has(host)) return true;
    // Check subdomains of known Mongolian domains
    if (host.endsWith(".gov.mn")) return true;
    for (const sld of MONGOLIAN_SLD) {
      if (host.endsWith("." + sld)) return true;
    }

    // Check international drug org domains — must still mention Mongolia
    for (const d of INTL_DRUG_DOMAINS) {
      if (host === d || host.endsWith("." + d)) {
        const combined = `${title} ${snippet}`.toLowerCase();
        if (combined.includes("mongolia") || combined.includes("монгол")) return true;
        return false; // international org but no Mongolia mention → skip
      }
    }

    // For anything else: must mention Mongolia in title or snippet
    const combined = `${title} ${snippet}`.toLowerCase();
    return combined.includes("mongolia") || combined.includes("монгол");
  } catch {
    return false;
  }
}

// ── Serper.dev Google Search ────────────────────────────────────────────────
async function searchWithSerper(): Promise<SerperResult[]> {
  const apiKey = process.env.SERPER_API_KEY;
  if (!apiKey) {
    console.warn("[Scraper] WARNING: No SERPER_API_KEY env var — Serper search disabled");
    return [];
  }
  console.log(`[Scraper] Serper API key present (${apiKey.substring(0, 8)}...)`);

  const results: SerperResult[] = [];
  const seen = new Set<string>();

  const queries: { q: string; gl: string; hl: string }[] = [];

  // ── English broad searches ──
  queries.push({ q: "Mongolia drug trafficking arrest seizure customs", gl: "mn", hl: "en" });
  queries.push({ q: "Mongolia narcotics smuggling bust meth fentanyl", gl: "mn", hl: "en" });
  queries.push({ q: "Mongolia synthetic drugs precursor chemicals", gl: "mn", hl: "en" });
  queries.push({ q: "Mongolia cannabis marijuana cultivation eradication", gl: "mn", hl: "en" });
  queries.push({ q: "Mongolia drug cartel organized crime heroin cocaine", gl: "mn", hl: "en" });
  queries.push({ q: "Mongolia UNODC INCB drug report narcotic control", gl: "mn", hl: "en" });
  queries.push({ q: "Mongolia cross-border drug smuggling China Russia Kazakhstan", gl: "mn", hl: "en" });
  queries.push({ q: "Mongolia opioid crisis substance abuse addiction treatment", gl: "mn", hl: "en" });
  queries.push({ q: "Mongolia CNB caffeine sodium benzoate drug", gl: "mn", hl: "en" });
  queries.push({ q: "Mongolia psychotropic substance control law enforcement", gl: "mn", hl: "en" });

  // ── Chinese cross-border searches ──
  queries.push({ q: "蒙古国 毒品 贩毒 走私 缉毒 禁毒 缴获", gl: "cn", hl: "zh-cn" });
  queries.push({ q: "中蒙 口岸 查获 毒品 安纳咖 冰毒 海洛因", gl: "cn", hl: "zh-cn" });
  queries.push({ q: "蒙古 跨境 贩毒 海关 边防 苯甲酸钠 咖啡因", gl: "cn", hl: "zh-cn" });
  queries.push({ q: "内蒙古 二连浩特 满洲里 口岸 蒙古 走私毒品", gl: "cn", hl: "zh-cn" });
  queries.push({ q: "中蒙边境 缉毒 边防检查 吸毒 戒毒 康复", gl: "cn", hl: "zh-cn" });
  queries.push({ q: "蒙古国 禁毒 国际合作 UNODC 毒品犯罪", gl: "cn", hl: "zh-cn" });
  queries.push({ q: "外蒙古 毒品泛滥 新型毒品 合成毒品 大麻", gl: "cn", hl: "zh-cn" });
  queries.push({ q: "甘其毛都 策克 口岸 蒙古 查获 走私 毒品", gl: "cn", hl: "zh-cn" });

  // ── Site-specific .mn news sites ──
  for (const site of ["montsame.mn", "news.mn", "gogo.mn", "ikon.mn", "unuudur.mn", "24tsag.mn"]) {
    queries.push({ q: `site:${site} drug OR narcotic OR trafficking OR cannabis OR meth OR fentanyl OR heroin OR cocaine OR seizure OR arrest OR smuggling`, gl: "mn", hl: "en" });
  }

  // ── Government / official sites ──
  queries.push({ q: "site:customs.gov.mn drug OR narcotic OR seizure OR smuggling OR trafficking", gl: "mn", hl: "en" });
  queries.push({ q: "site:police.gov.mn drug OR narcotic OR arrest OR crime", gl: "mn", hl: "en" });

  // ── International orgs ──
  queries.push({ q: "site:unodc.org Mongolia drug narcotic trafficking heroin methamphetamine", gl: "mn", hl: "en" });
  queries.push({ q: "site:interpol.int Mongolia drug", gl: "mn", hl: "en" });
  queries.push({ q: "site:incb.org Mongolia narcotic drug", gl: "mn", hl: "en" });
  queries.push({ q: "site:thediplomat.com Mongolia drug narcotic crime smuggling", gl: "mn", hl: "en" });
  queries.push({ q: "site:state.gov Mongolia narcotics trafficking", gl: "mn", hl: "en" });
  queries.push({ q: "site:ocindex.net Mongolia", gl: "mn", hl: "en" });
  queries.push({ q: "site:eurasianet.org Mongolia drug narcotic", gl: "mn", hl: "en" });
  queries.push({ q: "site:jamestown.org Mongolia drug trafficking", gl: "mn", hl: "en" });

  // ── Academic / research sources ──
  queries.push({ q: "Mongolia drug trafficking research study academic 2024 2025 2026", gl: "mn", hl: "en" });

  // ── Google News search (recent articles, better for news sites) ──
  const newsQueries = [
    "Mongolia drug trafficking narcotics",
    "Mongolia drug arrest seizure customs",
    "Mongolia methamphetamine fentanyl bust",
    "Mongolia cannabis marijuana smuggling",
    "Монгол хар тамхи мансууруулах",
    "Монгол наркотик психотроп",
    "蒙古 毒品 贩毒 查获",
  ];

  for (const q of newsQueries) {
    try {
      const resp = await axios.post(
        "https://google.serper.dev/news",
        { q, num: 25, gl: "mn", hl: q.match(/[Ѐ-ӿ]/) ? "mn" : q.match(/[一-鿿]/) ? "zh-cn" : "en" },
        { headers: { "X-API-KEY": apiKey, "Content-Type": "application/json" }, timeout: 15000 }
      );

      const items = resp.data?.news || [];
      totalRaw += items.length;

      for (const r of items) {
        const key = r.link;
        if (seen.has(key)) continue;
        const combined = `${r.title} ${r.snippet || ""}`;
        if (!isMongoliaRelevant(r.link, r.title, r.snippet || "")) continue;
        if (!hasDrugKeyword(combined)) continue;
        seen.add(key);
        results.push({ title: r.title, link: r.link, snippet: r.snippet || "", date: r.date || "" });
      }
    } catch (err: any) {
      // News endpoint may not be available on free tier, silently skip
    }
  }

  console.log(`[Scraper] Running ${queries.length} Serper queries...`);

  let totalRaw = 0;
  for (const query of queries) {
    try {
      const resp = await axios.post(
        "https://google.serper.dev/search",
        { q: query.q, num: 25, gl: query.gl, hl: query.hl },
        {
          headers: {
            "X-API-KEY": apiKey,
            "Content-Type": "application/json",
          },
          timeout: 15000,
        }
      );

      const organic = resp.data?.organic || [];
      totalRaw += organic.length;

      for (const r of organic) {
        const key = r.link;
        if (seen.has(key)) continue;

        const combined = `${r.title} ${r.snippet || ""}`;

        if (!isMongoliaRelevant(r.link, r.title, r.snippet || "")) continue;
        if (!hasDrugKeyword(combined)) continue;

        seen.add(key);
        results.push({
          title: r.title,
          link: r.link,
          snippet: r.snippet || "",
          date: r.date || "",
        });
      }
    } catch (err: any) {
      const status = err?.response?.status;
      if (status === 403 || status === 401) {
        console.error("[Scraper] Serper API key invalid or expired");
        break;
      }
      if (status === 400) {
        console.error(`[Scraper] Serper query rejected (free tier limit): ${query.q.substring(0, 60)}...`);
        continue;
      }
      console.error(`[Scraper] Serper query failed: ${String(err).substring(0, 100)}`);
    }
  }

  console.log(`[Scraper] Serper: ${totalRaw} raw → ${results.length} Mongolia drug-related (${queries.length} queries)`);
  return results;
}

// ── ScrapingBee Google Search (best for Mongolian/Cyrillic queries) ─────────
async function searchWithScrapingbee(): Promise<SerperResult[]> {
  const apiKey = process.env.SCRAPINGBEE_API_KEY;
  if (!apiKey) {
    console.log("[Scraper] No SCRAPINGBEE_API_KEY — skipping ScrapingBee search");
    return [];
  }

  const results: SerperResult[] = [];
  const seen = new Set<string>();

  const queries: { search: string; language: string }[] = [];

  // Mongolian drug keywords on top news sites — ScrapingBee handles Cyrillic perfectly
  const mnDrug = "хар тамхи OR мансууруулах OR наркотик OR фентанил OR психотроп OR каннабис OR марихуана OR кокаин OR метамфетамин OR гашиш";

  for (const site of ["montsame.mn", "news.mn", "gogo.mn", "ikon.mn", "unuudur.mn", "24tsag.mn"]) {
    queries.push({ search: `site:${site} (${mnDrug})`, language: "mn" });
  }

  // English drug terms on Mongolian sites
  const enDrug = "drug OR narcotic OR trafficking OR meth OR fentanyl OR cannabis OR heroin OR cocaine OR seizure";
  for (const site of ["montsame.mn", "news.mn", "gogo.mn", "ikon.mn", "customs.gov.mn"]) {
    queries.push({ search: `site:${site} (${enDrug})`, language: "en" });
  }

  // Mongolia + drugs broad (international coverage)
  queries.push({ search: "Mongolia drug trafficking OR narcotics OR seizure OR methamphetamine", language: "en" });
  queries.push({ search: "Монгол хар тамхи OR мансууруулах OR наркотик", language: "mn" });

  // Chinese cross-border keywords
  queries.push({ search: "蒙古 毒品 OR 贩毒 OR 缉毒 OR 安纳咖 OR 中蒙 走私毒品", language: "zh" });

  console.log(`[Scraper] Running ${queries.length} ScrapingBee queries...`);

  for (const q of queries) {
    try {
      const searchEncoded = encodeURIComponent(q.search);
      const url = `https://app.scrapingbee.com/api/v1/store/google?api_key=${apiKey}&search=${searchEncoded}&language=${q.language}&nb_results=20`;

      const resp = await axios.get(url, { timeout: 20000 });
      const organic = resp.data?.organic_results || [];

      for (const r of organic) {
        const key = r.url;
        if (seen.has(key)) continue;

        const combined = `${r.title || ""} ${r.snippet || ""}`;

        if (!isMongoliaRelevant(r.url, r.title || "", r.snippet || "")) continue;
        if (!hasDrugKeyword(combined)) continue;

        seen.add(key);
        results.push({
          title: r.title || "",
          link: r.url,
          snippet: r.snippet || "",
          date: r.date || r.published_date || "",
        });
      }
    } catch (err: any) {
      const status = err?.response?.status;
      if (status === 401 || status === 403) {
        console.error("[Scraper] ScrapingBee API key invalid or expired");
        break;
      }
      console.error(`[Scraper] ScrapingBee query failed: ${String(err).substring(0, 100)}`);
    }
  }

  console.log(`[Scraper] ScrapingBee returned ${results.length} Mongolia drug-related results`);
  return results;
}

// ── Direct site search (free, no API key) ───────────────────────────────────
interface SiteSearchConfig {
  name: string;
  searchUrl: string;
  linkPattern: RegExp;
  linkPrefix: string;
  linkFilter?: (href: string) => boolean;
}

const SITE_SEARCH_CONFIGS: SiteSearchConfig[] = [
  {
    name: "ikon.mn",
    searchUrl: "https://ikon.mn/search?q=",
    linkPattern: /href="(\/n\/[^"]+)"/g,
    linkPrefix: "https://ikon.mn",
  },
  {
    name: "montsame.mn",
    searchUrl: "https://montsame.mn/mn/search?q=",
    linkPattern: /href="(\/mn\/read\/[^"]+)"/g,
    linkPrefix: "https://montsame.mn",
  },
  {
    name: "gogo.mn",
    searchUrl: "https://gogo.mn/search?q=",
    linkPattern: /<a[^>]*href="(\/[^"]+)"[^>]*>/gi,
    linkPrefix: "https://gogo.mn",
    linkFilter: (href: string) => href.length > 4 && !href.includes("?"),
  },
];

async function searchSiteDirectly(config: SiteSearchConfig, query: string): Promise<SerperResult[]> {
  try {
    const encoded = encodeURIComponent(query);
    const resp = await axios.get(config.searchUrl + encoded, {
      headers: {
        "User-Agent": USER_AGENT,
        Accept: "text/html,application/xhtml+xml",
        "Accept-Language": "mn-MN,mn;q=0.9",
      },
      timeout: 15000,
      validateStatus: (s) => s < 400,
    });

    const html: string = resp.data;
    const results: SerperResult[] = [];
    const seen = new Set<string>();
    let match: RegExpExecArray | null;

    config.linkPattern.lastIndex = 0;
    while ((match = config.linkPattern.exec(html)) !== null) {
      let href = match[1];
      // Strip fragment and query params for dedup
      const cleanHref = href.replace(/[#?].*$/, "");
      if (seen.has(cleanHref)) continue;
      if (config.linkFilter && !config.linkFilter(href)) continue;

      const fullUrl = href.startsWith("http") ? href : config.linkPrefix + href;
      const cleanUrl = fullUrl.replace(/#.*$/, "");

      // Extract wide surrounding text context (~600 chars around the link)
      const matchIdx = match.index;
      const contextStart = Math.max(0, matchIdx - 300);
      const contextEnd = Math.min(html.length, matchIdx + 400);
      let context = html.substring(contextStart, contextEnd)
        .replace(/<script[\s\S]*?<\/script>/gi, "")
        .replace(/<style[\s\S]*?<\/style>/gi, "")
        .replace(/<img[^>]*>/gi, "")
        .replace(/<[^>]*>/g, " ")
        .replace(/&[a-z]+;/gi, " ")
        .replace(/&\w+;/g, "")
        .replace(/\s+/g, " ")
        .trim();

      // Filter: the context around the link must contain drug keywords
      // (wider context than the old per-title check)
      if (!hasDrugKeyword(context)) continue;
      seen.add(cleanHref);

      // Extract a reasonable title: first 15-120 chars of cleaned context
      const title = context.length > 15 ? context.substring(0, 120).trim() : context;

      results.push({ title, link: cleanUrl, snippet: context.substring(0, 300), date: "" });
    }

    return results;
  } catch (err: any) {
    const status = err?.response?.status || "network";
    const msg = err?.code || String(err).substring(0, 80);
    console.error(`[Scraper] ${config.name} direct search FAILED (status=${status}, err=${msg})`);
    return [];
  }
}

async function searchAllSitesDirectly(): Promise<SerperResult[]> {
  const allResults: SerperResult[] = [];
  const queries = [
    "хар тамхи",
    "мансууруулах бодис",
    "наркотик",
    "фентанил",
    "психотроп",
    "каннабис",
    "марихуана",
    "кокаин",
    "метамфетамин",
    "гашиш",
    "КНБ",
    "анага бодис",
    "drug trafficking",
    "narcotic smuggling",
  ];

  // Search a subset of queries per site to avoid overwhelming
  for (const config of SITE_SEARCH_CONFIGS) {
    const queryBatch = queries.slice(0, 5).join(" OR ");
    const results = await searchSiteDirectly(config, queryBatch);
    console.log(`[Scraper] ${config.name} direct search → ${results.length} results`);
    allResults.push(...results);
  }

  return allResults;
}

// ── RSS Feed parsing ────────────────────────────────────────────────────────
async function fetchAndParseRSS(feedUrl: string): Promise<SerperResult[]> {
  try {
    const resp = await axios.get(feedUrl, {
      headers: { "User-Agent": USER_AGENT, Accept: "application/rss+xml,application/xml,text/xml,*/*" },
      timeout: 15000,
      validateStatus: (s) => s < 400,
    });

    const xml: string = resp.data;
    const results: SerperResult[] = [];

    // Parse RSS items with regex (avoids adding an XML dependency)
    const itemRegex = /<item>([\s\S]*?)<\/item>/gi;
    let match: RegExpExecArray | null;

    while ((match = itemRegex.exec(xml)) !== null) {
      const itemXml = match[1];
      const titleMatch = itemXml.match(/<title>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?<\/title>/i);
      const linkMatch = itemXml.match(/<link>\s*([^\s<]+)\s*<\/link>/i);
      const descMatch = itemXml.match(/<description>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?<\/description>/i);
      const dateMatch = itemXml.match(/<pubDate>([\s\S]*?)<\/pubDate>/i);

      if (!titleMatch || !linkMatch) continue;
      const title = titleMatch[1].trim();
      const link = linkMatch[1].trim();
      const desc = descMatch ? descMatch[1].replace(/<[^>]*>/g, "").trim().substring(0, 500) : "";
      const combined = `${title} ${desc}`;

      if (!hasDrugKeyword(combined)) continue;

      let date = "";
      if (dateMatch) {
        try {
          date = new Date(dateMatch[1]).toISOString().split("T")[0];
        } catch {
          date = new Date().toISOString().split("T")[0];
        }
      } else {
        date = new Date().toISOString().split("T")[0];
      }

      results.push({ title, link, snippet: desc, date });
    }

    return results;
  } catch (err: any) {
    console.error(`[Scraper] RSS ${feedUrl} failed: ${String(err).substring(0, 80)}`);
    return [];
  }
}

async function fetchAllRSS(): Promise<SerperResult[]> {
  const allResults: SerperResult[] = [];
  const results = await Promise.allSettled(RSS_FEEDS.map(fetchAndParseRSS));

  for (const r of results) {
    if (r.status === "fulfilled") {
      allResults.push(...r.value);
    }
  }

  console.log(`[Scraper] RSS feeds returned ${allResults.length} drug-related items`);
  return allResults;
}

// ── Fetch article page content + publication date ───────────────────────────
interface ArticlePage {
  content: string;
  date: string; // YYYY-MM-DD or empty
}

function extractDateFromHTML(html: string): string {
  // <meta property="article:published_time" content="2026-07-14T10:30:00+08:00">
  const metaMatch = html.match(/<meta\s[^>]*property="article:published_time"[^>]*content="([^"]+)"/i)
    || html.match(/<meta\s[^>]*name="pubdate"[^>]*content="([^"]+)"/i)
    || html.match(/<meta\s[^>]*name="publish_date"[^>]*content="([^"]+)"/i);
  if (metaMatch) {
    try {
      return new Date(metaMatch[1]).toISOString().split("T")[0];
    } catch { /* fall through */ }
  }

  // <time datetime="2026-07-14">...</time>
  const timeMatch = html.match(/<time[^>]*datetime="([^"]+)"/i);
  if (timeMatch) {
    try {
      return new Date(timeMatch[1]).toISOString().split("T")[0];
    } catch { /* fall through */ }
  }

  // Schema.org JSON-LD datePublished
  const jsonLdMatch = html.match(/"datePublished"\s*:\s*"([^"]+)"/);
  if (jsonLdMatch) {
    try {
      return new Date(jsonLdMatch[1]).toISOString().split("T")[0];
    } catch { /* fall through */ }
  }

  // Common Mongolian date patterns in visible text: 2026-07-14, 2026.07.14, 2026/07/14
  const dateRegex = /(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})/;
  const dateMatch = html.match(dateRegex);
  if (dateMatch) {
    try {
      const d = new Date(`${dateMatch[1]}-${dateMatch[2].padStart(2, "0")}-${dateMatch[3].padStart(2, "0")}`);
      if (!isNaN(d.getTime())) return d.toISOString().split("T")[0];
    } catch { /* fall through */ }
  }

  return "";
}

async function fetchArticlePage(url: string): Promise<ArticlePage> {
  try {
    const resp = await axios.get(url, {
      headers: {
        "User-Agent": USER_AGENT,
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "mn-MN,mn;q=0.9,en-US;q=0.8,zh-CN;q=0.6",
      },
      timeout: 12000,
      maxRedirects: 3,
      validateStatus: (s) => s < 400,
    });
    const html: string = resp.data;

    // Extract date
    const date = extractDateFromHTML(html);

    // Extract text content
    const bodyText = html
      .replace(/<script[\s\S]*?<\/script>/gi, "")
      .replace(/<style[\s\S]*?<\/style>/gi, "")
      .replace(/<nav[\s\S]*?<\/nav>/gi, "")
      .replace(/<footer[\s\S]*?<\/footer>/gi, "")
      .replace(/<header[\s\S]*?<\/header>/gi, "")
      .replace(/<[^>]*>/g, " ")
      .replace(/&[a-z]+;/gi, " ")
      .replace(/\s+/g, " ")
      .trim()
      .substring(0, 3000);

    return { content: bodyText, date };
  } catch {
    return { content: "", date: "" };
  }
}

// ── Main: combine Serper + RSS → enriched articles ─────────────────────────
export async function scrapeAllSites(): Promise<ScrapedArticle[]> {
  const allRaw: SerperResult[] = [];
  const seenLinks = new Set<string>();

  // Run Serper + ScrapingBee + RSS in parallel
  const searchResults = await Promise.allSettled([
    searchWithSerper(),
    searchWithScrapingbee(),
    fetchAllRSS(),
  ]);

  const methodNames = ["Serper", "ScrapingBee", "RSS"];
  for (let i = 0; i < searchResults.length; i++) {
    const result = searchResults[i];
    if (result.status === "fulfilled") {
      console.log(`[Scraper] ${methodNames[i]}: ${result.value.length} results`);
      for (const r of result.value) {
        if (!seenLinks.has(r.link)) {
          seenLinks.add(r.link);
          allRaw.push(r);
        }
      }
    } else {
      console.error(`[Scraper] ${methodNames[i]} REJECTED: ${String(result.reason).substring(0, 120)}`);
    }
  }

  if (allRaw.length === 0) {
    console.log("[Scraper] No real articles found");
    return [];
  }

  console.log(`[Scraper] Total unique articles: ${allRaw.length}. Fetching content + dates...`);

  // Fetch full content + real publication dates for top articles
  const topResults = allRaw.slice(0, 60);
  const pageResults = await Promise.allSettled(
    topResults.map((r) => fetchArticlePage(r.link))
  );

  const articles: ScrapedArticle[] = [];
  for (let i = 0; i < topResults.length; i++) {
    const r = topResults[i];
    const pr = pageResults[i];
    const page = pr.status === "fulfilled" ? (pr as PromiseFulfilledResult<ArticlePage>).value : { content: "", date: "" };
    const fullText = `${r.title} ${r.snippet} ${page.content}`;
    const domain = extractDomain(r.link);
    const matched = extractMatchedKeywords(fullText);

    // Only use page-extracted date or today (Serper dates are indexed dates, not publish dates)
    const finalDate = page.date || new Date().toISOString().split("T")[0];

    articles.push({
      title: r.title,
      originalTitle: r.title,
      url: r.link,
      date: finalDate,
      siteName: domain || "Unknown",
      siteUrl: domain,
      summary: r.snippet.substring(0, 500),
      category: "实时采集",
      riskLevel: matched.length > 3 ? "High" : matched.length > 1 ? "Medium" : "Low",
      entities: { locations: [], organizations: [], suspects: "" },
      details: { seizureAmount: "", traffickingRoute: "", penalties: "" },
      matchedKeywords: matched,
    });
  }

  console.log(`[Scraper] Final: ${articles.length} real articles with keyword matches`);
  return articles;
}

export { hasDrugKeyword, DRUG_KEYWORDS_MN, DRUG_KEYWORDS_EN, DRUG_KEYWORDS_ZH, searchWithSerper, searchWithScrapingbee, searchAllSitesDirectly, fetchAllRSS };
