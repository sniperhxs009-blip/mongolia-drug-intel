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
  "drug", "narcotic", "trafficking", "seizure", "smuggling",
  "opioid", "fentanyl", "meth", "cocaine", "heroin", "cannabis",
  "cartel", "arrest", "raid", "anti-drug", "illicit",
  "UNODC", "interpol", "methamphetamine", "ecstasy",
];

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
  return (
    DRUG_KEYWORDS_MN.some((kw) => lower.includes(kw)) ||
    DRUG_KEYWORDS_EN.some((kw) => lower.includes(kw)) ||
    DRUG_KEYWORDS_ZH.some((kw) => lower.includes(kw))
  );
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

// ── Domain filtering: only Mongolian (.mn) + known international orgs ────────
const ALLOWED_DOMAINS = [
  ".mn",
  "unodc.org",
  "interpol.int",
  "nncc626.com",
  "mps.gov.cn",
];

function isAllowedDomain(url: string): boolean {
  return ALLOWED_DOMAINS.some((d) => {
    try {
      return new URL(url).hostname.endsWith(d);
    } catch {
      return false;
    }
  });
}

// ── Serper.dev Google Search ────────────────────────────────────────────────
async function searchWithSerper(): Promise<SerperResult[]> {
  const apiKey = process.env.SERPER_API_KEY;
  if (!apiKey) {
    console.log("[Scraper] No SERPER_API_KEY — skipping Serper search");
    return [];
  }

  const results: SerperResult[] = [];
  const seen = new Set<string>();

  // Build optimized queries targeting ONLY Mongolian domains
  const mnKeywords = DRUG_KEYWORDS_MN.slice(0, 10).join(" OR ");
  const enKeywords = ["drug", "narcotic", "trafficking", "seizure", "meth", "fentanyl", "cannabis", "arrest", "smuggling"].join(" OR ");

  // Query batch targeting only .mn sites
  const queries: { q: string; gl: string; hl: string }[] = [];

  // Top Mongolian news sites with Mongolian keywords
  const topNewsDomains = [
    "montsame.mn", "ikon.mn", "news.mn", "gogo.mn",
    "unuudur.mn", "24tsag.mn", "itoim.mn", "eguur.mn",
    "olloo.mn", "ubn.mn", "time.mn", "fact.mn",
  ];
  for (const domain of topNewsDomains) {
    queries.push({
      q: `site:${domain} (${mnKeywords})`,
      gl: "mn",
      hl: "mn",
    });
  }

  // Top news sites with English keywords
  for (const domain of ["montsame.mn", "news.mn", "ikon.mn"]) {
    queries.push({
      q: `site:${domain} (${enKeywords})`,
      gl: "mn",
      hl: "en",
    });
  }

  // Government/enforcement sites with Mongolian keywords
  const govDomains = [
    "customs.gov.mn", "police.gov.mn", "bpo.gov.mn",
    "mojha.gov.mn", "nema.gov.mn", "mongolia.gov.mn",
  ];
  for (const domain of govDomains) {
    queries.push({
      q: `site:${domain} (${mnKeywords})`,
      gl: "mn",
      hl: "mn",
    });
  }

  // UNODC + Interpol: Mongolia-specific drug pages
  queries.push({
    q: 'site:unodc.org Mongolia drug narcotic trafficking',
    gl: "mn",
    hl: "en",
  });
  queries.push({
    q: 'site:interpol.int Mongolia drug',
    gl: "mn",
    hl: "en",
  });

  // China anti-drug: cross-border Mongolia
  queries.push({
    q: 'site:nncc626.com 蒙古 毒品 OR 安纳咖 OR 贩毒',
    gl: "cn",
    hl: "zh-cn",
  });

  console.log(`[Scraper] Running ${queries.length} Serper queries...`);

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
      for (const r of organic) {
        const key = r.link;
        if (seen.has(key)) continue;

        // CRITICAL: only allow Mongolian domains + specific international orgs
        if (!isAllowedDomain(r.link)) continue;

        seen.add(key);

        const combined = `${r.title} ${r.snippet || ""}`;
        if (!hasDrugKeyword(combined)) continue;

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
      console.error(`[Scraper] Serper query failed: ${String(err).substring(0, 100)}`);
    }
  }

  console.log(`[Scraper] Serper returned ${results.length} drug-related .mn results`);
  return results;
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

// ── Fetch article page content for better keyword extraction ────────────────
async function fetchArticleContent(url: string): Promise<string> {
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
    // Extract text content with basic regex — lightweight, no cheerio needed
    const html: string = resp.data;
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
    return bodyText;
  } catch {
    return "";
  }
}

// ── Main: combine Serper + RSS → enriched articles ─────────────────────────
export async function scrapeAllSites(): Promise<ScrapedArticle[]> {
  const allRaw: SerperResult[] = [];
  const seenLinks = new Set<string>();

  // Run Serper search and RSS parsing in parallel
  const [serperResults, rssResults] = await Promise.all([
    searchWithSerper(),
    fetchAllRSS(),
  ]);

  // Merge: Serper first (higher quality), then RSS
  for (const r of [...serperResults, ...rssResults]) {
    if (!seenLinks.has(r.link)) {
      seenLinks.add(r.link);
      allRaw.push(r);
    }
  }

  if (allRaw.length === 0) {
    console.log("[Scraper] No real articles found");
    return [];
  }

  console.log(`[Scraper] Total unique articles: ${allRaw.length}. Fetching content...`);

  // Fetch full content for top articles (limit to avoid excessive requests)
  const topResults = allRaw.slice(0, 30);
  const contents = await Promise.allSettled(
    topResults.map((r) => fetchArticleContent(r.link))
  );

  const articles: ScrapedArticle[] = [];
  for (let i = 0; i < topResults.length; i++) {
    const r = topResults[i];
    const c = contents[i];
    const content = c.status === "fulfilled" ? (c as PromiseFulfilledResult<string>).value : "";
    const fullText = `${r.title} ${r.snippet} ${content}`;
    const domain = extractDomain(r.link);
    const matched = extractMatchedKeywords(fullText);

    articles.push({
      title: r.title,
      originalTitle: r.title,
      url: r.link,
      date: r.date || new Date().toISOString().split("T")[0],
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

export { hasDrugKeyword, DRUG_KEYWORDS_MN, DRUG_KEYWORDS_EN, DRUG_KEYWORDS_ZH };
