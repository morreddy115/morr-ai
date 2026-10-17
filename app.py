import os, re, io, uuid, time, secrets, sqlite3, socket, ipaddress, tempfile, urllib.parse
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template_string, request, jsonify, session, redirect, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ===========================================================================
# SETUP
# Environment variables (set them on Render -> Environment, never in code):
#   SECRET_KEY         required: any long random text (keeps logins safe)
#   DATABASE_URL       recommended: Postgres link (Neon/Supabase) so accounts survive redeploys
#   GEMINI_API_KEY     AI provider 1 (also reads images, PDFs and voice)
#   GROQ_API_KEY       AI provider 2
#   TAVILY_API_KEY     optional: best live web search
#   OPENROUTER_API_KEY + OPENROUTER_MODEL   optional: AI provider 3
#   GEMINI_MODEL / GROQ_MODEL   optional: force a model name (otherwise auto-detected)
#   PROVIDER_ORDER     optional, default "gemini,groq,openrouter"
# ===========================================================================
app = Flask(__name__)
SECRET = os.environ.get("SECRET_KEY")
if not SECRET:
    SECRET = secrets.token_hex(32)
    print("[warn] SECRET_KEY is not set. Logins will reset on every restart. Set it on Render.")
app.secret_key = SECRET
app.config.update(
    MAX_CONTENT_LENGTH=20 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.getenv("RENDER")),
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

GEMINI_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
GROQ_KEY = (os.getenv("GROQ_API_KEY") or "").strip()
TAVILY_KEY = (os.getenv("TAVILY_API_KEY") or "").strip()
OPENROUTER_KEY = (os.getenv("OPENROUTER_API_KEY") or "").strip()
OPENROUTER_MODEL = (os.getenv("OPENROUTER_MODEL") or "").strip()
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
SQLITE_PATH = os.getenv("SQLITE_PATH", "morr.db")
PROVIDER_ORDER = [p.strip() for p in os.getenv("PROVIDER_ORDER", "gemini,groq,openrouter").split(",") if p.strip()]

gclient = None
types = None
if GEMINI_KEY:
    try:
        from google import genai
        from google.genai import types
        gclient = genai.Client(api_key=GEMINI_KEY)
    except Exception as e:
        print(f"[gemini] could not start client: {e}")

GENERATED_DIR = os.path.join(tempfile.gettempdir(), "morr_ai_generated")
os.makedirs(GENERATED_DIR, exist_ok=True)
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def cleanup_old_files(max_age=3600):
    try:
        cutoff = time.time() - max_age
        for name in os.listdir(GENERATED_DIR):
            p = os.path.join(GENERATED_DIR, name)
            if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                os.remove(p)
    except Exception:
        pass


# ===========================================================================
# DATABASE (Postgres if DATABASE_URL is set, otherwise SQLite)
# ===========================================================================
IS_PG = bool(DATABASE_URL)


def get_conn():
    if IS_PG:
        import psycopg2
        return psycopg2.connect(DATABASE_URL, connect_timeout=10)
    return sqlite3.connect(SQLITE_PATH)


def db(sql, params=(), fetch=None, insert=False):
    conn = get_conn()
    try:
        cur = conn.cursor()
        if IS_PG:
            sql = sql.replace("?", "%s")
            if insert:
                sql += " RETURNING id"
        cur.execute(sql, params)
        result = None
        if insert:
            result = cur.fetchone()[0] if IS_PG else cur.lastrowid
        elif fetch == "one":
            result = cur.fetchone()
        elif fetch == "all":
            result = cur.fetchall()
        conn.commit()
        return result
    finally:
        conn.close()


def init_db():
    pk = "SERIAL PRIMARY KEY" if IS_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
    try:
        db(f"CREATE TABLE IF NOT EXISTS users (id {pk}, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL)")
        db(f"CREATE TABLE IF NOT EXISTS conversations (id {pk}, user_id INTEGER NOT NULL, title TEXT, created TEXT, updated TEXT)")
        db(f"CREATE TABLE IF NOT EXISTS messages (id {pk}, conversation_id INTEGER NOT NULL, role TEXT, content TEXT, created TEXT)")
        db("CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations (user_id, updated)")
        db("CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages (conversation_id)")
        if not IS_PG:
            print("[warn] DATABASE_URL not set: using a local SQLite file. Accounts and chats are LOST on every Render redeploy.")
    except Exception as e:
        print(f"[db] init failed: {e}")


init_db()


# ===========================================================================
# LIVE INTERNET SEARCH  (Tavily -> DuckDuckGo -> Wikipedia) + page reading
# ===========================================================================
def is_public_url(url):
    try:
        p = urllib.parse.urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return False
        for info in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except Exception:
        return False


def fetch_page(url, limit=1500):
    """Read the main text of a public web page (redirects are re-checked)."""
    try:
        for _ in range(4):
            if not is_public_url(url):
                return ""
            r = requests.get(url, headers={"User-Agent": BROWSER_UA}, timeout=6, allow_redirects=False)
            if r.status_code in (301, 302, 303, 307, 308):
                url = urllib.parse.urljoin(url, r.headers.get("Location", ""))
                continue
            if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
                return ""
            soup = BeautifulSoup(r.text[:300000], "html.parser")
            for t in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                t.decompose()
            text = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
            return re.sub(r"\s+", " ", text)[:limit]
    except Exception:
        pass
    return ""


def _ddgs_class():
    try:
        from ddgs import DDGS
        return DDGS
    except Exception:
        try:
            from duckduckgo_search import DDGS
            return DDGS
        except Exception:
            return None


def web_search(query, deep=False):
    """Returns {"text": str for the AI, "sources": [{"title","url"}]}"""
    items, direct = [], ""

    def add(title, snippet, url):
        if url and snippet and all(url != i["url"] for i in items):
            items.append({"title": (title or url)[:120], "snippet": snippet[:400], "url": url})

    if TAVILY_KEY:
        try:
            r = requests.post("https://api.tavily.com/search",
                              json={"api_key": TAVILY_KEY, "query": query, "max_results": 5,
                                    "include_answer": True, "search_depth": "basic"}, timeout=10)
            r.raise_for_status()
            data = r.json()
            direct = data.get("answer") or ""
            for x in data.get("results", []):
                add(x.get("title"), x.get("content"), x.get("url"))
        except Exception as e:
            print(f"[search] tavily failed: {str(e)[:200]}")

    if len(items) < 3:
        DDGS = _ddgs_class()
        if DDGS:
            try:
                for x in list(DDGS().text(query, max_results=6)):
                    add(x.get("title"), x.get("body"), x.get("href"))
            except Exception as e:
                print(f"[search] duckduckgo failed: {str(e)[:200]}")

    if len(items) < 3:
        try:
            r = requests.get("https://en.wikipedia.org/w/api.php", params={
                "action": "query", "format": "json", "generator": "search", "gsrsearch": query,
                "gsrlimit": 3, "prop": "extracts|info", "exintro": 1, "explaintext": 1,
                "exsentences": 4, "inprop": "url"}, headers={"User-Agent": "MORR AI GH/2.0"}, timeout=8)
            r.raise_for_status()
            pages = (r.json().get("query") or {}).get("pages", {})
            for p in sorted(pages.values(), key=lambda x: x.get("index", 99)):
                add(p.get("title"), p.get("extract"), p.get("fullurl"))
        except Exception as e:
            print(f"[search] wikipedia failed: {str(e)[:200]}")

    if deep:
        for it in items[:2]:
            it["page"] = fetch_page(it["url"])

    parts = []
    if direct:
        parts.append(f"Quick answer: {direct}")
    for n, it in enumerate(items[:6], 1):
        block = f"[{n}] {it['title']}\n{it['snippet']}"
        if it.get("page"):
            block += f"\nPage excerpt: {it['page']}"
        block += f"\nURL: {it['url']}"
        parts.append(block)
    return {"text": "\n\n".join(parts)[:7000],
            "sources": [{"title": i["title"], "url": i["url"]} for i in items[:4]]}


SMALLTALK = re.compile(
    r"^\s*(hi+|hello|hey+|yo|chale|charley|wagwan|how are you|how far|how you dey|how body|how is it going|"
    r"good (morning|afternoon|evening|night)|thanks?|thank you|ok(ay)?|cool|nice|bye|goodbye|who are you|"
    r"what('s| is) your name|what can you do|akwaaba|medaase|ete sen|sannu|ina kwana|na gode|bonjour|salut|hola|merci)\b",
    re.I)
NO_SEARCH = re.compile(r"^\s*(translate|rewrite|write|compose|draft|summari[sz]e|fix|debug|solve|calculate|"
                       r"correct|proofread|tell me a joke|joke)\b", re.I)
SEARCH_CUES = re.compile(
    r"\b(who is|who's|who was|president|prime minister|ceo|current|currently|latest|today|tonight|now|news|"
    r"price|weather|score|result|results|won|winner|when did|when is|where is|how much|population|capital|"
    r"exchange rate|release|stock|election|minister|governor|champion|2025|2026)\b", re.I)


def should_search(q, has_attachment):
    if not q or len(q.strip()) < 3:
        return False
    if SMALLTALK.match(q) or NO_SEARCH.match(q):
        return False
    if SEARCH_CUES.search(q):
        return True
    if has_attachment:
        return False
    words = q.split()
    return "?" in q or len(words) <= 6


# ===========================================================================
# AI PROVIDERS (models are auto-detected, so retired model names stop breaking the app)
# ===========================================================================
MODEL_CACHE = {}


def discover_gemini_model():
    try:
        best, best_key = None, None
        for m in gclient.models.list():
            name = (m.name or "").replace("models/", "")
            if "flash" not in name or any(x in name for x in ("lite", "image", "tts", "live", "audio", "embed", "native", "robotics")):
                continue
            actions = getattr(m, "supported_actions", None)
            if actions and "generateContent" not in actions:
                continue
            mt = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
            key = (float(mt.group(1)) if mt else 0.0, -len(name))
            if best_key is None or key > best_key:
                best, best_key = name, key
        print(f"[gemini] auto-detected model: {best}")
        return best
    except Exception as e:
        print(f"[gemini] model discovery failed: {str(e)[:200]}")
        return None


def get_gemini_model():
    return MODEL_CACHE.get("gemini") or os.getenv("GEMINI_MODEL") or "gemini-3.8-flash"


def gemini_generate(contents, system=None, use_search=False):
    if not gclient:
        raise RuntimeError("Gemini is not configured")
    for attempt in range(2):
        model = get_gemini_model()
        try:
            cfg = types.GenerateContentConfig(
                system_instruction=system, temperature=0.7,
                tools=[types.Tool(google_search=types.GoogleSearch())] if use_search else None)
            return gclient.models.generate_content(model=model, contents=contents, config=cfg)
        except Exception as e:
            s = str(e)
            if attempt == 0 and ("NOT_FOUND" in s or "404" in s[:30]):
                new = discover_gemini_model()
                if new and new != model:
                    MODEL_CACHE["gemini"] = new
                    continue
            raise


def gemini_sources(resp):
    out = []
    try:
        for ch in (resp.candidates[0].grounding_metadata.grounding_chunks or [])[:4]:
            if ch.web and ch.web.uri:
                out.append({"title": ch.web.title or ch.web.uri, "url": ch.web.uri})
    except Exception:
        pass
    return out


def call_gemini(system, history, user_text):
    contents = [types.Content(role="user" if h["role"] == "user" else "model",
                              parts=[types.Part(text=h["content"])]) for h in history]
    contents.append(types.Content(role="user", parts=[types.Part(text=user_text)]))
    try:
        resp = gemini_generate(contents, system, use_search=True)
    except Exception as e:
        if "429" in str(e)[:30] or "RESOURCE_EXHAUSTED" in str(e):
            raise
        print(f"[gemini] search mode failed, retrying plain: {str(e)[:200]}")
        resp = gemini_generate(contents, system, use_search=False)
    if not resp.text:
        raise RuntimeError("Gemini returned an empty answer")
    return resp.text, gemini_sources(resp)


def _chat_post(url, key, model, messages, extra_headers=None):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    headers.update(extra_headers or {})
    r = requests.post(url, headers=headers, timeout=45,
                      json={"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 1200})
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code} {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"]


def discover_groq_model():
    try:
        r = requests.get("https://api.groq.com/openai/v1/models",
                         headers={"Authorization": f"Bearer {GROQ_KEY}"}, timeout=10)
        r.raise_for_status()
        best, best_size = None, -1
        for m in r.json().get("data", []):
            mid = m.get("id", "")
            if m.get("active") is False or any(x in mid.lower() for x in
                                               ("whisper", "guard", "tts", "playai", "embed", "orpheus", "vision-preview")):
                continue
            sizes = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)b", mid.lower())]
            size = max(sizes) if sizes else 0
            if size > best_size:
                best, best_size = mid, size
        print(f"[groq] auto-detected model: {best}")
        return best
    except Exception as e:
        print(f"[groq] model discovery failed: {str(e)[:200]}")
        return None


def call_groq(system, history, user_text):
    messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": user_text}]
    forced = os.getenv("GROQ_MODEL")
    for attempt in range(2):
        model = MODEL_CACHE.get("groq") or forced or discover_groq_model()
        if not model:
            raise RuntimeError("No Groq model available")
        MODEL_CACHE["groq"] = model
        try:
            return _chat_post("https://api.groq.com/openai/v1/chat/completions", GROQ_KEY, model, messages)
        except Exception as e:
            s = str(e).lower()
            if attempt == 0 and any(x in s for x in ("model_not_found", "decommissioned", "does not exist", "404")):
                MODEL_CACHE.pop("groq", None)
                forced = None
                continue
            raise


def call_openrouter(system, history, user_text):
    messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": user_text}]
    return _chat_post("https://openrouter.ai/api/v1/chat/completions", OPENROUTER_KEY, OPENROUTER_MODEL,
                      messages, {"X-Title": "MORR AI GH"})


def build_system(lang):
    today = datetime.now(timezone.utc).strftime("%A, %d %B %Y")
    if lang and lang != "Auto":
        lang_rule = f"Reply in {lang}."
    else:
        lang_rule = ("Reply in the same language the user writes in (English, Ghanaian Pidgin, Twi, Hausa, French, "
                     "Arabic, Spanish or any other). If they mix languages, match their style.")
    return (
        "You are MORR AI GH, a smart, warm and friendly assistant built by Morr in Ghana, "
        "like ChatGPT or Meta AI. Talk like a real person: natural, direct, not robotic.\n"
        f"Today's date is {today}. {lang_rule}\n"
        "Rules:\n"
        "- Greetings and small talk get a short, human reply (for example 'how are you doing' -> "
        "'Chale, I'm good! How about you?'). Never search or define the greeting.\n"
        "- For facts, use the web results or search you are given and trust them over your memory. "
        "If the user's question has a wrong premise, politely correct it "
        "(for example: Jamaica has a Prime Minister, not a President).\n"
        "- If you are not sure, say so plainly. Never invent facts, names, numbers or links.\n"
        "- If a file or image is attached, use it first.\n"
        "- Be concise. Use short paragraphs, and lists only when they help."
    )


def build_user_text(q, file_ctx, img_ctx, web_text=""):
    parts = []
    if web_text:
        parts.append("LIVE WEB SEARCH RESULTS (use these for facts, mention the source name when helpful):\n" + web_text)
    if file_ctx:
        parts.append("ATTACHED FILE CONTENT:\n" + file_ctx[:6000])
    if img_ctx:
        parts.append("ATTACHED IMAGE (description and any text in it):\n" + img_ctx[:3000])
    parts.append("USER MESSAGE:\n" + q)
    return "\n\n".join(parts)


def clean_history(hist):
    out = []
    for h in (hist or [])[-10:]:
        if isinstance(h, dict) and h.get("role") in ("user", "assistant") and isinstance(h.get("content"), str):
            out.append({"role": h["role"], "content": h["content"][:1500]})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def generate_answer(q, lang, file_ctx, img_ctx, history):
    """Try each AI provider in turn. Returns (answer, sources, provider)."""
    system = build_system(lang)
    has_att = bool(file_ctx or img_ctx)
    need_web = should_search(q, has_att)
    web = {"text": "", "sources": []}
    web_done = False

    for provider in PROVIDER_ORDER:
        try:
            if provider == "gemini" and gclient:
                text, srcs = call_gemini(system, history, build_user_text(q, file_ctx, img_ctx))
                return text, srcs, "gemini"
            if provider in ("groq", "openrouter"):
                if provider == "groq" and not GROQ_KEY:
                    continue
                if provider == "openrouter" and not (OPENROUTER_KEY and OPENROUTER_MODEL):
                    continue
                if need_web and not web_done:
                    web = web_search(q, deep=True)
                    web_done = True
                user_text = build_user_text(q, file_ctx, img_ctx, web["text"])
                fn = call_groq if provider == "groq" else call_openrouter
                text = fn(system, history, user_text)
                if text:
                    return text, web["sources"], provider
        except Exception as e:
            print(f"[{provider}] failed: {str(e)[:300]}")

    # Last resort: show live search results directly, with a clear message
    if not web_done and q and not SMALLTALK.match(q):
        web = web_search(q)
    if web["text"]:
        top = web["text"].split("\n\n")[:3]
        msg = ("My AI brain is not reachable right now, but here is what I found on the web:\n\n"
               + "\n\n".join(top))
        return msg, web["sources"], "search-only"
    return ("Sorry, I could not reach my AI services or the internet just now. "
            "Please try again in a moment."), [], "none"


# ===========================================================================
# TEXT TO SPEECH
# ===========================================================================
def make_audio(text, lang):
    try:
        from gtts import gTTS
        plain = re.sub(r"https?://\S+|[*#_`>\[\]]", "", text).strip()[:350]
        if not plain or lang == "Twi":
            return None
        code = {"English": "en", "Pidgin": "en", "Hausa": "ha"}.get(lang)
        if code is None:
            code = "en" if re.fullmatch(r"[\x00-\x7F]+", plain, re.S) else None
        if code is None:
            return None
        cleanup_old_files()
        name = f"morr_{uuid.uuid4().hex[:8]}.mp3"
        gTTS(text=plain, lang=code).save(os.path.join(GENERATED_DIR, name))
        return f"/audio/{name}"
    except Exception as e:
        print(f"[tts] failed: {str(e)[:150]}")
        return None


# ===========================================================================
# PAGES
# ===========================================================================
HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>MORR AI GH</title>
<style>
*{box-sizing:border-box}
body{margin:0;display:flex;height:100vh;height:100dvh;font-family:system-ui,-apple-system,sans-serif;background:#0a0a0a;color:white}
#sidebar{width:272px;background:#171717;padding:14px;overflow-y:auto;border-right:1px solid #222;display:flex;flex-direction:column;flex-shrink:0}
#main{flex:1;display:flex;flex-direction:column;min-width:0}
#topbar{display:none;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid #222}
#topbar b{color:#FFD700}
#chat{flex:1;overflow-y:auto;padding:16px;max-width:900px;width:100%;margin:0 auto}
.msg{padding:12px 16px;border-radius:18px;margin:10px 0;max-width:88%;line-height:1.6;white-space:pre-wrap;word-wrap:break-word;overflow-wrap:anywhere}
.user{background:#FFD700;color:black;margin-left:auto;border-bottom-right-radius:4px}
.ai{background:#1e1e1e;border:1px solid #333;border-bottom-left-radius:4px}
.msg img{max-width:100%;border-radius:12px;margin-top:8px}
.msg a{color:#FFD700}
.user a{color:#5a4600}
.msg code{background:#000;color:#fff;padding:1px 5px;border-radius:5px}
.src{display:block;font-size:12px;margin-top:8px;color:#aaa;white-space:normal}
.input-area{border-top:1px solid #222;padding:10px;background:#0a0a0a}
.row{display:flex;gap:6px;align-items:center;max-width:900px;margin:0 auto;width:100%}
select{background:#2a2a2a;color:white;padding:10px 6px;border-radius:10px;border:none;max-width:92px}
#q{flex:1;padding:13px;border-radius:12px;border:none;background:#1e1e1e;color:white;font-size:16px;min-width:0}
.btn{padding:11px 13px;background:#FFD700;color:black;border:none;border-radius:12px;font-weight:bold;cursor:pointer}
.btn2{background:#333;color:white}
.side-btn{background:#222;color:#ddd;border:1px solid #333;padding:10px;border-radius:10px;cursor:pointer;width:100%;font-size:14px;margin:8px 0}
.grp{font-size:11px;color:#777;margin:14px 0 4px;text-transform:uppercase}
.hist{display:flex;align-items:center;justify-content:space-between;padding:8px 10px;border-radius:8px;cursor:pointer;color:#bbb;font-size:13px;gap:6px}
.hist:hover,.hist.active{background:#262626;color:white}
.hist span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hist i{font-style:normal;color:#777;padding:0 4px}
.hist i:hover{color:#ff6b6b}
#overlay{display:none}
@media(max-width:800px){
 #sidebar{position:fixed;left:0;top:0;bottom:0;z-index:20;transform:translateX(-100%);transition:transform .2s}
 #sidebar.open{transform:none}
 #overlay.open{display:block;position:fixed;inset:0;background:#0009;z-index:10}
 #topbar{display:flex}
 .msg{max-width:94%}
}
</style></head><body>
<div id="overlay" onclick="toggleSide()"></div>
<div id="sidebar">
 <h3 style="color:#FFD700;margin:0 0 6px">MORR AI GH 🇬🇭</h3>
 {% if user_email %}
 <div style="margin:8px 0;padding:8px;background:#222;border-radius:8px;font-size:13px;word-break:break-all">{{user_email}}<br><a href="/logout" style="color:#FFD700">Logout</a></div>
 {% else %}
 <div style="margin:8px 0;font-size:12px;color:#999">Create a free account to save your chats and open them later.</div>
 <a href="/login" style="display:block;padding:10px;background:#FFD700;color:black;text-align:center;border-radius:8px;font-weight:bold;text-decoration:none;margin-bottom:6px">Log in</a>
 <a href="/signup" style="display:block;padding:10px;background:#222;color:white;text-align:center;border-radius:8px;text-decoration:none;border:1px solid #333">Create account</a>
 {% endif %}
 <button class="side-btn" onclick="newChat()">＋ New chat</button>
 <div id="histList"></div>
</div>
<div id="main">
 <div id="topbar"><button class="btn btn2" onclick="toggleSide()">☰</button><b>MORR AI GH</b></div>
 <div id="chat"></div>
 <div class="input-area">
  <div id="status" style="color:#FFD700;font-size:12px;max-width:900px;margin:0 auto 6px;min-height:14px"></div>
  <div class="row">
   <select id="lang"><option value="Auto">Auto</option><option>English</option><option>Pidgin</option><option>Twi</option><option>Hausa</option></select>
   <input type="file" id="fileInput" hidden onchange="handleFile()" accept=".pdf,.docx,.txt,.csv,.json,.py,.js,.html,.md,.jpg,.jpeg,.png,.webp">
   <button class="btn btn2" onclick="document.getElementById('fileInput').click()">📎</button>
   <input id="q" placeholder="Ask, upload a file, or speak" autocomplete="off">
   <button class="btn" onclick="send()">➤</button>
   <button class="btn btn2" id="micBtn" onclick="toggleMic()">🎤</button>
   <button class="btn btn2" id="spkBtn" onclick="toggleSpeak()" title="Read answers aloud">🔊</button>
  </div>
  <audio id="player" controls style="display:none;width:100%;max-width:900px;margin:8px auto 0"></audio>
 </div>
</div>
<script>
const LOGGED_IN = {{ 'true' if user_email else 'false' }};
let currentConv=null, guestHist=[], attachText='', attachImg='', attachName='', busy=false;
let speak = localStorage.getItem('morr_speak')!=='0';
let recorder, chunks=[], recording=false, recMime='';
const $=id=>document.getElementById(id);
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function fmt(s){return esc(s).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/`([^`\n]+)`/g,'<code>$1</code>').replace(/(https?:\/\/[^\s<]+)/g,'<a href="$1" target="_blank" rel="noopener">$1</a>');}
function addMsg(role,html){const d=document.createElement('div');d.className='msg '+role;d.innerHTML=html;$('chat').appendChild(d);$('chat').scrollTop=$('chat').scrollHeight;return d;}
function srcHtml(srcs){if(!srcs||!srcs.length)return '';return '<span class="src">Sources: '+srcs.slice(0,3).map(s=>'<a href="'+esc(s.url)+'" target="_blank" rel="noopener">'+esc((s.title||s.url).substring(0,40))+'</a>').join(' · ')+'</span>';}
function welcome(){addMsg('ai','Akwaaba! I am MORR AI 🇬🇭<br>I speak English, Pidgin, Twi, Hausa and more. How may I help you today?');}
function toggleSide(){$('sidebar').classList.toggle('open');$('overlay').classList.toggle('open');}
function toggleSpeak(){speak=!speak;localStorage.setItem('morr_speak',speak?'1':'0');$('spkBtn').style.opacity=speak?1:.4;}
$('spkBtn').style.opacity=speak?1:.4;
function grp(iso){const d=new Date(iso),n=new Date();const sd=x=>new Date(x.getFullYear(),x.getMonth(),x.getDate());const diff=Math.round((sd(n)-sd(d))/86400000);if(diff<=0)return'Today';if(diff==1)return'Yesterday';if(diff<=7)return'Previous 7 days';return'Older';}
async function loadConvs(){
 const box=$('histList');box.innerHTML='';
 if(!LOGGED_IN)return;
 try{
  const list=await (await fetch('/api/conversations')).json();
  let last='';
  list.forEach(c=>{
   const g=grp(c.updated);
   if(g!==last){const h=document.createElement('div');h.className='grp';h.textContent=g;box.appendChild(h);last=g;}
   const row=document.createElement('div');row.className='hist'+(c.id===currentConv?' active':'');
   const t=document.createElement('span');t.textContent=c.title||'New chat';
   const x=document.createElement('i');x.textContent='✕';x.title='Delete';
   row.onclick=()=>openConv(c.id);
   x.onclick=ev=>{ev.stopPropagation();delConv(c.id);};
   row.appendChild(t);row.appendChild(x);box.appendChild(row);
  });
 }catch(e){}
}
async function openConv(id){
 try{
  const msgs=await (await fetch('/api/conversations/'+id)).json();
  $('chat').innerHTML='';currentConv=id;
  msgs.forEach(m=>addMsg(m.role==='user'?'user':'ai',fmt(m.content)));
  loadConvs();
  if(window.innerWidth<=800&&$('sidebar').classList.contains('open'))toggleSide();
 }catch(e){$('status').innerText='Could not open that chat';}
}
async function delConv(id){
 if(!confirm('Delete this chat?'))return;
 await fetch('/api/conversations/'+id,{method:'DELETE'});
 if(currentConv===id)newChat();else loadConvs();
}
function newChat(){currentConv=null;guestHist=[];$('chat').innerHTML='';welcome();loadConvs();if(window.innerWidth<=800&&$('sidebar').classList.contains('open'))toggleSide();}
async function send(){
 if(busy)return;
 const i=$('q');const q=i.value.trim();
 if(!q&&!attachText&&!attachImg)return;
 busy=true;
 if(q)addMsg('user',fmt(q));
 i.value='';$('status').innerText='MORR is thinking...';
 const body={question:q,file_context:attachText,image_context:attachImg,attachment_name:attachName,language:$('lang').value,
  conversation_id:currentConv,history:LOGGED_IN?[]:guestHist,speak:speak};
 attachText='';attachImg='';attachName='';$('fileInput').value='';
 try{
  const res=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await res.json();$('status').innerText='';
  addMsg('ai',fmt(data.answer||'No answer')+srcHtml(data.sources));
  if(LOGGED_IN&&data.conversation_id){currentConv=data.conversation_id;loadConvs();}
  if(!LOGGED_IN){guestHist.push({role:'user',content:q},{role:'assistant',content:data.answer||''});guestHist=guestHist.slice(-10);}
  if(data.audio_url){const p=$('player');p.style.display='block';p.src=data.audio_url;p.play().catch(()=>{});}
 }catch(e){$('status').innerText='';addMsg('ai','Error: '+esc(e.message));}
 busy=false;
}
async function handleFile(){
 const f=$('fileInput').files[0];if(!f)return;
 $('status').innerText='Reading '+f.name+'...';
 const fd=new FormData();fd.append('file',f);
 try{
  const data=await (await fetch('/upload',{method:'POST',body:fd})).json();
  if(data.error){$('status').innerText='⚠️ '+data.error;attachText='';attachImg='';attachName='';return;}
  attachText=data.text||'';attachImg=data.image_desc||'';attachName=f.name;
  $('status').innerText='✅ '+f.name+' attached. Now type your question (or just press send).';
  if(data.preview)addMsg('user','📎 '+esc(f.name)+'<br><img src="'+data.preview+'">');
  else addMsg('user','📎 '+esc(f.name));
 }catch(e){$('status').innerText='⚠️ Upload failed: '+e.message;}
}
async function toggleMic(){
 const btn=$('micBtn');
 try{
  if(!recording){
   const s=await navigator.mediaDevices.getUserMedia({audio:true});
   recMime=MediaRecorder.isTypeSupported('audio/webm')?'audio/webm':(MediaRecorder.isTypeSupported('audio/mp4')?'audio/mp4':'');
   recorder=recMime?new MediaRecorder(s,{mimeType:recMime}):new MediaRecorder(s);chunks=[];
   recorder.ondataavailable=e=>chunks.push(e.data);
   recorder.onstop=async()=>{
    const type=recorder.mimeType||recMime||'audio/webm';const ext=type.includes('mp4')?'m4a':'webm';
    const fd=new FormData();fd.append('audio',new Blob(chunks,{type}),'voice.'+ext);fd.append('language',$('lang').value);
    $('status').innerText='Transcribing...';
    try{const d=await (await fetch('/voice',{method:'POST',body:fd})).json();
     if(d.text){$('q').value=d.text;$('status').innerText='';send();}else{$('status').innerText='Could not understand the audio, try again.';}
    }catch(e){$('status').innerText='Voice failed: '+e.message;}
    s.getTracks().forEach(t=>t.stop());
   };
   recorder.start();recording=true;btn.innerText='🔴';
  }else{recorder.stop();recording=false;btn.innerText='🎤';}
 }catch(e){$('status').innerText='Mic error: '+e.message;}
}
$('q').addEventListener('keydown',e=>{if(e.key==='Enter')send();});
welcome();loadConvs();
</script></body></html>"""

AUTH_HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>MORR AI GH - {{ title }}</title></head>
<body style="margin:0;background:#0a0a0a;color:white;font-family:system-ui,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center">
<div style="background:#171717;padding:28px;border-radius:15px;width:min(340px,90vw);border:1px solid #333">
<h2 style="color:#FFD700;margin-top:0">MORR AI GH 🇬🇭</h2><div style="margin-bottom:10px">{{ title }}</div>
{% if error %}<div style="background:#3a1515;border:1px solid #7a2a2a;padding:8px;border-radius:8px;font-size:13px;margin-bottom:8px">{{ error }}</div>{% endif %}
<form method="POST">
<input name="email" type="email" placeholder="Email" value="{{ email or '' }}" required style="width:100%;padding:12px;margin:6px 0;border-radius:8px;border:1px solid #333;background:#222;color:white;font-size:16px">
<input name="password" type="password" placeholder="Password{% if mode == 'signup' %} (min 8 characters){% endif %}" required style="width:100%;padding:12px;margin:6px 0;border-radius:8px;border:1px solid #333;background:#222;color:white;font-size:16px">
<button style="width:100%;padding:12px;border-radius:8px;border:none;background:#FFD700;color:black;font-weight:bold;margin-top:8px;font-size:16px">{{ title }}</button>
</form>
<div style="margin-top:14px;font-size:13px;color:#999">
{% if mode == 'signup' %}Already have an account? <a href="/login" style="color:#FFD700">Log in</a>{% else %}New here? <a href="/signup" style="color:#FFD700">Create an account</a>{% endif %}
 · <a href="/" style="color:#999">Back</a></div></div></body></html>"""

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def current_user():
    return session.get("user_id")


@app.route("/")
def home():
    return render_template_string(HTML, user_email=session.get("email"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = (request.form.get("email") or "").lower().strip()
        pw = request.form.get("password") or ""
        err = None
        if not EMAIL_RE.match(email):
            err = "Please enter a valid email."
        elif len(pw) < 8:
            err = "Password must be at least 8 characters."
        if not err:
            try:
                if db("SELECT id FROM users WHERE email=?", (email,), fetch="one"):
                    err = "An account with that email already exists. Please log in."
                else:
                    uid = db("INSERT INTO users (email, password) VALUES (?, ?)",
                             (email, generate_password_hash(pw)), insert=True)
                    session.clear()
                    session.permanent = True
                    session["user_id"], session["email"] = uid, email
                    return redirect("/")
            except Exception as e:
                print(f"[signup] failed: {e}")
                err = "Could not create the account right now. Please try again."
        return render_template_string(AUTH_HTML, title="Create account", mode="signup", error=err, email=email)
    return render_template_string(AUTH_HTML, title="Create account", mode="signup", error=None, email="")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").lower().strip()
        pw = request.form.get("password") or ""
        try:
            row = db("SELECT id, password FROM users WHERE email=?", (email,), fetch="one")
        except Exception as e:
            print(f"[login] failed: {e}")
            return render_template_string(AUTH_HTML, title="Log in", mode="login",
                                          error="Service busy, please try again.", email=email)
        if row and check_password_hash(row[1], pw):
            session.clear()
            session.permanent = True
            session["user_id"], session["email"] = row[0], email
            return redirect("/")
        return render_template_string(AUTH_HTML, title="Log in", mode="login",
                                      error="Incorrect email or password.", email=email)
    return render_template_string(AUTH_HTML, title="Log in", mode="login", error=None, email="")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ===========================================================================
# CHAT HISTORY API (private to each user)
# ===========================================================================
def owns(cid, uid):
    try:
        cid = int(cid)
    except (TypeError, ValueError):
        return None
    return db("SELECT id FROM conversations WHERE id=? AND user_id=?", (cid, uid), fetch="one")


@app.route("/api/conversations")
def api_conversations():
    uid = current_user()
    if not uid:
        return jsonify([]), 401
    rows = db("SELECT id, title, updated FROM conversations WHERE user_id=? ORDER BY updated DESC LIMIT 100",
              (uid,), fetch="all") or []
    return jsonify([{"id": r[0], "title": r[1], "updated": r[2]} for r in rows])


@app.route("/api/conversations/<int:cid>", methods=["GET", "DELETE"])
def api_conversation(cid):
    uid = current_user()
    if not uid:
        return jsonify({"error": "login required"}), 401
    if not owns(cid, uid):
        return jsonify({"error": "not found"}), 404
    if request.method == "DELETE":
        db("DELETE FROM messages WHERE conversation_id=?", (cid,))
        db("DELETE FROM conversations WHERE id=?", (cid,))
        return jsonify({"ok": True})
    rows = db("SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id", (cid,), fetch="all") or []
    return jsonify([{"role": r[0], "content": r[1]} for r in rows])


# ===========================================================================
# ASK
# ===========================================================================
@app.route("/ask", methods=["POST"])
def ask_route():
    d = request.get_json(silent=True) or {}
    q = (d.get("question") or "").strip()[:4000]
    file_ctx = (d.get("file_context") or "")[:10000]
    img_ctx = (d.get("image_context") or "")[:4000]
    att_name = (d.get("attachment_name") or "")[:100]
    lang = d.get("language") or "Auto"
    if lang not in ("Auto", "English", "Pidgin", "Twi", "Hausa"):
        lang = "Auto"
    if not q and (file_ctx or img_ctx):
        q = "Please read the attached file or image and summarize the key points."
    if not q:
        return jsonify({"answer": "Please type a question."}), 400

    uid = current_user()
    conv_id = d.get("conversation_id")
    history = []
    try:
        if uid:
            if conv_id and not owns(conv_id, uid):
                conv_id = None
            if conv_id:
                rows = db("SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 10",
                          (int(conv_id),), fetch="all") or []
                history = clean_history([{"role": r[0], "content": r[1]} for r in reversed(rows)])
        else:
            history = clean_history(d.get("history"))
    except Exception as e:
        print(f"[ask] history load failed: {e}")
        conv_id = None

    try:
        ans, sources, provider = generate_answer(q, lang, file_ctx, img_ctx, history)
    except Exception as e:
        print(f"[ask] unexpected failure: {e}")
        return jsonify({"answer": "Something went wrong on my side. Please try again."}), 500
    print(f"[ask] answered by {provider}")

    if uid:
        try:
            ts = now_iso()
            if not conv_id:
                conv_id = db("INSERT INTO conversations (user_id, title, created, updated) VALUES (?, ?, ?, ?)",
                             (uid, q[:45], ts, ts), insert=True)
            conv_id = int(conv_id)
            stored_q = (f"📎 {att_name}\n" if att_name else "") + q
            db("INSERT INTO messages (conversation_id, role, content, created) VALUES (?, ?, ?, ?)",
               (conv_id, "user", stored_q, ts))
            db("INSERT INTO messages (conversation_id, role, content, created) VALUES (?, ?, ?, ?)",
               (conv_id, "assistant", ans, now_iso()))
            db("UPDATE conversations SET updated=? WHERE id=?", (now_iso(), conv_id))
        except Exception as e:
            print(f"[ask] saving chat failed: {e}")

    audio_url = make_audio(ans, lang) if d.get("speak") else None
    return jsonify({"answer": ans, "sources": sources, "audio_url": audio_url, "conversation_id": conv_id})


# ===========================================================================
# FILE & IMAGE READER
# ===========================================================================
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
DESCRIBE_PROMPT = ("Describe this image in detail. Transcribe ALL visible text exactly (OCR). "
                   "Mention objects, people (without naming strangers), colours, charts or tables and what they show.")


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "No file received."}), 400
    safe = secure_filename(f.filename) or "upload"
    ext = os.path.splitext(safe.lower())[1]
    tmp = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4().hex[:8]}_{safe}")
    f.save(tmp)
    text, img_desc, preview = "", "", None
    try:
        if ext in IMG_EXT:
            from PIL import Image
            im = Image.open(tmp).convert("RGB")
            big = im.copy()
            big.thumbnail((1600, 1600))
            buf = io.BytesIO()
            big.save(buf, "JPEG", quality=85)
            im.thumbnail((800, 800))
            cleanup_old_files()
            pname = f"prev_{uuid.uuid4().hex[:8]}.jpg"
            im.save(os.path.join(GENERATED_DIR, pname), "JPEG", quality=85)
            preview = f"/media/{pname}"
            if not gclient:
                return jsonify({"error": "Image reading needs GEMINI_API_KEY to be set."})
            try:
                resp = gemini_generate([types.Content(role="user", parts=[
                    types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
                    types.Part(text=DESCRIBE_PROMPT)])])
                img_desc = resp.text or ""
            except Exception as e:
                print(f"[upload] image read failed: {str(e)[:300]}")
                return jsonify({"error": "I could not read that image right now. Please try again in a moment."})
            if not img_desc:
                return jsonify({"error": "I could not make out anything in that image."})
        elif ext == ".pdf":
            import PyPDF2
            reader = PyPDF2.PdfReader(tmp)
            text = " ".join((p.extract_text() or "") for p in reader.pages[:15]).strip()[:10000]
            if len(text) < 30 and gclient and os.path.getsize(tmp) < 10 * 1024 * 1024:
                with open(tmp, "rb") as fh:
                    data = fh.read()
                try:
                    resp = gemini_generate([types.Content(role="user", parts=[
                        types.Part.from_bytes(data=data, mime_type="application/pdf"),
                        types.Part(text="Extract all the text from this document.")])])
                    text = (resp.text or "")[:10000]
                except Exception as e:
                    print(f"[upload] scanned pdf failed: {str(e)[:300]}")
            if not text:
                return jsonify({"error": "I could not find readable text in that PDF."})
        elif ext in (".txt", ".csv", ".py", ".js", ".html", ".json", ".md"):
            with open(tmp, "r", errors="ignore") as fh:
                text = fh.read()[:10000]
        elif ext == ".docx":
            import docx
            text = " ".join(p.text for p in docx.Document(tmp).paragraphs)[:10000]
        else:
            return jsonify({"error": "That file type is not supported. Try PDF, DOCX, TXT, CSV, JSON, JPG, PNG or WEBP."})
    except Exception as e:
        print(f"[upload] failed: {str(e)[:300]}")
        return jsonify({"error": "I could not read that file. It may be damaged or password protected."})
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return jsonify({"text": text, "image_desc": img_desc, "preview": preview})


@app.route("/voice", methods=["POST"])
def voice():
    f = request.files.get("audio")
    if not f:
        return jsonify({"text": ""})
    data = f.read()
    mime = (f.mimetype or "audio/webm").split(";")[0]
    if not mime.startswith("audio/"):
        mime = "audio/webm"
    txt = ""
    try:
        if gclient and data:
            resp = gemini_generate([types.Content(role="user", parts=[
                types.Part.from_bytes(data=data, mime_type=mime),
                types.Part(text="Transcribe this audio exactly as spoken, in its original language "
                                "(English, Pidgin, Twi, Hausa or other). Return only the transcription.")])])
            txt = resp.text or ""
    except Exception as e:
        print(f"[voice] failed: {str(e)[:300]}")
    return jsonify({"text": txt.strip()})


@app.route("/media/<filename>")
def media(filename):
    p = os.path.join(GENERATED_DIR, secure_filename(filename))
    if os.path.exists(p):
        return send_file(p, mimetype="image/jpeg")
    return "not found", 404


@app.route("/download/<filename>")
def dl(filename):
    p = os.path.join(GENERATED_DIR, secure_filename(filename))
    if os.path.exists(p):
        return send_file(p, as_attachment=True)
    return "not found", 404


@app.route("/audio/<filename>")
def au(filename):
    p = os.path.join(GENERATED_DIR, secure_filename(filename))
    if os.path.exists(p):
        return send_file(p, mimetype="audio/mpeg")
    return "not found", 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
