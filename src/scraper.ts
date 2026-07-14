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

    // Check international drug org domains
    for (const d of INTL_DRUG_DOMAINS) {
      if (host === d || host.endsWith("." + d)) return true;
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
    console.log("[Scraper] No SERPER_API_KEY — skipping Serper search");
    return [];
  }

  const results: SerperResult[] = [];
  const seen = new Set<string>();

  // Free tier: one site per query (no multi-site OR allowed)
  const queries: { q: string; gl: string; hl: string }[] = [];

  // 1) Each major Mongolian news site with English drug keywords
  const enDrug = "drug OR narcotic OR trafficking OR meth OR fentanyl OR cannabis OR heroin OR cocaine";
  const topMediaDomains = ["montsame.mn", "news.mn", "gogo.mn", "ikon.mn", "unuudur.mn"];
  for (const d of topMediaDomains) {
    queries.push({ q: `site:${d} ${enDrug}`, gl: "mn", hl: "en" });
  }

  // 2) Major news sites with Mongolian drug keywords (one at a time)
  const mnDrug = '"хар тамхи" OR мансууруулах OR наркотик OR фентанил OR психотроп';
  for (const d of ["montsame.mn", "news.mn", "gogo.mn", "ikon.mn"]) {
    queries.push({ q: `site:${d} ${mnDrug}`, gl: "mn", hl: "mn" });
  }

  // 3) Government sites (general search — drug content is rare here)
  for (const d of ["customs.gov.mn", "police.gov.mn", "bpo.gov.mn"]) {
    queries.push({ q: `site:${d} ${mnDrug}`, gl: "mn", hl: "mn" });
  }

  // 4) International orgs: Mongolia-specific drug pages
  queries.push({ q: "site:unodc.org Mongolia drug OR narcotic OR trafficking", gl: "mn", hl: "en" });
  queries.push({ q: "site:interpol.int Mongolia drug", gl: "mn", hl: "en" });

  // 5) Broad search: Mongolia + drug topics (catches The Diplomat, UNESCO, etc.)
  queries.push({ q: "Mongolia drug trafficking OR narcotics OR seizure OR methamphetamine", gl: "mn", hl: "en" });
  queries.push({ q: "Mongolia illicit drugs OR narcotic control OR cross-border smuggling", gl: "mn", hl: "en" });

  // 6) Chinese side: cross-border Mongolia drug news
  queries.push({ q: "site:nncc626.com 蒙古 OR 中蒙 OR 口岸 毒品 OR 安纳咖 OR 贩毒", gl: "cn", hl: "zh-cn" });

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

        const combined = `${r.title} ${r.snippet || ""}`;

        // Must be Mongolia-relevant AND contain drug keywords
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

  console.log(`[Scraper] Serper returned ${results.length} Mongolia drug-related results`);
  return results;
}

// ── Bing Search API (better for Mongolian/Cyrillic queries) ─────────────────
async function searchWithBing(): Promise<SerperResult[]> {
  const apiKey = process.env.BING_API_KEY;
  if (!apiKey) {
    console.log("[Scraper] No BING_API_KEY — skipping Bing search");
    return [];
  }

  const results: SerperResult[] = [];
  const seen = new Set<string>();

  // Bing is strong with non-English queries — focus on Mongolian keywords
  const queries: { q: string; mkt: string }[] = [];

  // Mongolian drug keywords on news sites
  const mnDrug = '("хар тамхи" OR мансууруулах OR наркотик OR фентанил OR психотроп OR каннабис OR марихуана OR кокаин OR метамфетамин OR гашиш)';

  for (const site of ["montsame.mn", "news.mn", "gogo.mn", "ikon.mn", "unuudur.mn", "24tsag.mn"]) {
    queries.push({ q: `site:${site} ${mnDrug}`, mkt: "mn-MN" });
  }

  // English drug terms on .mn domains (Bing handles .mn better than Google)
  const enDrug = "(drug OR narcotic OR trafficking OR meth OR fentanyl OR cannabis OR heroin OR cocaine OR seizure)";
  for (const site of ["montsame.mn", "news.mn", "gogo.mn", "ikon.mn", "customs.gov.mn", "police.gov.mn"]) {
    queries.push({ q: `site:${site} ${enDrug}`, mkt: "en-US" });
  }

  // Mongolia + drugs (broad, for international coverage Bing might have that Google missed)
  queries.push({ q: `Mongolia (drug OR narcotic OR trafficking OR methamphetamine)`, mkt: "en-US" });
  queries.push({ q: `Монгол (хар тамхи OR мансууруулах OR наркотик)`, mkt: "mn-MN" });

  // Chinese keywords for cross-border content
  queries.push({
    q: `site:nncc626.com OR site:mps.gov.cn 蒙古 毒品 OR 安纳咖 OR 贩毒`,
    mkt: "zh-CN",
  });

  console.log(`[Scraper] Running ${queries.length} Bing queries...`);

  for (const query of queries) {
    try {
      const resp = await axios.get("https://api.bing.microsoft.com/v7.0/search", {
        headers: {
          "Ocp-Apim-Subscription-Key": apiKey,
        },
        params: {
          q: query.q,
          count: 20,
          mkt: query.mkt,
        },
        timeout: 15000,
      });

      const webPages = resp.data?.webPages?.value || [];
      for (const r of webPages) {
        const key = r.url;
        if (seen.has(key)) continue;

        const combined = `${r.name} ${r.snippet || ""}`;

        if (!isMongoliaRelevant(r.url, r.name, r.snippet || "")) continue;
        if (!hasDrugKeyword(combined)) continue;

        seen.add(key);
        results.push({
          title: r.name,
          link: r.url,
          snippet: r.snippet || "",
          date: r.datePublished || "",
        });
      }
    } catch (err: any) {
      const status = err?.response?.status;
      if (status === 401 || status === 403) {
        console.error("[Scraper] Bing API key invalid or expired");
        break;
      }
      console.error(`[Scraper] Bing query failed: ${String(err).substring(0, 100)}`);
    }
  }

  console.log(`[Scraper] Bing returned ${results.length} Mongolia drug-related results`);
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

  // Run Serper, Bing, and RSS in parallel
  const [serperResults, bingResults, rssResults] = await Promise.all([
    searchWithSerper(),
    searchWithBing(),
    fetchAllRSS(),
  ]);

  // Merge: Serper first, then Bing, then RSS
  for (const r of [...serperResults, ...bingResults, ...rssResults]) {
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
