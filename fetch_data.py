"""
众智创新 · 金属价格实时追踪
"""

import json
import os
import datetime
import urllib.request
import urllib.parse
import urllib.error
import ssl

METALS_DEV_API_KEY = os.environ.get("METALS_DEV_API_KEY", "")
NEWS_API_KEY       = os.environ.get("NEWS_API_KEY",        "")
TWITTER_BEARER     = os.environ.get("TWITTER_BEARER",      "")
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY",   "")

METALS = {
    "gold":      {"name": "黄金 Gold",       "unit": "USD/盎司 oz"},
    "silver":    {"name": "白银 Silver",      "unit": "USD/盎司 oz"},
    "platinum":  {"name": "铂 Platinum",      "unit": "USD/盎司 oz"},
    "palladium": {"name": "钯 Palladium",     "unit": "USD/盎司 oz"},
    "copper":    {"name": "铜 Copper",        "unit": "USD/吨 mt"},
    "aluminum":  {"name": "铝 Aluminum",      "unit": "USD/吨 mt"},
    "nickel":    {"name": "镍 Nickel",        "unit": "USD/吨 mt"},
    "zinc":      {"name": "锌 Zinc",          "unit": "USD/吨 mt"},
    "lead":      {"name": "铅 Lead",          "unit": "USD/吨 mt"},
    "lme_zinc":  {"name": "LME锌 Zinc 3M",   "unit": "USD/吨 mt"},
    "lme_nickel":{"name": "LME镍 Nickel 3M", "unit": "USD/吨 mt"},
    "lme_copper":{"name": "LME铜 Copper 3M", "unit": "USD/吨 mt"},
}

# ============================================================
#  新闻来源白名单（宽松匹配：来源名包含任一关键词即可）
# ============================================================
ALLOWED_SOURCE_KEYWORDS = [
    # 英文大型金融/财经媒体
    "reuters", "bloomberg", "financial times", "ft.com", "ftchinese",
    "wall street journal", "wsj", "new york times", "nytimes",
    "economist", "cnbc", "barron", "marketwatch", "bbc",
    "associated press", "ap news", "guardian",
    "mining.com", "kitco", "metals daily", "metal bulletin",
    "cbs news", "pbs",
    # 印度大型媒体（经常报道金属价格）
    "times of india", "economic times", "economictimes",
    "business line", "businessline", "livemint", "ndtv",
    # 中文大型金融媒体
    "财新", "caixin", "虎嗅", "huxiu", "第一财经", "yicai",
    "新浪财经", "sina", "证券时报", "21世纪", "经济观察",
    "界面", "jiemian", "澎湃", "thepaper",
    "华尔街见闻", "wallstreetcn", "金十", "jin10",
    "新华", "xinhua", "人民日报", "中国证券报",
    "上海有色", "smm", "南华早报", "scmp",
    "36kr", "36氪", "cnbeta",
    # 全球通讯社 & 商业新闻
    "globenewswire", "prnewswire", "business wire",
    "financial post", "seeking alpha", "investing.com",
    "oilprice", "scientific american",
]

def is_allowed_source(source_name):
    if not source_name:
        return False
    src = source_name.lower().strip()
    return any(kw in src for kw in ALLOWED_SOURCE_KEYWORDS)

# ============================================================
#  过滤：加密货币 + 明显无关内容
# ============================================================
CRYPTO_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency",
    "blockchain", "altcoin", "token", "defi", "nft", "web3",
    "dogecoin", "solana", "ripple", "xrp", "binance", "coinbase",
    "比特币", "以太坊", "加密货币", "虚拟货币", "数字货币", "区块链",
    "币圈", "代币", "挖矿", "矿机",
]

IRRELEVANT_KEYWORDS = [
    "creatine", "headphone", "sony headphone", "apple watch",
    "lakers", "nba score", "nfl score", "iphone deal",
    "netflix", "disney", "marvel", "video game", "fortnite",
    "ray-ban", "eye patch", "milanese loop", "spider-man",
]

def is_bad_news(title, desc=""):
    text = (title + " " + desc).lower()
    if any(kw in text for kw in CRYPTO_KEYWORDS):
        return True
    if any(kw in text for kw in IRRELEVANT_KEYWORDS):
        return True
    return False

# ============================================================
#  辅助函数
# ============================================================
def safe_request(url, headers=None, timeout=20, method="GET", data=None):
    try:
        if data:
            body = data.encode("utf-8")
            req = urllib.request.Request(url, data=body, method=method)
        else:
            req = urllib.request.Request(url, method=method)
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  ⚠ 请求失败: {url[:80]}... -> {e}")
        return None

def get_script_dir():
    return os.path.dirname(os.path.abspath(__file__))

# ============================================================
#  翻译：用 Claude API 把英文翻译成中文
# ============================================================
def translate_articles(articles):
    if not ANTHROPIC_API_KEY:
        print("  ⚠ 未设置 ANTHROPIC_API_KEY，跳过翻译")
        return articles

    en_items = [(i, a) for i, a in enumerate(articles) if a.get("lang") != "zh"]
    if not en_items:
        print("  ✅ 全部为中文新闻，无需翻译")
        return articles

    print(f"  🔄 正在翻译 {len(en_items)} 条英文新闻...")

    # 逐条翻译（更可靠）
    for idx, (i, a) in enumerate(en_items):
        title = a.get("title", "")
        desc = a.get("description", "")
        prompt = f"请将以下金融新闻标题和摘要翻译成中文，保持专业金融术语准确。只输出翻译结果，格式为：\n标题：翻译后的标题\n摘要：翻译后的摘要\n\n原文标题：{title}\n原文摘要：{desc}"

        payload = json.dumps({
            "model": "claude-sonnet-4-5",
            "max_tokens": 500,
            "messages": [{"role": "user", "content": prompt}]
        })

        result = safe_request(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
            data=payload,
            timeout=30,
        )

        if result and "content" in result:
            text = ""
            for block in result.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")

            # 解析翻译结果
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("标题：") or line.startswith("标题:"):
                    new_title = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                    if new_title:
                        articles[i]["title"] = new_title
                elif line.startswith("摘要：") or line.startswith("摘要:"):
                    new_desc = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                    if new_desc:
                        articles[i]["description"] = new_desc

            print(f"    ✅ 翻译完成 [{idx+1}/{len(en_items)}]: {articles[i]['title'][:40]}...")
        else:
            print(f"    ⚠ 翻译失败 [{idx+1}/{len(en_items)}]: {title[:40]}...")

    return articles

# ============================================================
#  1. 获取金属价格
# ============================================================
def fetch_prices():
    print("📊 正在获取金属价格...")
    url = f"https://api.metals.dev/v1/latest?api_key={METALS_DEV_API_KEY}&currency=USD&unit=toz"
    data = safe_request(url)
    prices = []
    if data and data.get("status") == "success":
        metals_data = data.get("metals", {})
        for code, info in METALS.items():
            price = metals_data.get(code)
            prices.append({"code": code, "name": info["name"], "price_usd": round(price, 2) if price else None, "unit": info["unit"]})
        print(f"  ✅ 获取到 {len(prices)} 种金属价格")
    else:
        print(f"  ❌ 价格 API 返回失败")
        for code, info in METALS.items():
            prices.append({"code": code, "name": info["name"], "price_usd": None, "unit": info["unit"]})
    return prices

# ============================================================
#  1b. 保存历史价格
# ============================================================
def save_history(prices):
    print("📈 正在更新历史价格...")
    path = os.path.join(get_script_dir(), "history.json")
    history = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except: pass
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    rec = {"date": today, "prices": {p["code"]: p["price_usd"] for p in prices if p["price_usd"]}}
    found = False
    for i, h in enumerate(history):
        if h.get("date") == today: history[i] = rec; found = True; break
    if not found: history.append(rec)
    history.sort(key=lambda x: x["date"])
    history = history[-60:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 历史记录已更新，共 {len(history)} 天数据")

# ============================================================
#  2. 获取新闻
# ============================================================
def fetch_news():
    print("📰 正在获取新闻...")
    all_raw = []

    # 中文新闻（多个关键词组合）
    zh_queries = ["黄金 价格", "白银 铜 价格", "贵金属", "有色金属 价格", "金属 市场 行情"]
    for q in zh_queries:
        url = f"https://newsapi.org/v2/everything?q={urllib.parse.quote(q)}&sortBy=publishedAt&pageSize=10&language=zh&apiKey={NEWS_API_KEY}"
        data = safe_request(url)
        if data and data.get("status") == "ok":
            for a in data.get("articles", []):
                title = a.get("title", "")
                desc = a.get("description") or ""
                source = a.get("source", {}).get("name", "")
                if not title or is_bad_news(title, desc): continue
                if not is_allowed_source(source):
                    print(f"    ⏭ 跳过非白名单来源: {source} — {title[:40]}")
                    continue
                all_raw.append({"title": title, "source": source, "url": a.get("url",""), "published": a.get("publishedAt",""), "description": desc[:200], "lang": "zh"})

    # 英文新闻
    en_queries = ["gold price", "silver price copper", "platinum palladium nickel price", "precious metals market", "base metals commodity"]
    for q in en_queries:
        url = f"https://newsapi.org/v2/everything?q={urllib.parse.quote(q)}&sortBy=publishedAt&pageSize=10&language=en&apiKey={NEWS_API_KEY}"
        data = safe_request(url)
        if data and data.get("status") == "ok":
            for a in data.get("articles", []):
                title = a.get("title", "")
                desc = a.get("description") or ""
                source = a.get("source", {}).get("name", "")
                if not title or is_bad_news(title, desc): continue
                if not is_allowed_source(source):
                    print(f"    ⏭ 跳过非白名单来源: {source} — {title[:40]}")
                    continue
                all_raw.append({"title": title, "source": source, "url": a.get("url",""), "published": a.get("publishedAt",""), "description": desc[:200], "lang": "en"})

    # 去重 + 排序 + 取前10
    seen = set()
    articles = []
    for a in all_raw:
        if a["title"] not in seen:
            seen.add(a["title"])
            articles.append(a)
    articles.sort(key=lambda x: x.get("published",""), reverse=True)
    articles = articles[:10]

    print(f"  📋 过滤后共 {len(articles)} 条新闻，开始翻译...")

    # 翻译英文新闻
    articles = translate_articles(articles)

    for a in articles:
        a.pop("lang", None)

    print(f"  ✅ 最终新闻: {len(articles)} 条")
    return articles

# ============================================================
#  3. 获取推文
# ============================================================
def fetch_tweets():
    print("🐦 Twitter API 需付费，已停用")
    return []
    print("🐦 正在获取推文...")
    query = urllib.parse.quote("(gold price OR silver price OR copper price) -crypto -bitcoin -is:retweet lang:en")
    url = f"https://api.twitter.com/2/tweets/search/recent?query={query}&max_results=10&tweet.fields=created_at,author_id,text"
    data = safe_request(url, headers={"Authorization": f"Bearer {TWITTER_BEARER}"})
    tweets = []
    if data and "data" in data:
        for t in data["data"]:
            txt = t.get("text","")
            if is_bad_news(txt): continue
            tweets.append({"text": txt, "created_at": t.get("created_at",""), "url": f"https://twitter.com/i/web/status/{t.get('id','')}"})
        print(f"  ✅ 获取到 {len(tweets)} 条推文")
    else:
        err = data.get("detail", data.get("title", str(data))) if data else "无响应"
        print(f"  ⚠ 推文获取失败: {err}")
    return tweets

# ============================================================
#  主函数
# ============================================================
def main():
    print("=" * 50)
    print(f"🚀 众智创新 · 金属价格实时追踪")
    print(f"   开始抓取 — {datetime.datetime.utcnow().isoformat()}Z")
    print("=" * 50)
    prices = fetch_prices()
    save_history(prices)
    result = {
        "updated_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "prices": prices, "news": fetch_news(), "tweets": fetch_tweets(),
    }
    out = os.path.join(get_script_dir(), "data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 数据已保存 — 价格:{len(result['prices'])} 新闻:{len(result['news'])} 推文:{len(result['tweets'])}")

if __name__ == "__main__":
    main()
