"""
众智创新 · 金属价格实时追踪
每天定时运行，把数据写入 data.json，并追加历史价格到 history.json

使用的 API：
1. Metals.dev  —— 金属价格（免费，100次/月）
2. NewsAPI     —— 新闻（过滤掉虚拟货币相关内容）
3. Twitter Bearer Token —— 推文（可选）
"""

import json
import os
import datetime
import urllib.request
import urllib.parse
import urllib.error
import ssl

# ============================================================
#  在这里填入你的 API Key（或者设为环境变量）
# ============================================================
METALS_DEV_API_KEY = os.environ.get("METALS_DEV_API_KEY", "在这里粘贴你的Key")
NEWS_API_KEY       = os.environ.get("NEWS_API_KEY",        "在这里粘贴你的Key")
TWITTER_BEARER     = os.environ.get("TWITTER_BEARER",      "")  # 可选

# ============================================================
#  金属列表（metals.dev 使用的代码）
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
}

# ============================================================
#  虚拟货币过滤关键词
# ============================================================
CRYPTO_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency",
    "blockchain", "altcoin", "token", "defi", "nft", "web3",
    "dogecoin", "solana", "ripple", "xrp", "binance", "coinbase",
    "比特币", "以太坊", "加密货币", "虚拟货币", "数字货币", "区块链",
    "币圈", "代币", "挖矿", "矿机",
]

def is_crypto_news(title, description=""):
    text = (title + " " + description).lower()
    return any(kw in text for kw in CRYPTO_KEYWORDS)

# ============================================================
#  辅助函数
# ============================================================
def safe_request(url, headers=None, timeout=15):
    try:
        req = urllib.request.Request(url)
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
#  1. 获取金属价格（使用 metals.dev）
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
                "code": code,
                "name": info["name"],
                "price_usd": round(price, 2) if price else None,
                "unit": info["unit"],
            })
        print(f"  ✅ 获取到 {len(prices)} 种金属价格")
    else:
        error_msg = ""
        if data:
            error_msg = data.get("error_message", str(data))
        print(f"  ❌ 价格 API 返回失败: {error_msg}")
        for code, info in METALS.items():
            prices.append({
                "code": code, "name": info["name"],
                "price_usd": None, "unit": info["unit"],
            })
    return prices

# ============================================================
#  1b. 保存历史价格（追加到 history.json，保留最近 60 天）
# ============================================================
def save_history(prices):
    print("📈 正在更新历史价格...")
    history_path = os.path.join(get_script_dir(), "history.json")

    # 读取已有历史
    history = []
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    # 今天的日期
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    # 构建今天的价格记录
    today_record = {"date": today, "prices": {}}
    for p in prices:
        if p["price_usd"] is not None:
            today_record["prices"][p["code"]] = p["price_usd"]

    # 如果今天已经有记录就覆盖，否则追加
    found = False
    for i, rec in enumerate(history):
        if rec.get("date") == today:
            history[i] = today_record
            found = True
            break
    if not found:
        history.append(today_record)

    # 按日期排序，只保留最近 60 天
    history.sort(key=lambda x: x["date"])
    history = history[-60:]

    # 写回文件
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"  ✅ 历史记录已更新，共 {len(history)} 天数据")

# ============================================================
#  2. 获取新闻（过滤掉虚拟货币）
# ============================================================
def fetch_news():
    print("📰 正在获取新闻...")
    queries = [
        "gold price OR silver price OR copper price",
        "platinum price OR palladium price OR nickel price",
        "precious metals market",
    ]
    seen_titles = set()
    articles = []

    for q in queries:
        encoded = urllib.parse.quote(q)
        url = (
            f"https://newsapi.org/v2/everything"
            f"?q={encoded}"
            f"&sortBy=publishedAt&pageSize=10&language=en"
            f"&apiKey={NEWS_API_KEY}"
        )
        data = safe_request(url)
        if data and data.get("status") == "ok":
            for a in data.get("articles", []):
                title = a.get("title", "")
                desc = a.get("description") or ""
                if not title or title in seen_titles:
                    continue
                if is_crypto_news(title, desc):
                    print(f"    🚫 过滤: {title[:50]}...")
                    continue
                seen_titles.add(title)
                articles.append({
                    "title": title,
                    "source": a.get("source", {}).get("name", ""),
                    "url": a.get("url", ""),
                    "published": a.get("publishedAt", ""),
                    "description": desc[:200],
                })

    for q in ["贵金属 价格", "有色金属 价格"]:
        encoded = urllib.parse.quote(q)
        url = (
            f"https://newsapi.org/v2/everything"
            f"?q={encoded}"
            f"&sortBy=publishedAt&pageSize=5&language=zh"
            f"&apiKey={NEWS_API_KEY}"
        )
        data = safe_request(url)
        if data and data.get("status") == "ok":
            for a in data.get("articles", []):
                title = a.get("title", "")
                desc = a.get("description") or ""
                if not title or title in seen_titles:
                    continue
                if is_crypto_news(title, desc):
                    continue
                seen_titles.add(title)
                articles.append({
                    "title": title,
                    "source": a.get("source", {}).get("name", ""),
                    "url": a.get("url", ""),
                    "published": a.get("publishedAt", ""),
                    "description": desc[:200],
                })

    articles.sort(key=lambda x: x.get("published", ""), reverse=True)
    articles = articles[:10]
    print(f"  ✅ 获取到 {len(articles)} 条新闻（已过滤加密货币）")
    return articles

# ============================================================
#  3. 获取推文（可选）
# ============================================================
def fetch_tweets():
    if not TWITTER_BEARER or TWITTER_BEARER == "":
        print("🐦 未设置 Twitter Bearer Token，跳过")
        return []

    print("🐦 正在获取推文...")
    query = urllib.parse.quote(
        "(gold price OR silver price OR copper price OR platinum price) "
        "-crypto -bitcoin -btc -eth -blockchain "
        "-is:retweet lang:en"
    )
    url = (
        f"https://api.twitter.com/2/tweets/search/recent"
        f"?query={query}&max_results=10"
        f"&tweet.fields=created_at,author_id,text"
    )
    headers = {"Authorization": f"Bearer {TWITTER_BEARER}"}
    data = safe_request(url, headers=headers)
    tweets = []

    if data and "data" in data:
        for t in data["data"]:
            tweet_text = t.get("text", "")
            if is_crypto_news(tweet_text):
                continue
            tweet_id = t.get("id", "")
            tweets.append({
                "text": tweet_text,
                "created_at": t.get("created_at", ""),
                "url": f"https://twitter.com/i/web/status/{tweet_id}",
            })
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
