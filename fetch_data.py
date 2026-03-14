"""
金属价格 + 新闻 + 推文 数据抓取脚本
每天定时运行，把数据写入 data.json

需要的 API Key（免费申请，下面有教程）：
1. MetalpriceAPI  —— 金属价格
2. NewsAPI        —— 新闻
3. Twitter Bearer Token —— 推文（可选，申请较难）
"""

import json
import os
import datetime
import urllib.request
import urllib.parse
import urllib.error
import ssl

# ============================================================
#  在这里填入你的 API Key（或者设为环境变量，见下方说明）
# ============================================================
METALPRICE_API_KEY = os.environ.get("METALPRICE_API_KEY", "在这里粘贴你的Key")
NEWS_API_KEY       = os.environ.get("NEWS_API_KEY",       "在这里粘贴你的Key")
TWITTER_BEARER     = os.environ.get("TWITTER_BEARER",     "")  # 可选

# ============================================================
#  金属列表（MetalpriceAPI 使用的代码）
# ============================================================
METALS = {
    "XAU": "黄金 Gold",
    "XAG": "白银 Silver",
    "XCU": "铜 Copper",
    "ALU": "铝 Aluminum",
    "XPT": "铂 Platinum",
    "XPD": "钯 Palladium",
    "XRH": "铑 Rhodium",
    "NI":  "镍 Nickel",
    "CO":  "钴 Cobalt",
}

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
#  1. 获取金属价格
# ============================================================
def fetch_prices():
    print("📊 正在获取金属价格...")
    symbols = ",".join(METALS.keys())
    url = (
        f"https://api.metalpriceapi.com/v1/latest"
        f"?api_key={METALPRICE_API_KEY}"
        f"&base=USD&currencies={symbols}"
    )
    data = safe_request(url)
    prices = []

    if data and data.get("success"):
        rates = data.get("rates", {})
        for code, name in METALS.items():
            key = f"USD{code}"
            rate = rates.get(key)
            if rate and rate != 0:
                # API 返回的是 1 USD = ? 盎司，取倒数得到每盎司美元
                price_per_oz = round(1.0 / rate, 2)
            else:
                price_per_oz = None
            prices.append({
                "code": code,
                "name": name,
                "price_usd_per_oz": price_per_oz,
            })
        print(f"  ✅ 获取到 {len(prices)} 种金属价格")
    else:
        print("  ❌ 价格 API 返回失败，使用占位数据")
        for code, name in METALS.items():
            prices.append({"code": code, "name": name, "price_usd_per_oz": None})

    return prices

# ============================================================
#  2. 获取新闻
# ============================================================
def fetch_news():
    print("📰 正在获取新闻...")
    # 多组关键词，每组取几条，合并去重
    queries = [
        "gold price OR silver price OR copper price",
        "platinum price OR palladium price OR nickel price",
        "贵金属 价格 OR 有色金属 价格",
    ]
    seen_titles = set()
    articles = []

    for q in queries:
        encoded = urllib.parse.quote(q)
        url = (
            f"https://newsapi.org/v2/everything"
            f"?q={encoded}"
            f"&sortBy=publishedAt&pageSize=5&language=en"
            f"&apiKey={NEWS_API_KEY}"
        )
        data = safe_request(url)
        if data and data.get("status") == "ok":
            for a in data.get("articles", []):
                title = a.get("title", "")
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    articles.append({
                        "title": title,
                        "source": a.get("source", {}).get("name", ""),
                        "url": a.get("url", ""),
                        "published": a.get("publishedAt", ""),
                        "description": (a.get("description") or "")[:200],
                    })

    # 也搜中文新闻
    for q in ["贵金属 价格", "有色金属 价格"]:
        encoded = urllib.parse.quote(q)
        url = (
            f"https://newsapi.org/v2/everything"
            f"?q={encoded}"
            f"&sortBy=publishedAt&pageSize=3&language=zh"
            f"&apiKey={NEWS_API_KEY}"
        )
        data = safe_request(url)
        if data and data.get("status") == "ok":
            for a in data.get("articles", []):
                title = a.get("title", "")
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    articles.append({
                        "title": title,
                        "source": a.get("source", {}).get("name", ""),
                        "url": a.get("url", ""),
                        "published": a.get("publishedAt", ""),
                        "description": (a.get("description") or "")[:200],
                    })

    # 只保留最新 10 条
    articles.sort(key=lambda x: x.get("published", ""), reverse=True)
    articles = articles[:10]
    print(f"  ✅ 获取到 {len(articles)} 条新闻")
    return articles

# ============================================================
#  3. 获取推文（可选 —— 如果没有 Twitter Key 就跳过）
# ============================================================
def fetch_tweets():
    if not TWITTER_BEARER or TWITTER_BEARER == "":
        print("🐦 未设置 Twitter Bearer Token，跳过推文抓取")
        return []

    print("🐦 正在获取推文...")
    query = urllib.parse.quote(
        "(gold price OR silver price OR copper price OR platinum price) -is:retweet lang:en"
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
            tweet_id = t.get("id", "")
            tweets.append({
                "text": t.get("text", ""),
                "created_at": t.get("created_at", ""),
                "url": f"https://twitter.com/i/web/status/{tweet_id}",
            })
        print(f"  ✅ 获取到 {len(tweets)} 条推文")
    else:
        print("  ⚠ 推文获取失败或无结果")

    return tweets

# ============================================================
#  主函数：汇总数据 -> 写入 data.json
# ============================================================
def main():
    print("=" * 50)
    print(f"🚀 开始抓取数据 — {datetime.datetime.utcnow().isoformat()}Z")
    print("=" * 50)

    result = {
        "updated_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "prices": fetch_prices(),
        "news": fetch_news(),
        "tweets": fetch_tweets(),
    }

    # 写到脚本所在目录
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 数据已保存到 {out_path}")
    print(f"   价格: {len(result['prices'])} 种金属")
    print(f"   新闻: {len(result['news'])} 条")
    print(f"   推文: {len(result['tweets'])} 条")

if __name__ == "__main__":
    main()
