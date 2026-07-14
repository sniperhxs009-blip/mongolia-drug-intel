/**
 * Mongolian Drug News Web Scraper
 * Scrapes Mongolian news/media sites for drug-related articles.
 * Uses RSS feeds, search endpoints, and direct page parsing with cheerio.
 */
import axios from "axios";
import * as cheerio from "cheerio";

const USER_AGENT =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

const DRUG_KEYWORDS_MN = [
  "мансууруулах", "хар тамхи", "наркотик", "фентанил", "психотроп",
  "каннабис", "марихуан", "кокаин", "метамфетамин", "амфетамин",
  "катинон", "мефедрон", "гашиш", "КНБ", "анага бодис",
  "кофеин натри бензоат", "эфедрин", "хууль бус эргэлт",
  "гаалийн илрүүлэлт", "хил хамгаалах",
];

const DRUG_KEYWORDS_EN = [
  "drug", "narcotic", "trafficking", "seizure", "bust", "smuggling",
  "opioid", "fentanyl", "meth", "cocaine", "heroin", "cannabis",
  "cartel", "arrest", "raid", "anti-drug", "illicit",
  "UNODC", "interpol", "methamphetamine", "ecstasy",
  "drug lord", "drug dealer", "drug network",
];

const DRUG_KEYWORDS_ZH = [
  "毒品", "贩毒", "缉毒", "禁毒", "走私毒品", "跨境贩毒",
  "吸毒", "海洛因", "冰毒", "吗啡", "摇头丸", "查获", "缴获", "抓捕", "捣毁",
  "安纳咖", "苯甲酸钠咖啡因", "海关", "边防",
];

function hasDrugKeyword(text: string): boolean {
  const lower = text.toLowerCase();
  return (
    DRUG_KEYWORDS_MN.some((kw) => lower.includes(kw)) ||
    DRUG_KEYWORDS_EN.some((kw) => lower.includes(kw)) ||
    DRUG_KEYWORDS_ZH.some((kw) => lower.includes(kw))
  );
}

async function fetchHTML(url: string): Promise<string | null> {
  try {
    const resp = await axios.get(url, {
      headers: {
        "User-Agent": USER_AGENT,
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "mn-MN,mn;q=0.9,en-US;q=0.8,zh-CN;q=0.6",
      },
      timeout: 10000,
      maxRedirects: 3,
      validateStatus: (s) => s < 400,
    });
    return resp.data;
  } catch {
    return null;
  }
}

async function fetchRSS(url: string): Promise<string | null> {
  try {
    const resp = await axios.get(url, {
      headers: {
        "User-Agent": USER_AGENT,
        Accept: "application/rss+xml,application/xml,text/xml,*/*",
      },
      timeout: 10000,
      maxRedirects: 3,
      validateStatus: (s) => s < 400,
    });
    return resp.data;
  } catch {
    return null;
  }
}

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

/**
 * Scrape MONTSAME national news agency
 */
async function scrapeMontsame(): Promise<ScrapedArticle[]> {
  const articles: ScrapedArticle[] = [];
  const baseUrl = "https://montsame.mn";

  try {
    // Try the law category page
    const html = await fetchHTML(`${baseUrl}/mn/more/36`);
    if (!html) return articles;

    const $ = cheerio.load(html);
    const links = $("a[href*='/read/']").toArray();

    for (const el of links.slice(0, 15)) {
      const href = $(el).attr("href");
      const titleText = $(el).text().trim();
      if (!href || !titleText || titleText.length < 10) continue;
      if (!hasDrugKeyword(titleText)) continue;

      const fullUrl = href.startsWith("http") ? href : baseUrl + href;
      const articleHtml = await fetchHTML(fullUrl);
      if (!articleHtml) continue;

      const $$ = cheerio.load(articleHtml);
      const pageTitle = $$("title").text().replace(/Montsame|МОНЦАМЭ|News|Мэдээ/gi, "").trim();
      const bodyText = $$("article, .article-content, .news-content, main").text().trim().substring(0, 2000);
      const dateMatch = bodyText.match(/(\d{4}[-/.]\d{2}[-/.]\d{2})/);

      const matched: string[] = [];
      DRUG_KEYWORDS_MN.forEach((kw) => {
        if ((pageTitle + bodyText).toLowerCase().includes(kw)) matched.push(kw);
      });
      DRUG_KEYWORDS_EN.forEach((kw) => {
        if ((pageTitle + bodyText).toLowerCase().includes(kw)) matched.push(kw);
      });

      articles.push({
        title: pageTitle || titleText,
        originalTitle: titleText,
        url: fullUrl,
        date: dateMatch ? dateMatch[1] : new Date().toISOString().split("T")[0],
        siteName: "蒙通社 MONTSAME",
        siteUrl: "montsame.mn",
        category: "媒体新闻",
        riskLevel: matched.length > 3 ? "High" : "Medium",
        summary: bodyText.substring(0, 300),
        entities: { locations: [], organizations: [], suspects: "" },
        details: { seizureAmount: "", traffickingRoute: "", penalties: "" },
        matchedKeywords: matched.slice(0, 8),
      });
    }
  } catch {
    // silently fail
  }

  return articles;
}

/**
 * Scrape Ikon.mn news site
 */
async function scrapeIkon(): Promise<ScrapedArticle[]> {
  const articles: ScrapedArticle[] = [];

  try {
    const html = await fetchHTML("https://ikon.mn");
    if (!html) return articles;

    const $ = cheerio.load(html);
    const links = $("a[href*='/n/']").toArray();

    for (const el of links.slice(0, 20)) {
      const href = $(el).attr("href");
      const titleText = $(el).text().trim();
      if (!href || !titleText || titleText.length < 10) continue;
      if (!hasDrugKeyword(titleText)) continue;

      const fullUrl = href.startsWith("http") ? href : "https://ikon.mn" + href;
      const articleHtml = await fetchHTML(fullUrl);
      if (!articleHtml) continue;

      const $$ = cheerio.load(articleHtml);
      const bodyText = $$("article, .article-content, .news-content, .content").text().trim().substring(0, 2000);
      const dateMatch = bodyText.match(/(\d{4}[-/.]\d{2}[-/.]\d{2})/);

      const matched: string[] = [];
      DRUG_KEYWORDS_MN.forEach((kw) => {
        if ((titleText + bodyText).toLowerCase().includes(kw)) matched.push(kw);
      });

      if (matched.length > 0) {
        articles.push({
          title: titleText,
          originalTitle: titleText,
          url: fullUrl,
          date: dateMatch ? dateMatch[1] : new Date().toISOString().split("T")[0],
          siteName: "IKON.MN",
          siteUrl: "ikon.mn",
          category: "媒体新闻",
          riskLevel: matched.length > 3 ? "High" : "Medium",
          summary: bodyText.substring(0, 300),
          entities: { locations: [], organizations: [], suspects: "" },
          details: { seizureAmount: "", traffickingRoute: "", penalties: "" },
          matchedKeywords: matched.slice(0, 8),
        });
      }
    }
  } catch {
    // silently fail
  }

  return articles;
}

/**
 * Scrape GOGO.MN news site
 */
async function scrapeGogo(): Promise<ScrapedArticle[]> {
  const articles: ScrapedArticle[] = [];

  try {
    const html = await fetchHTML("https://gogo.mn");
    if (!html) return articles;

    const $ = cheerio.load(html);
    const links = $("a").toArray();

    for (const el of links) {
      const href = $(el).attr("href");
      const titleText = $(el).text().trim();
      if (!href || !titleText || titleText.length < 15) continue;
      if (!hasDrugKeyword(titleText)) continue;

      const fullUrl = href.startsWith("http") ? href : "https://gogo.mn" + href;
      articles.push({
        title: titleText,
        originalTitle: titleText,
        url: fullUrl,
        date: new Date().toISOString().split("T")[0],
        siteName: "GOGO.MN",
        siteUrl: "gogo.mn",
        category: "媒体新闻",
        riskLevel: "Medium",
        summary: "",
        entities: { locations: [], organizations: [], suspects: "" },
        details: { seizureAmount: "", traffickingRoute: "", penalties: "" },
        matchedKeywords: [],
      });
    }
  } catch {
    // silently fail
  }

  return articles;
}

/**
 * Scrape See.mn news site
 */
async function scrapeSee(): Promise<ScrapedArticle[]> {
  const articles: ScrapedArticle[] = [];

  try {
    // See.mn has article URLs like see.mn/{id}.html
    // Scrape the homepage for links
    const html = await fetchHTML("https://see.mn");
    if (!html) return articles;

    const $ = cheerio.load(html);
    const links = $("a[href*='.html']").toArray();

    for (const el of links.slice(0, 15)) {
      const href = $(el).attr("href");
      const titleText = $(el).text().trim();
      if (!href || !titleText || titleText.length < 10) continue;
      if (!hasDrugKeyword(titleText)) continue;

      const fullUrl = href.startsWith("http") ? href : "https://see.mn" + href;
      articles.push({
        title: titleText,
        originalTitle: titleText,
        url: fullUrl,
        date: new Date().toISOString().split("T")[0],
        siteName: "See.mn",
        siteUrl: "see.mn",
        category: "媒体新闻",
        riskLevel: "Medium",
        summary: "",
        entities: { locations: [], organizations: [], suspects: "" },
        details: { seizureAmount: "", traffickingRoute: "", penalties: "" },
        matchedKeywords: [],
      });
    }
  } catch {
    // silently fail
  }

  return articles;
}

/**
 * Main scraping function - runs all site scrapers in parallel
 */
export async function scrapeAllSites(): Promise<ScrapedArticle[]> {
  const results = await Promise.allSettled([
    scrapeMontsame(),
    scrapeIkon(),
    scrapeGogo(),
    scrapeSee(),
  ]);

  const allArticles: ScrapedArticle[] = [];
  const seenUrls = new Set<string>();

  for (const result of results) {
    if (result.status === "fulfilled") {
      for (const article of result.value) {
        if (!seenUrls.has(article.url)) {
          seenUrls.add(article.url);
          allArticles.push(article);
        }
      }
    }
  }

  console.log(`[Scraper] Found ${allArticles.length} drug-related articles from ${results.length} sites`);
  return allArticles;
}

export { hasDrugKeyword, DRUG_KEYWORDS_MN, DRUG_KEYWORDS_EN, DRUG_KEYWORDS_ZH };
