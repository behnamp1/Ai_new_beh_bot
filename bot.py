import os, json, time, hashlib, re
import feedparser, requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from langdetect import detect

# ====== ENV ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@your_channel_username")
HF_TOKEN = os.getenv("HF_TOKEN")  # ← توکن HuggingFace
POSTED_PATH = "posted.json"

# ====== برند/هشتگ ======
BRAND_EMOJI = "🤖"
DEFAULT_TAGS_FA = ["#هوش_مصنوعی", "#خبر_کوتاه", "#مدل_زبان"]

# ====== مدل‌ها در HF ======
HF_SUM_MODEL = "csebuetnlp/mT5_multilingual_XLSum"        # خلاصه‌سازی چندزبانه
HF_EN_FA_MODEL = "Helsinki-NLP/opus-mt-en-fa"             # ترجمه en→fa

# ---------- Utilities ----------
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

# ---------- HF Inference API ----------
def hf_infer(model: str, inputs: str, params: dict = None, timeout=45):
    if not HF_TOKEN:
        print("HF_TOKEN missing; skip HF call.")
        return ""
    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {"inputs": inputs}
    if params:
        payload["parameters"] = params
    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if r.status_code == 503:  # مدل سرد/در حال لود
        time.sleep(6)
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if not r.ok:
        print("HF error:", r.status_code, r.text[:500])
        return ""
    try:
        out = r.json()
        if isinstance(out, list) and out and "generated_text" in out[0]:
            return out[0]["generated_text"].strip()
        if isinstance(out, dict) and "generated_text" in out:
            return out["generated_text"].strip()
    except Exception as e:
        print("HF parse error:", e)
    return ""

def hf_summarize_multilingual(text: str, target_lang: str = "fa", max_len: int = 140):
    if not text or len(text) < 40:
        return ""
    if target_lang == "fa":
        prompt = f"خلاصهٔ خبری کوتاه و دقیق به فارسی از متن زیر بنویس:\n\n{text}\n\nخلاصه:"
    else:
        prompt = f"Write a concise news-style summary in English from the text below:\n\n{text}\n\nSummary:"
    return (hf_infer(HF_SUM_MODEL, prompt, params={"max_new_tokens": max_len}) or "").strip()

def hf_translate_en_to_fa(text: str, max_len: int = 260):
    if not text: return ""
    return (hf_infer(HF_EN_FA_MODEL, text, params={"max_new_tokens": max_len}) or "").strip()

# ---------- Persian rewriting ----------
def rewrite_persian(title_fa, summary_fa):
    title_fa = re.sub(r"\s+", " ", title_fa).strip()
    if len(title_fa) > 90: title_fa = title_fa[:87] + "…"

    bullets = []
    for sent in re.split(r"[.!؟]\s+", summary_fa):
        s = sent.strip(" .!؟")
        if 6 <= len(s) <= 120:
            bullets.append("• " + s)
        if len(bullets) == 3:
            break
    if not bullets:
        bullets = ["• نکتهٔ مهم اول", "• نکتهٔ مهم دوم", "• نکتهٔ مهم سوم"]

    takeaway = ""
    for sent in re.split(r"[.!؟]\s+", summary_fa):
        if 14 <= len(sent) <= 140:
            takeaway = sent.strip()
            break
    if not takeaway:
        takeaway = "این خبر نشان می‌دهد روندهای هوش مصنوعی با سرعت در حال تحول‌اند."

    return title_fa, "\n".join(bullets), takeaway

def make_hashtags_fa(title_fa):
    words = re.findall(r"[A-Za-z\u0600-\u06FF]+", title_fa)
    stops = set(["با","از","به","و","در","برای","شود","است","AI","هوش","مصنوعی"])
    tags = []
    for w in words:
        if 2 < len(w) <= 18 and w not in stops and len(tags) < 3:
            tags.append("#" + w.replace(" ", "_"))
    return " ".join(tags + DEFAULT_TAGS_FA)

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

# ---------- Telegram ----------
def send_telegram_text(token, chat_id, text, disable_preview=False):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={
        "chat_id": chat_id,
        "text": text[:4096],
        "disable_web_page_preview": disable_preview
    }, timeout=30)
    if not r.ok:
        print("Telegram error:", r.status_code, r.text[:500])
    r.raise_for_status()

def send_telegram_photo(token, chat_id, photo_url, caption):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        img = requests.get(photo_url, timeout=12).content
        files = {"photo": ("img.jpg", img)}
        data = {"chat_id": chat_id, "caption": caption[:1024]}
        r = requests.post(url, data=data, files=files, timeout=30)
        if not r.ok:
            print("Telegram error:", r.status_code, r.text[:500])
        r.raise_for_status()
    except Exception:
        send_telegram_text(token, chat_id, caption, disable_preview=False)

def craft_caption_fa(title_fa, bullets_fa, takeaway_fa, link):
    host = urlparse(link).netloc.replace("www.","")
    hashtags = make_hashtags_fa(title_fa)
    body = f"{BRAND_EMOJI} {title_fa}\n\n{bullets_fa}\n\n🔎 جمع‌بندی: {takeaway_fa}\n\nمنبع: {host}\n{hashtags}\n🔗 لینک: {link}"
    return body[:1024]

# ---------- MAIN ----------
def main():
    assert TELEGRAM_TOKEN, "TELEGRAM_TOKEN is missing"
    feeds = load_feeds()

    # فقط اولین فید و اولین آیتم رو می‌گیره
    if not feeds:
        print("No feeds found in feeds.txt")
        return

    feed_url = feeds[0]
    d = feedparser.parse(feed_url)

    if not d.entries:
        print("No entries in feed")
        return

    # اولین آیتم
    entry = d.entries[0]
    title = entry.get("title", "(Untitled)")
    link = entry.get("link", "")
    summary = strip_html(entry.get("summary", ""))

    # متن فارسی ساده بساز (بدون خلاصه‌سازی)
    caption = f"🧪 تست ارسال پیام:\n\n{title}\n\n{summary[:200]}...\n\nلینک: {link}"

    try:
        send_telegram_text(TELEGRAM_TOKEN, CHANNEL_USERNAME, caption, disable_preview=False)
        print("Test message sent to Telegram!")
    except Exception as e:
        print("Error posting:", e)
