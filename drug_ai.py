"""
AI-powered drug article analyzer with two-stage pipeline.

Stage 1 (Fast): Context-aware pattern matching — catches obvious cases in <1ms
Stage 2 (AI): DeepSeek LLM semantic classification — real AI understanding
"""
import re
import json
import os
import hashlib
from drug_keywords import TIER1_KEYWORDS, TIER2_KEYWORDS, TIER3_KEYWORDS

# === DeepSeek API config ===
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"

# === STAGE 1: Context-Aware Pattern Matching ===

DRUG_PATTERNS = [
    # Quantity + drug
    (r'(\d+[\.,]?\d*\s*(?:кг|тонн|грамм|kg|ton|g|т|ш|ширхэг|кг-аар|тонноор))\s*(.+?(?:марихуан|каннабис|гашиш|кокаин|героин|опи[уй]|метамфетамин|амфетамин|мефедрон|эфедрон|фентанил|морфин|экстази|ЛСД|МДМА))', 15),
    # Seizure + drug
    (r'(?:изъят|конфискован|хураан авсан|баривчилсан|seized|confiscated|илрүүлсэн)\s*.+?(?:наркотик|марихуан|каннабис|гашиш|кокаин|героин|опи[уй]|метамфетамин|амфетамин|мефедрон|фентанил|drug|хар тамхи)', 12),
    # Drug trafficking phrases
    (r'(?:наркотрафик|drug trafficking|наркотик.*?(?:трафик|оборот)|незаконн.*?(?:оборот|трафик).*?наркотик|хар тамхи.*?(?:наймаа|худалдаа)|контрабанд.*?(?:наркотик|drug))', 10),
    # Drug + criminal case
    (r'(?:мансууруулах|сэтгэцэд нөлөө[тл]|хар тамхи|наркотик|narcotic|drug).{0,30}(?:гэмт хэрэг|зөрчил|хэрэг|crime|offence|case|хууль бус)', 8),
    # Anti-narcotics operation with results
    (r'(?:антинаркотическ|anti.narcotic|anti.drug).{0,50}(?:операц|operation).{0,100}(?:изъят|конфискован|изъято|seized|ликвидирован|пресечен|итог|результат)', 10),
    # Drug lab / production
    (r'(?:нарколаборатор|drug lab|нарко.{0,10}лаборатор|нууц лаборатори|подпольн.{0,20}(?:лаборатор|цех)|незаконн.{0,20}производств.{0,20}наркотик)', 12),
    # Drug cultivation
    (r'(?:посев|культивирован|выращиван|тариал|ургамал|plantat).{0,30}(?:опи[уй]|мак|конопл|каннабис|cannabis|poppy|нарко)', 8),
    # Cross-border drug smuggling
    (r'(?:хил|border|границ|гааль|customs).{0,40}(?:наркотик|drug|хар тамхи|мансууруулах|контрабанд)', 8),
    # Drug courier / mule
    (r'(?:наркокурьер|drug (?:courier|mule)|задержан.{0,20}(?:наркотик|drug)|(?:наркотик|drug).{0,20}задержан)', 10),
    # Drug overdose / death
    (r'(?:передозировк|overdose|отравлен.{0,20}наркотик|наркотическ.{0,20}(?:отравлен|смерт|погиб))', 10),
    # Drug market/price
    (r'(?:наркорынок|drug market|стоимость.{0,20}(?:наркотик|drug)|цена.{0,20}(?:наркотик|drug)|(?:наркотик|drug).{0,20}(?:рынок|стоимость|цена))', 8),
]

# Sources known to have "drug" boilerplate on every page
# Their articles need extra scrutiny — must have operational details, not just keywords
BOILERPLATE_SOURCES = [
    "unodc.org", "United Nations Office on Drugs and Crime",
    "odkb-csto.org", "CSTO/ODKB", "CSTO",
]


def stage1_analyze(title, content):
    """Fast pattern matching. Returns scores and matched details."""
    text = f"{title} {content}"
    text_lower = text.lower()
    title_lower = title.lower()

    total_score = 0
    matched_patterns = []
    details = []

    for pattern, weight in DRUG_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            total_score += weight
            matched_patterns.append(pattern[:80])
            if isinstance(matches[0], tuple):
                details.append(f"Pattern: {matches[0][0][:120]}")
            else:
                details.append(f"Pattern: {str(matches[0])[:120]}")

    t1_matches = [kw for kw in TIER1_KEYWORDS if kw.lower() in text_lower]
    unique_t1 = len(set(t1_matches))
    total_score += unique_t1 * 5

    t2_matches = [kw for kw in TIER2_KEYWORDS if kw.lower() in text_lower]
    unique_t2 = len(set(t2_matches))
    total_score += unique_t2 * 3

    has_strong = unique_t1 > 0 or unique_t2 > 0
    if has_strong:
        t3_matches = [kw for kw in TIER3_KEYWORDS if kw.lower() in text_lower]
        total_score += len(set(t3_matches)) * 1

    title_t1 = len([kw for kw in TIER1_KEYWORDS if kw.lower() in title_lower])
    title_t2 = len([kw for kw in TIER2_KEYWORDS if kw.lower() in title_lower])
    title_hits = title_t1 + title_t2 + len([kw for kw in TIER3_KEYWORDS if kw.lower() in title_lower])
    if title_hits > 0:
        total_score += 8
    if title_t1 > 0:
        total_score += 10

    return {
        "score": total_score,
        "pattern_count": len(matched_patterns),
        "t1_count": unique_t1,
        "t2_count": unique_t2,
        "title_hits": title_hits > 0,
        "title_t1": title_t1 > 0,
        "details": details[:5],
        "all_keywords": list(set(t1_matches + t2_matches)),
    }


# === STAGE 2: DeepSeek AI Semantic Classification ===

DRUG_CLASSIFICATION_PROMPT = """You are a drug news classifier. Analyze this article and determine if it is ABOUT drug-related topics.

A drug-related article SPECIFICALLY discusses:
- Drug seizures, arrests, trafficking, smuggling operations with concrete details
- Drug production labs, cultivation sites being busted
- Specific drug crime court cases, convictions, investigations
- Drug abuse, addiction, overdose incidents
- Drug market trends, prices, new drug types emerging
- Anti-narcotics operations with specific results (quantities, arrests, locations)

NOT drug-related (return is_drug=false):
- Organizational boilerplate: generic descriptions of an organization's mission that mention "fighting drugs" among 10 other topics
- Website navigation pages, "About Us", annual reports that list drug topics as one of many areas
- Articles about general crime, corruption, or politics that mention drugs only in passing
- CSTO/ODKB meeting summaries that list "drug trafficking" as one agenda item among many
- UNODC pages that are about environmental crime, cybercrime, corruption, or police training (even if the footer mentions drugs)
- Diplomatic meetings, parliamentary speeches that recite organizational priorities

IMPORTANT: If the article is just an organizational page describing what an agency does, return is_drug=false.
Only return is_drug=true if the article's MAIN TOPIC is a specific drug-related event, operation, crime, or policy.

Title: {title}
Content: {content}

Respond with ONLY this JSON, no other text:
{{"is_drug": true/false, "confidence": 0.0-1.0, "drug_types": [], "action": "seizure/arrest/trafficking/production/policy/prevention/other/none", "summary": "one sentence in article's language", "reasoning": "why this is or is not drug-related"}}"""


class DrugAnalyzer:
    """Two-stage drug article analyzer with DeepSeek AI."""

    def __init__(self, api_key=None, api_base=None, model=None):
        self.api_key = api_key or DEEPSEEK_API_KEY
        self.api_base = api_base or DEEPSEEK_API_BASE
        self.model = model or DEEPSEEK_MODEL
        self._cache = {}

    def analyze(self, title, content, source=None):
        """Analyze article. Uses DeepSeek AI for all candidates when API key is set."""
        content_hash = hashlib.md5(f"{title}{content}{source or ''}".encode()).hexdigest()
        if content_hash in self._cache:
            return dict(self._cache[content_hash])

        s1 = stage1_analyze(title, content)

        # Source-specific anti-boilerplate check
        is_boilerplate_source = any(bs in (source or "") for bs in BOILERPLATE_SOURCES)

        if is_boilerplate_source:
            # UNODC/CSTO: every page has drug keywords in boilerplate.
            # Require operational details: at least 2 different specific drug names
            # OR 1 drug name + 2+ drug phrases + 2+ patterns
            has_strong_signal = (
                s1["t1_count"] >= 2 or
                (s1["t1_count"] >= 1 and s1["t2_count"] >= 2 and s1["pattern_count"] >= 2)
            )
        else:
            has_strong_signal = s1["t1_count"] >= 1 or s1["t2_count"] >= 2 or s1["pattern_count"] >= 2

        s1_is_drug = s1["score"] >= 12 and has_strong_signal
        s1_confidence = min(s1["score"] / 35.0, 1.0) if s1["score"] > 0 else 0.0

        result = {
            "is_drug": s1_is_drug,
            "confidence": round(s1_confidence, 2),
            "stage": "fast",
            "score": s1["score"],
            "patterns": s1["pattern_count"],
            "t1_count": s1["t1_count"],
            "t2_count": s1["t2_count"],
            "keywords": s1["all_keywords"],
            "title_hit": s1["title_hits"],
            "details": s1["details"],
            "drug_types": [],
            "action": "",
            "summary": "",
            "reasoning": "",
        }

        # Stage 2: DeepSeek AI analysis
        # Run AI when: (a) article passes Stage 1, OR (b) article has some drug signals (score >= 5)
        can_use_ai = bool(self.api_key)
        needs_ai = s1["score"] >= 5

        if can_use_ai and needs_ai:
            ai_result = self._ai_analyze(title, content)
            if ai_result:
                result["is_drug"] = ai_result.get("is_drug", result["is_drug"])
                result["confidence"] = ai_result.get("confidence", result["confidence"])
                result["stage"] = "ai"
                result["drug_types"] = ai_result.get("drug_types", [])
                result["action"] = ai_result.get("action", "")
                result["summary"] = ai_result.get("summary", "")
                result["reasoning"] = ai_result.get("reasoning", "")

        # Override: drug name in title = almost certainly drug-related
        if not result["is_drug"] and s1["title_t1"]:
            result["is_drug"] = True
            result["confidence"] = 0.85
            result["stage"] = "override"

        # Override: 2+ drug names + operational details
        if not result["is_drug"] and s1["t1_count"] >= 2 and s1["pattern_count"] >= 1:
            result["is_drug"] = True
            result["confidence"] = min(s1["score"] / 30.0, 0.95)
            result["stage"] = "override"

        self._cache[content_hash] = result
        return result

    def _ai_analyze(self, title, content):
        """Call DeepSeek API for semantic drug classification."""
        try:
            prompt = DRUG_CLASSIFICATION_PROMPT.format(
                title=title[:300],
                content=content[:1500]
            )

            import requests
            resp = requests.post(
                f"{self.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 300,
                },
                timeout=20,
            )

            if resp.status_code == 200:
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                json_match = re.search(r'\{.*\}', text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
        except Exception:
            pass
        return None

    def batch_analyze(self, articles):
        """Analyze multiple articles."""
        results = []
        for art in articles:
            title = art.get("title", "")
            content = art.get("content", "")
            source = art.get("source", "")
            result = self.analyze(title, content, source)
            art["drug_analysis"] = result
            results.append(art)
        return results

    def filter_drug_articles(self, articles, min_confidence=0.5):
        """Filter and sort articles by drug relevance."""
        analyzed = self.batch_analyze(articles)
        drug_articles = [
            a for a in analyzed
            if a.get("drug_analysis", {}).get("is_drug")
            and a.get("drug_analysis", {}).get("confidence", 0) >= min_confidence
        ]
        drug_articles.sort(key=lambda x: -x.get("drug_analysis", {}).get("confidence", 0))
        return drug_articles
