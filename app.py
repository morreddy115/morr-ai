import os
import sqlite3
import tempfile
import uuid
import requests
import json
from flask import Flask, render_template_string, request, jsonify, session, redirect, send_file
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "morr-gh-2026-final-v3")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
GENERATED_DIR = os.path.join(tempfile.gettempdir(), "morr_ai_generated")
os.makedirs(GENERATED_DIR, exist_ok=True)

# --- DB ---
def init_db():
    conn = sqlite3.connect('morr.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT UNIQUE, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT, q TEXT, a TEXT, created TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()
init_db()

# --- INTERNET SEARCH: WHOLE INTERNET (Not Wikipedia only) ---
def search_whole_internet(query):
    """Searches entire web via DuckDuckGo - no API key needed"""
    results_text = ""
    images = []
    sources = []
    try:
        # Try duckduckgo-search library
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            for r in results:
                results_text += f"\nTitle: {r.get('title')}\nSnippet: {r.get('body')}\nSource: {r.get('href')}\n"
                sources.append(r.get('href'))
    except Exception as e:
        print(f"DDGS error: {e}")
        # Fallback to Wikipedia if DDGS not available
        try:
            r = requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(query)}", timeout=8, headers={"User-Agent":"MORR AI GH"})
            if r.status_code==200:
                j=r.json()
                results_text = j.get("extract","")
                if j.get("originalimage"):
                    images.append(j["originalimage"]["source"])
                sources.append(j.get("content_urls",{}).get("desktop",{}).get("page"))
        except:
            pass
    return {"text": results_text[:6000], "images": images, "sources": sources}

# --- SMART BRAIN: Groq (FREE) + Gemini Backup ---
def ask_smart_brain(question, internet_context, history_text, lang):
    GROQ_KEY = os.getenv("GROQ_API_KEY")
    GEMINI_KEY = os.getenv("GEMINI_API_KEY")

    system_prompt = f"""You are MORR AI GH, Ghana's smartest AI, built by Morr.
You are like Meta AI, ChatGPT, friendly, witty, proudly Ghanaian. Language: {lang}.
You have LIVE internet context below. Use it to answer accurately.
- If user says "how are you doing" -> say "Chale I'm good oo! How for you? How I fit help you today?" NOT song definition.
- If President of Gabon -> Brice Oligui Nguema (took over Aug 2023, elected 2025)
- If Jamaica President -> Explain Jamaica has NO President, it has Prime Minister Andrew Holness and King Charles as head of state.
- Keep answers short, helpful, human, Ghana vibe when needed.
- If internet context has info, cite it.
"""

    full_prompt = f"{system_prompt}\n\nINTERNET LIVE RESULTS:\n{internet_context}\n\nCHAT HISTORY:\n{history_text}\n\nUSER QUESTION: {question}\n\nAnswer:"

    # 1. Try GROQ (FREE, STABLE, Llama - same tech as Meta AI)
    if GROQ_KEY:
        try:
            from groq import Groq
            client = Groq(api_key=GROQ_KEY)
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role":"user","content": full_prompt}],
                temperature=0.7,
                max_tokens=800
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"Groq failed: {e}")

    # 2. Try Gemini as backup
    if GEMINI_KEY:
        try:
            from google import genai
            from google.genai import types
            gclient = genai.Client(api_key=GEMINI_KEY)
            resp = gclient.models.generate_content(
                model="gemini-2.0-flash",
                contents=full_prompt,
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
            )
            return resp.text
        except Exception as e:
            print(f"Gemini failed: {e}")

    # 3. FINAL FALLBACK: No API key at all - answer from internet context itself
    if internet_context:
        return f"Based on live internet search for '{question}':\n\n{internet_context[:1000]}\n\n(Note: Add GROQ_API_KEY in Render for smarter replies)"
    return "Chale, I'm having small network issue, but I'm here! Try ask again — How I fit help you?"

HTML = """
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>MORR AI GH - V3</title>
<style>
body{margin:0;display:flex;height:100vh;font-family:system-ui;background:#0a0a0a;color:white}
#sidebar{width:270px;background:#171717;padding:15px;overflow-y:auto;border-right:1px solid #222;display:flex;flex-direction:column}
#main{flex:1;display:flex;flex-direction:column;max-width:100%}
#chat{flex:1;overflow-y:auto;padding:20px;max-width:900px;width:100%;margin:0 auto;box-sizing:border-box}
.msg{padding:14px 18px;border-radius:18px;margin:10px 0;max-width:90%;line-height:1.6;font-size:14.5px;white-space:pre-wrap;word-wrap:break-word}
.user{background:#FFD700;color:black;margin-left:auto}
.ai{background:#1e1e1e;border:1px solid #333}
.input-area{border-top:1px solid #222;padding:12px;background:#0a0a0a}
.row{display:flex;gap:8px;max-width:900px;margin:0 auto;width:100%}
#q{flex:1;padding:14px;border-radius:12px;border:none;background:#1e1e1e;color:white;font-size:16px}
.btn{padding:12px 18px;background:#FFD700;color:black;border:none;border-radius:12px;font-weight:bold;cursor:pointer}
.hist{padding:8px 10px;border-radius:8px;cursor:pointer;color:#aaa;font-size:13px;margin:4px 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hist:hover{background:#222;color:white}
.small{font-size:11px;color:#666}
a{color:#FFD700}
</style></head><body>
<div id="sidebar">
<h3 style="color:#FFD700;margin:0">MORR AI GH <span style="font-size:12px;background:#FFD700;color:black;padding:2px 6px;border-radius:6px">V3</span></h3>
<div class="small">Whole Internet + Llama Brain</div>
{% if user_email %}
<div style="margin:12px 0;padding:8px;background:#222;border-radius:8px;font-size:13px">{{ user_email }}<br><a href="/logout">Logout</a></div>
{% else %}
<a href="/login" style="display:block;margin:12px 0;padding:10px;background:white;color:black;text-align:center;border-radius:8px;font-weight:bold;text-decoration:none">Login / Create Account</a>
{% endif %}
<hr style="border-color:#222;width:100%">
<button onclick="localStorage.clear();location.reload()" style="background:#222;color:#aaa;border:none;padding:6px 10px;border-radius:6px;cursor:pointer;font-size:12px">+ New Chat</button>
<div style="margin-top:12px" id="histList"></div>
</div>
<div id="main">
<div id="chat"><div class="msg ai">Akwaaba! I am MORR AI V3 🇬🇭\nHow May I Help You Today</div></div>
<div class="input-area"><div class="row">
<input id="q" placeholder="Ask anything... Twi, Pidgin, English"><button class="btn" onclick="send()">➤</button>
</div><div id="status" style="max-width:900px;margin:5px auto;color:#FFD700;font-size:12px"></div></div>
</div>
<script>
let history = JSON.parse(localStorage.getItem('morr_v3_hist')||'[]');
function renderHist(){
 const d=document.getElementById('histList');
 d.innerHTML='<div class="small">Recent Commands</div>'+history.slice().reverse().slice(0,20).map(h=>`<div class="hist" onclick="document.getElementById('q').value='${h.q.replace(/'/g,'')}';">${h.q.substring(0,35)}</div>`).join('');
}
renderHist();
async function send(){
 let q=document.getElementById('q').value.trim(); if(!q) return;
 document.getElementById('q').value='';
 let chat=document.getElementById('chat');
 chat.innerHTML+=`<div class="msg user">${q}</div>`;
 history.push({q}); localStorage.setItem('morr_v3_hist', JSON.stringify(history)); renderHist();
 document.getElementById('status').innerText='MORR dey search whole internet + thinking...';
 try{
  let res=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});
  let data=await res.json();
  let html=data.answer.replace(/</g,'&lt;').replace(/\\n/g,'<br>');
  if(data.sources && data.sources.length){ html+=`<br><br><small>Sources: ${data.sources.slice(0,2).map(s=>`<a href="${s}" target="_blank">${s.substring(0,30)}...</a>`).join(' | ')}</small>`; }
  chat.innerHTML+=`<div class="msg ai">${html}</div>`;
 }catch(e){ chat.innerHTML+=`<div class="msg ai">Error: ${e.message}</div>`; }
 document.getElementById('status').innerText=''; chat.scrollTop=chat.scrollHeight;
}
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter')send()});
</script></body></html>
"""

LOGIN_HTML = """<div style="background:#0a0a0a;color:white;height:100vh;display:flex;align-items:center;justify-content:center;font-family:system-ui"><div style="background:#171717;padding:30px;border-radius:15px;width:320px;border:1px solid #333"><h2 style="color:#FFD700">MORR AI GH V3</h2><form method="POST"><input name="email" placeholder="Email" required style="width:100%;padding:12px;margin:8px 0;border-radius:8px;border:1px solid #333;background:#222;color:white"><input name="password" type="password" placeholder="Password" required style="width:100%;padding:12px;margin:8px 0;border-radius:8px;border:1px solid #333;background:#222;color:white"><button style="width:100%;padding:12px;border-radius:8px;border:none;background:#FFD700;color:black;font-weight:bold;margin-top:10px">Login / Create Account</button></form><p style="font-size:11px;color:#888;margin-top:12px">If email new, we create account. If exists, we login.</p><a href="/" style="color:#666;font-size:12px">Back to chat</a></div></div>"""

@app.route("/")
def home():
    return render_template_string(HTML, user_email=session.get("email"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form["email"].lower().strip()
        password=request.form["password"]
        conn=sqlite3.connect('morr.db'); c=conn.cursor()
        c.execute("SELECT id,password FROM users WHERE email=?", (email,)); row=c.fetchone()
        if row and check_password_hash(row[1], password):
            session["user_id"]=row[0]; session["email"]=email; conn.close(); return redirect("/")
        elif row:
            conn.close(); return "Wrong password <a href='/login'>Back</a>"
        else:
            hashed=generate_password_hash(password)
            c.execute("INSERT INTO users (email,password) VALUES (?,?)", (email,hashed)); conn.commit()
            session["user_id"]=c.lastrowid; session["email"]=email; conn.close(); return redirect("/")
    return render_template_string(LOGIN_HTML)

@app.route("/logout")
def logout():
    session.clear(); return redirect("/")

@app.route("/ask", methods=["POST"])
def ask_route():
    data=request.get_json(); q=data.get("question","").strip()
    if not q: return jsonify({"answer":"Ask something"})
    # 1. Search whole internet
    web = search_whole_internet(q)
    # 2. Ask smart brain
    answer = ask_smart_brain(q, web["text"], "", "English")
    # Save chat if logged in
    if session.get("user_id"):
        try:
            conn=sqlite3.connect('morr.db'); c=conn.cursor()
            c.execute("INSERT INTO chats (user_id,title,q,a) VALUES (?,?,?,?)", (session["user_id"], q[:50], q, answer))
            conn.commit(); conn.close()
        except: pass
    return jsonify({"answer": answer, "sources": web["sources"]})

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
