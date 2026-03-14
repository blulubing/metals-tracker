"""
众智创新 · 金属价格实时追踪
每天定时运行，把数据写入 data.json

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
#  贵金属单位: troy ounce (toz)
#  工业金属单位: metric tonne (mt)
# ============================================================
METALS = {
    # 贵金属
    "gold":      {"name": "黄金 Gold",       "unit": "USD/盎司 oz"},
    "silver":    {"name": "白银 Silver",      "unit": "USD/盎司 oz"},
    "platinum":  {"name": "铂 Platinum",      "unit": "USD/盎司 oz"},
    "palladium": {"name": "钯 Palladium",     "unit": "USD/盎司 oz"},
    # 工业金属
    "copper":    {"name": "铜 Copper",        "unit": "USD/吨 mt"},
    "aluminum":  {"name": "铝 Aluminum",      "unit": "USD/吨 mt"},
    "nickel":    {"name": "镍 Nickel",        "unit": "USD/吨 mt"},
    "zinc":      {"name": "锌 Zinc",          "unit": "USD/吨 mt"},
    "lead":      {"name": "铅 Lead",          "unit": "USD/吨 mt"},
}

# ============================================================
#  虚拟货币 / 加密货币过滤关键词
# ============================================================
CRYPTO_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency",
    "blockchain", "altcoin", "token", "defi", "nft", "web3",
    "dogecoin", "solana", "ripple", "xrp", "binance", "coinbase",
    "比特币", "以太坊", "加密货币", "虚拟货币", "数字货币", "区块链",
    "币圈", "代币", "挖矿", "矿机",
]

def is_crypto_news(title, description=""):
    """检查新闻是否与虚拟货币有关"""
    text = (title + " " + description).lower()
    return any(kw in text for kw in CRYPTO_KEYWORDS)

# ============================================================
#  辅助函数：安全地发送 HTTP 请求
# ============================================================
def safe_request(url, headers=None, timeout=15):
    """发送 GET 请求，返回字典或 None"""
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
            # metals.dev 工业金属默认单位是 metric tonne
            # 但我们请求了 unit=toz，所以全部是盎司价格
            # 不过工业金属的盎司价格很小，更常用吨价
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
                "code": code,
                "name": info["name"],
                "price_usd": None,
                "unit": info["unit"],
            })

    return prices

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
                # 过滤虚拟货币新闻
                if is_crypto_news(title, desc):
                    print(f"    🚫 过滤掉加密货币新闻: {title[:50]}...")
                    continue
                seen_titles.add(title)
                articles.append({
                    "title": title,
                    "source": a.get("source", {}).get("name", ""),
                    "url": a.get("url", ""),
                    "published": a.get("publishedAt", ""),
                    "description": desc[:200],
                })

    # 也搜中文新闻（同样过滤加密货币）
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
                    print(f"    🚫 过滤掉加密货币新闻: {title[:50]}...")
                    continue
                seen_titles.add(title)
                articles.append({
                    "title": title,
                    "source": a.get("source", {}).get("name", ""),
                    "url": a.get("url", ""),
                    "published": a.get("publishedAt", ""),
                    "description": desc[:200],
                })

    # 只保留最新 10 条
    articles.sort(key=lambda x: x.get("published", ""), reverse=True)
    articles = articles[:10]
    print(f"  ✅ 获取到 {len(articles)} 条新闻（已过滤加密货币相关内容）")
    return articles

# ============================================================
#  3. 获取推文（可选）
# ============================================================
def fetch_tweets():
    if not TWITTER_BEARER or TWITTER_BEARER == "":
        print("🐦 未设置 Twitter Bearer Token，跳过推文抓取")
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
            # 二次过滤
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
    print(f"   开始抓取数据 — {datetime.datetime.utcnow().isoformat()}Z")
    print("=" * 50)

    result = {
        "updated_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "prices": fetch_prices(),
        "news": fetch_news(),
        "tweets": fetch_tweets(),
    }

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 数据已保存到 {out_path}")
    print(f"   价格: {len(result['prices'])} 种金属")
    print(f"   新闻: {len(result['news'])} 条")
    print(f"   推文: {len(result['tweets'])} 条")

if __name__ == "__main__":
    main()
