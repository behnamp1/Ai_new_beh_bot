import os, json, time, hashlib, re
import feedparser, requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@your_channel_username")
POSTED_PATH = "posted.json"

def load_feeds():
    with open("feeds.txt", "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def load_posted():
    if not os.path.exists(POSTED_PATH):
        return set()
    try:
        return set(json.load(open(POSTED_PATH, "r", encoding="utf-8")))
    except:
        return set()

def save_posted(ids):
    json.dump(sorted(list(ids)), open(POSTED_PATH, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

def strip_html(html):
    if not html: return ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()

def fetch_page_text(url, timeout=12):
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent":"Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        ps = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        txt = " ".join(ps)
        return re.sub(r"\s+", " ", txt).strip()
    except:
        return ""

def summarize(text, max_sentences=3):
    try:
        from sumy.parsers.plaintext import PlaintextParser
        from sumy.nlp.tokenizers import Tokenizer
        from sumy.summarizers.text_rank import TextRankSummarizer
        parser = PlaintextParser.from_string(text, Tokenizer("english"))
        summarizer = TextRankSummarizer()
        sents = summarizer(parser.document, max_sentences)
        out = " ".join(str(s) for s in sents)
        return out.strip()
    except Exception:
        return ""

def make_hashtags(title):
    words = re.findall(r"[A-Za-z\u0600-\u06FF]+", title)
    stops = set(["ai","the","of","in","and","with","for","از","به","و","در"])
    kws = [w for w in words if len(w) > 2 and w.lower() not in stops]
    tags = []
    for w in kws[:3]:
        tags.append("#"+w.strip())
    return " ".join(tags)

def send_telegram_text(token, chat_id, text, disable_preview=True):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": text[:4096],
                                 "disable_web_page_preview": disable_preview}, timeout=30)
    r.raise_for_status()

def send_telegram_photo(token, chat_id, photo_url, caption):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        img = requests.get(photo_url, timeout=12).content
        files = {"photo": ("img.jpg", img)}
        data = {"chat_id": chat_id, "caption": caption[:1024]}
        r = requests.post(url, data=data, files=files, timeout=30)
        r.raise_for_status()
    except:
        send_telegram_text(token, chat_id, caption, disable_preview=False)

def pick_image(entry):
    if hasattr(entry, "media_thumbnail"):
        try: return entry.media_thumbnail[0]["url"]
        except: pass
    if hasattr(entry, "media_content"):
        try: return entry.media_content[0]["url"]
        except: pass
    if "links" in entry:
        for l in entry.links:
            if l.get("rel") == "enclosure" and l.get("type","").startswith("image/"):
                return l.get("href")
    return None

def craft_caption(title, summary, link):
    host = urlparse(link).netloc.replace("www.","")
    hashtags = make_hashtags(title)
    if summary and len(summary) > 380: summary = summary[:380] + "…"
    caption = f"🤖 {title}\n\n{summary}\n\nمنبع: {host}\n{hashtags}\n🔗 {link}"
    return caption[:1024]

def main():
    assert TELEGRAM_TOKEN, "TELEGRAM_TOKEN is missing"
    feeds = load_feeds()
    posted = load_posted()
    new_any = False

    for feed_url in feeds:
        d = feedparser.parse(feed_url)
        for entry in d.entries[:6]:
            uid = entry.get("id") or entry.get("link") or hashlib.md5(str(entry).encode()).hexdigest()
            if uid in posted: continue

            title = entry.get("title","(Untitled)")
            link = entry.get("link","")
            rss_sum = strip_html(entry.get("summary",""))
            img = pick_image(entry)

            text_for_sum = rss_sum
            if len(text_for_sum) < 300 and link:
                page_txt = fetch_page_text(link)
                if len(page_txt) > 400:
                    text_for_sum = page_txt

            summary = ""
            if text_for_sum:
                summary = summarize(text_for_sum, max_sentences=3)
            if not summary:
                summary = rss_sum[:360] + ("…" if len(rss_sum)>360 else "")

            caption = craft_caption(title, summary, link) if link else f"🤖 {title}\n\n{summary}"
            try:
                if img:
                    send_telegram_photo(TELEGRAM_TOKEN, CHANNEL_USERNAME, img, caption)
                else:
                    send_telegram_text(TELEGRAM_TOKEN, CHANNEL_USERNAME, caption, disable_preview=False)
                posted.add(uid)
                new_any = True
                time.sleep(1.2)
            except Exception as e:
                print("Error posting:", e)

    if new_any:
        save_posted(posted)
        print("Posted new items.")

if __name__ == "__main__":
    main()
