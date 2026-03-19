"""
众智创新 · 金属价格实时追踪
每天定时运行，把数据写入 data.json，并追加历史价格到 history.json
使用 Claude API 翻译英文新闻标题为中文
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

# ============================================================
#  金属列表
# ============================================================
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
#  新闻来源白名单（只接受大型金融新闻平台）
# ============================================================
ALLOWED_SOURCES = [
    # 英文大型金融媒体
    "reuters", "bloomberg", "financial times", "the wall street journal",
    "wsj", "the new york times", "nytimes", "the economist",
    "cnbc", "ft.com", "barron's", "barrons", "marketwatch",
    "the guardian", "bbc", "associated press", "ap news",
    "mining.com", "kitco", "metals daily",
    # 中文大型金融媒体
    "财新", "caixin", "虎嗅", "huxiu", "第一财经", "yicai",
    "新浪财经", "sina finance", "证券时报", "21世纪经济报道",
    "经济观察报", "界面新闻", "jiemian", "澎湃新闻", "thepaper",
    "华尔街见闻", "wallstreetcn", "金十数据", "jin10",
    "新华社", "xinhua", "人民日报", "中国证券报",
    "上海有色网", "smm", "南华早报", "scmp",
]

def is_allowed_source(source_name):
    """检查新闻来源是否在白名单中"""
    if not source_name:
        return False
    src = source_name.lower().strip()
    return any(allowed in src or src in allowed for allowed in ALLOWED_SOURCES)

# ============================================================
#  虚拟货币过滤
# ============================================================
CRYPTO_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency",
    "blockchain", "altcoin", "token", "defi", "nft", "web3",
    "dogecoin", "solana", "ripple", "xrp", "binance", "coinbase",
    "比特币", "以太坊", "加密货币", "虚拟货币", "数字货币", "区块链",
    "币圈", "代币", "挖矿", "矿机",
]

def is_crypto(title, desc=""):
    text = (title + " " + desc).lower()
    return any(kw in text for kw in CRYPTO_KEYWORDS)

# ============================================================
#  辅助函数
# ============================================================
def safe_request(url, headers=None, timeout=15, method="GET", data=None):
    try:
        req = urllib.request.Request(url, method=method)
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        ctx = ssl.create_default_context()
        body = data.encode("utf-8") if data else None
        with urllib.request.urlopen(req, body, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  ⚠ 请求失败: {url[:80]}... -> {e}")
        return None

def get_script_dir():
    return os.path.dirname(os.path.abspath(__file__))

# ============================================================
#  翻译函数：用 Claude API 把英文标题和摘要翻译成中文
# ============================================================
def translate_articles(articles):
    """批量翻译英文新闻标题和摘要为中文"""
    if not ANTHROPIC_API_KEY:
        print("  ⚠ 未设置 ANTHROPIC_API_KEY，跳过翻译")
        return articles

    # 筛选需要翻译的文章（非中文的）
    to_translate = []
    for i, a in enumerate(articles):
        if a.get("lang") != "zh":
            to_translate.append((i, a))

    if not to_translate:
        print("  ✅ 全部为中文新闻，无需翻译")
        return articles

    print(f"  🔄 正在翻译 {len(to_translate)} 条英文新闻...")

    # 构建翻译请求的文本
    lines = []
    for idx, (i, a) in enumerate(to_translate):
        lines.append(f"[{idx}] 标题: {a['title']}")
        if a.get("description"):
            lines.append(f"[{idx}] 摘要: {a['description']}")

    prompt = (
        "请将以下金融新闻的标题和摘要严格翻译成中文。"
        "保持专业金融术语准确。每条翻译保持原编号格式。"
        "只输出翻译结果，不要加任何解释。\n\n"
        + "\n".join(lines)
    )

    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 2000,
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

    if not result or "content" not in result:
        print("  ⚠ 翻译 API 调用失败，保留原文")
        return articles

    translated_text = ""
    for block in result.get("content", []):
        if block.get("type") == "text":
            translated_text += block.get("text", "")

    # 解析翻译结果
    for idx, (i, a) in enumerate(to_translate):
        # 找到对应的翻译文本
        title_marker = f"[{idx}] 标题:"
        desc_marker = f"[{idx}] 摘要:"

        # 提取翻译后的标题
        t_start = translated_text.find(title_marker)
        if t_start != -1:
            t_start += len(title_marker)
            # 找到这行的结尾
            t_end = translated_text.find("\n", t_start)
            if t_end == -1:
                t_end = len(translated_text)
            new_title = translated_text[t_start:t_end].strip()
            if new_title:
                articles[i]["title"] = new_title

        # 提取翻译后的摘要
        d_start = translated_text.find(desc_marker)
        if d_start != -1:
            d_start += len(desc_marker)
            d_end = translated_text.find("\n[", d_start)
            if d_end == -1:
                d_end = translated_text.find("\n\n", d_start)
            if d_end == -1:
                d_end = len(translated_text)
            new_desc = translated_text[d_start:d_end].strip()
            if new_desc:
                articles[i]["description"] = new_desc

    print(f"  ✅ 翻译完成")
    return articles

# ============================================================
#  1. 获取金属价格
# ============================================================
def fetch_prices():
    print("📊 正在获取金属价格...")
    url = (
        f"https://api.metals.dev/v1/latest"
        f"?api_key={METALS_DEV_API_KEY}"
        f"&currency=USD&unit=toz"
    )
    data = safe_request(url)
    prices = []

    if data and data.get("status") == "success":
        metals_data = data.get("metals", {})
        for code, info in METALS.items():
            price = metals_data.get(code)
            prices.append({
                "code": code, "name": info["name"],
                "price_usd": round(price, 2) if price else None,
                "unit": info["unit"],
            })
        print(f"  ✅ 获取到 {len(prices)} 种金属价格")
    else:
        error_msg = data.get("error_message", str(data)) if data else "无响应"
        print(f"  ❌ 价格 API 返回失败: {error_msg}")
        for code, info in METALS.items():
            prices.append({"code": code, "name": info["name"], "price_usd": None, "unit": info["unit"]})
    return prices

# ============================================================
#  1b. 保存历史价格
# ============================================================
def save_history(prices):
    print("📈 正在更新历史价格...")
    history_path = os.path.join(get_script_dir(), "history.json")
    history = []
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    today_record = {"date": today, "prices": {}}
    for p in prices:
        if p["price_usd"] is not None:
            today_record["prices"][p["code"]] = p["price_usd"]

    found = False
    for i, rec in enumerate(history):
        if rec.get("date") == today:
            history[i] = today_record
            found = True
            break
    if not found:
        history.append(today_record)

    history.sort(key=lambda x: x["date"])
    history = history[-60:]

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 历史记录已更新，共 {len(history)} 天数据")

# ============================================================
#  2. 获取新闻（只限大型金融媒体 + 翻译成中文）
# ============================================================
def fetch_news():
    print("📰 正在获取新闻...")

    all_raw = []

    # 中文新闻
    for q in ["黄金 价格", "白银 铜 价格", "贵金属", "有色金属 市场", "金属 行情"]:
        encoded = urllib.parse.quote(q)
        url = (
            f"https://newsapi.org/v2/everything"
            f"?q={encoded}&sortBy=publishedAt&pageSize=10&language=zh"
            f"&apiKey={NEWS_API_KEY}"
        )
        data = safe_request(url)
        if data and data.get("status") == "ok":
            for a in data.get("articles", []):
                title = a.get("title", "")
                desc = a.get("description") or ""
                source = a.get("source", {}).get("name", "")
                if not title or is_crypto(title, desc):
                    continue
                if not is_allowed_source(source):
                    print(f"    ⏭ 跳过非白名单来源: {source} — {title[:40]}")
                    continue
                all_raw.append({
                    "title": title, "source": source,
                    "url": a.get("url", ""), "published": a.get("publishedAt", ""),
                    "description": desc[:200], "lang": "zh",
                })

    # 英文新闻
    for q in ["gold price", "silver copper price metals", "platinum palladium nickel", "precious metals market", "base metals commodity"]:
        encoded = urllib.parse.quote(q)
        url = (
            f"https://newsapi.org/v2/everything"
            f"?q={encoded}&sortBy=publishedAt&pageSize=10&language=en"
            f"&apiKey={NEWS_API_KEY}"
        )
        data = safe_request(url)
        if data and data.get("status") == "ok":
            for a in data.get("articles", []):
                title = a.get("title", "")
                desc = a.get("description") or ""
                source = a.get("source", {}).get("name", "")
                if not title or is_crypto(title, desc):
                    continue
                if not is_allowed_source(source):
                    print(f"    ⏭ 跳过非白名单来源: {source} — {title[:40]}")
                    continue
                all_raw.append({
                    "title": title, "source": source,
                    "url": a.get("url", ""), "published": a.get("publishedAt", ""),
                    "description": desc[:200], "lang": "en",
                })

    # 去重，按时间排序，取最新 10 条
    seen = set()
    articles = []
    for a in all_raw:
        if a["title"] not in seen:
            seen.add(a["title"])
            articles.append(a)
    articles.sort(key=lambda x: x.get("published", ""), reverse=True)
    articles = articles[:10]

    # 翻译英文新闻为中文
    articles = translate_articles(articles)

    # 移除 lang 字段（前端不需要）
    for a in articles:
        a.pop("lang", None)

    print(f"  ✅ 获取到 {len(articles)} 条新闻（仅限大型金融媒体）")
    return articles

# ============================================================
#  3. 获取推文（可选）
# ============================================================
def fetch_tweets():
    if not TWITTER_BEARER:
        print("🐦 未设置 Twitter Bearer Token，跳过")
        return []
    print("🐦 正在获取推文...")
    query = urllib.parse.quote(
        "(gold price OR silver price OR copper price OR platinum price) "
        "-crypto -bitcoin -btc -eth -blockchain -is:retweet lang:en"
    )
    url = f"https://api.twitter.com/2/tweets/search/recent?query={query}&max_results=10&tweet.fields=created_at,author_id,text"
    headers = {"Authorization": f"Bearer {TWITTER_BEARER}"}
    data = safe_request(url, headers=headers)
    tweets = []
    if data and "data" in data:
        for t in data["data"]:
            txt = t.get("text", "")
            if is_crypto(txt):
                continue
            tweets.append({"text": txt, "created_at": t.get("created_at",""), "url": f"https://twitter.com/i/web/status/{t.get('id','')}"})
        print(f"  ✅ 获取到 {len(tweets)} 条推文")
    else:
        print("  ⚠ 推文获取失败或无结果")
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
        "prices": prices,
        "news": fetch_news(),
        "tweets": fetch_tweets(),
    }

    out_path = os.path.join(get_script_dir(), "data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 数据已保存")
    print(f"   价格: {len(result['prices'])} 种金属")
    print(f"   新闻: {len(result['news'])} 条")
    print(f"   推文: {len(result['tweets'])} 条")

if __name__ == "__main__":
    main()
