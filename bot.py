import os, re, time
import feedparser, requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@your_channel_username")

# ---------- tiny utils ----------
def strip_html(html):
    if not html: return ""
    soup = BeautifulSoup(html, "html.parser")
    txt = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", txt).strip()

def load_feeds():
    with open("feeds.txt", "r", encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]

def tg_send(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHANNEL_USERNAME, "text": text[:4096],
                                 "disable_web_page_preview": False}, timeout=30)
    print("TG response:", r.status_code, r.text[:200])
    r.raise_for_status()

# ---------- forced demo send ----------
def main():
    assert TELEGRAM_TOKEN, "TELEGRAM_TOKEN is missing"
    feeds = load_feeds()
    assert feeds, "feeds.txt is empty"

    # پیام شروع برای اطمینان
    tg_send("⚙️ bot.py started (forced demo run)")

    # فقط از اولین فید، دو آیتم اول را بفرست
    d = feedparser.parse(feeds[0])
    print("Feed:", feeds[0], "| entries:", len(d.entries))
    if not d.entries:
        tg_send("❗ No entries in first feed.")
        return

    sent = 0
    for e in d.entries[:2]:
        title = e.get("title", "(Untitled)")
        link = e.get("link", "")
        summary = strip_html(e.get("summary", ""))[:400]
        msg = f"📰 {title}\n\n{summary}\n\n🔗 {link}"
        try:
            tg_send(msg)
            sent += 1
            time.sleep(1.0)
        except Exception as ex:
            print("Send error:", ex)

    tg_send(f"✅ bot.py finished. Sent {sent} items (forced).")

if __name__ == "__main__":
    main()
