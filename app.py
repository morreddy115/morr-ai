import os, sqlite3, tempfile, uuid, requests, json
from flask import Flask, render_template_string, request, jsonify, session, redirect, send_file
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "morr-final-2026")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
GENERATED_DIR = os.path.join(tempfile.gettempdir(), "morr_ai_generated")
os.makedirs(GENERATED_DIR, exist_ok=True)

def init_db():
    conn = sqlite3.connect('morr.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT UNIQUE, password TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT, q TEXT, a TEXT, created TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    conn.commit(); conn.close()
init_db()

# --- WHOLE INTERNET SEARCH - FIXED ---
def search_whole_internet(query):
    text = ""; sources = []
    if not query or len(query.strip()) < 2:
        return {"text": "", "sources": []}
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            for r in list(ddgs.text(query, max_results=6)):
                text += f"{r.get('title')}: {r.get('body')} Source:{r.get('href')}\n"
                sources.append(r.get('href'))
    except Exception as e:
        print(f"DDGS fail: {e}")
    return {"text": text[:6000], "sources": sources}

# --- SMART BRAIN - FIXED (No more Add GROQ_API_KEY error) ---
def ask_smart_brain(question, web_text, file_text, image_desc, lang, history):
    GROQ_KEY = (os.getenv("GROQ_API_KEY") or "").strip()
    GEMINI_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()

    system = f"""You are MORR AI GH built by Morr. Like Meta AI. Language: {lang}. Ghanaian, friendly, concise.
Rules:
- 'how are you doing' => human greeting, not song.
- If file or image uploaded, use that context first.
"""
    file_context = f"FILE: {file_text[:4000]} IMAGE: {image_desc[:2000]}" if (file_text or image_desc) else ""
    prompt = f"{system}\nINTERNET: {web_text[:5000]}\n{file_context}\nHISTORY: {history[-4:]}\nQUESTION: {question}\nAnswer:"

    if GROQ_KEY and GROQ_KEY.startswith("gsk_"):
        try:
            from groq import Groq
            client = Groq(api_key=GROQ_KEY)
            comp = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":prompt}], max_tokens=900, temperature=0.7)
            if comp.choices and comp.choices[0].message.content:
                return comp.choices[0].message.content
        except Exception as e:
            print(f"Groq fail: {e}")

    if GEMINI_KEY:
        try:
            from google import genai
            from google.genai import types
            gclient = genai.Client(api_key=GEMINI_KEY)
            resp = gclient.models.generate_content(model="gemini-2.0-flash", contents=prompt, config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
            if resp.text:
                return resp.text
        except Exception as e:
            print(f"Gemini fail: {e}")

    # FINAL FALLBACK - FIXED: Never shows Add GROQ key again
    if web_text:
        return web_text[:1200]
    if file_text or image_desc:
        return f"I received your file/image. {file_text[:500] or image_desc[:500]} \n\nWhat should I do with it? Summarize, explain, or analyze?"
    return "Chale I'm here! My internet search came empty, try ask again. How may I help you today?"

HTML = """
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>MORR AI GH - V3.1</title>
<style>
body{margin:0;display:flex;height:100vh;font-family:system-ui;background:#0a0a0a;color:white}
#sidebar{width:270px;background:#171717;padding:14px;overflow-y:auto;border-right:1px solid #222;display:flex;flex-direction:column}
#main{flex:1;display:flex;flex-direction:column}
#chat{flex:1;overflow-y:auto;padding:16px;max-width:900px;width:100%;margin:0 auto;box-sizing:border-box}
.msg{padding:14px 18px;border-radius:18px;margin:10px 0;max-width:88%;line-height:1.6;white-space:pre-wrap;word-wrap:break-word}
.user{background:#FFD700;color:black;margin-left:auto;border-bottom-right-radius:4px}
.ai{background:#1e1e1e;border:1px solid #333;border-bottom-left-radius:4px}
.input-area{border-top:1px solid #222;padding:12px;background:#0a0a0a}
.row{display:flex;gap:8px;align-items:center;max-width:900px;margin:0 auto;width:100%}
select{background:#2a2a2a;color:white;padding:10px;border-radius:10px;border:none}
#q{flex:1;padding:14px;border-radius:12px;border:none;background:#1e1e1e;color:white;font-size:16px;min-width:0}
.btn{padding:12px 16px;background:#FFD700;color:black;border:none;border-radius:12px;font-weight:bold;cursor:pointer}
.btn2{background:#333;color:white}
.msg img{max-width:100%;border-radius:12px;margin-top:8px}
.hist{padding:8px 10px;border-radius:8px;cursor:pointer;color:#aaa;font-size:13px}
.hist:hover{background:#222;color:white}
</style></head><body>
<div id="sidebar">
<h3 style="color:#FFD700;margin:0">MORR AI GH <span style="font-size:12px;background:#FFD700;color:black;padding:2px 6px;border-radius:6px">V3.1</span></h3>
{% if user_email %}<div style="margin:10px 0;padding:8px;background:#222;border-radius:8px;font-size:13px">{{user_email}}<br><a href="/logout" style="color:#FFD700">Logout</a></div>
{% else %}<a href="/login" style="display:block;margin:12px 0;padding:10px;background:white;color:black;text-align:center;border-radius:8px;font-weight:bold;text-decoration:none">Login / Create Account</a>{% endif %}
<button onclick="localStorage.removeItem('morr_v3_hist');location.reload()" style="background:#222;color:#aaa;border:none;padding:6px 10px;border-radius:6px;cursor:pointer;font-size:12px">+ New Chat</button>
<div id="histList" style="margin-top:10px"></div>
</div>
<div id="main">
<div id="chat"><div class="msg ai">Akwaaba! I am MORR AI V3 🇬🇭
How May I Help You Today</div></div>
<div class="input-area">
<div id="status" style="color:#FFD700;font-size:12px;max-width:900px;margin:0 auto 6px"></div>
<div class="row">
<select id="lang"><option>English</option><option>Pidgin</option><option>Twi</option><option>Hausa</option></select>
<input type="file" id="fileInput" hidden onchange="handleFile()" accept=".pdf,.docx,.txt,.csv,.json,.py,.js,.html,.md,.jpg,.jpeg,.png,.webp">
<button class="btn btn2" onclick="document.getElementById('fileInput').click()">📎</button>
<input id="q" placeholder="Ask, upload image, or speak"><button class="btn" onclick="send()">➤</button>
<button class="btn btn2" id="micBtn" onclick="toggleMic()">🎤</button>
</div>
<audio id="player" controls style="display:none;width:100%;max-width:900px;margin:8px auto 0"></audio>
</div>
</div>
<script>
let hist=JSON.parse(localStorage.getItem('morr_v3_hist')||'[]');
let uploadedText="", uploadedImageDesc=""; let recorder,chunks=[],recording=false;
function renderHist(){document.getElementById('histList').innerHTML='<div style="font-size:11px;color:#666">Recent Commands</div>'+hist.slice().reverse().slice(0,20).map(h=>`<div class="hist">${h.q.substring(0,32)}</div>`).join('')}
renderHist();
function addMsg(role,text,isHtml=false){let c=document.getElementById('chat');let d=document.createElement('div');d.className='msg '+role;if(isHtml)d.innerHTML=text;else d.textContent=text;c.appendChild(d);c.scrollTop=c.scrollHeight}
async function send(){
 let i=document.getElementById('q'); let q=i.value.trim(); if(!q &&!uploadedText &&!uploadedImageDesc) return;
 if(q) addMsg('user',q); i.value=''; document.getElementById('status').innerText='MORR dey search whole internet...';
 try{
  let body={question:q,file_context:uploadedText,image_context:uploadedImageDesc,language:document.getElementById('lang').value};
  let res=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  let data=await res.json(); document.getElementById('status').innerText='';
  let out=data.answer||'No answer'; if(data.image_url) out+=`<br><img src="${data.image_url}">`; if(data.source_url) out+=`<br><small><a href="${data.source_url}" target="_blank">🔗 Source</a></small>`;
  if(data.sources) out+=`<br><small>${data.sources.slice(0,2).map(s=>`<a href="${s}" target="_blank">${s.substring(0,35)}...</a>`).join(' | ')}</small>`;
  addMsg('ai',out,true); hist.push({q}); localStorage.setItem('morr_v3_hist',JSON.stringify(hist)); renderHist();
  if(data.audio_url){let p=document.getElementById('player');p.style.display='block';p.src=data.audio_url+'?t='+Date.now(); p.play();}
 }catch(e){addMsg('ai','Error: '+e.message)} uploadedText=''; uploadedImageDesc=''; document.getElementById('fileInput').value='';
}
async function handleFile(){
 let f=document.getElementById('fileInput').files[0]; if(!f) return;
 document.getElementById('status').innerText='📄 Analyzing '+f.name+'...';
 let fd=new FormData(); fd.append('file',f);
 let res=await fetch('/upload',{method:'POST',body:fd}); let data=await res.json();
 uploadedText=data.text||''; uploadedImageDesc=data.image_desc||'';
 document.getElementById('status').innerText='✅ '+f.name+' ready';
 if(data.preview){addMsg('user','[Uploaded: '+f.name+']<br><img src="'+data.preview+'">',true);}
}
async function toggleMic(){
 let btn=document.getElementById('micBtn');
 try{
  if(!recording){let s=await navigator.mediaDevices.getUserMedia({audio:true}); recorder=new MediaRecorder(s); chunks=[]; recorder.ondataavailable=e=>chunks.push(e.data);
   recorder.onstop=async()=>{let blob=new Blob(chunks,{type:'audio/webm'});let fd=new FormData();fd.append('audio',blob,'voice.webm');fd.append('language',document.getElementById('lang').value);document.getElementById('status').innerText='Transcribing...';let res=await fetch('/voice',{method:'POST',body:fd});let d=await res.json();if(d.text){document.getElementById('q').value=d.text;send();} s.getTracks().forEach(t=>t.stop());}; recorder.start(); recording=true; btn.innerText='🔴';
  }else{recorder.stop(); recording=false; btn.innerText='🎤';}
 }catch(e){document.getElementById('status').innerText='Mic error: '+e.message;}
}
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter')send()});
</script></body></html>
"""

LOGIN_HTML = """<div style="background:#0a0a0a;color:white;height:100vh;display:flex;align-items:center;justify-content:center;font-family:system-ui"><div style="background:#171717;padding:30px;border-radius:15px;width:320px;border:1px solid #333"><h2 style="color:#FFD700">MORR AI GH V3.1</h2><form method="POST"><input name="email" placeholder="Email" required style="width:100%;padding:12px;margin:8px 0;border-radius:8px;border:1px solid #333;background:#222;color:white"><input name="password" type="password" placeholder="Password" required style="width:100%;padding:12px;margin:8px 0;border-radius:8px;border:1px solid #333;background:#222;color:white"><button style="width:100%;padding:12px;border-radius:8px;border:none;background:#FFD700;color:black;font-weight:bold;margin-top:10px">Login / Create Account</button></form><a href="/" style="color:#666;font-size:12px">Back</a></div></div>"""

@app.route("/")
def home(): return render_template_string(HTML, user_email=session.get("email"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form["email"].lower().strip(); pw=request.form["password"]
        conn=sqlite3.connect('morr.db'); c=conn.cursor()
        c.execute("SELECT id,password FROM users WHERE email=?", (email,)); row=c.fetchone()
        if row and check_password_hash(row[1], pw): session["user_id"]=row[0]; session["email"]=email; conn.close(); return redirect("/")
        elif row: conn.close(); return "Wrong password <a href='/login'>Back</a>"
        else: c.execute("INSERT INTO users (email,password) VALUES (?,?)", (email, generate_password_hash(pw))); conn.commit(); session["user_id"]=c.lastrowid; session["email"]=email; conn.close(); return redirect("/")
    return render_template_string(LOGIN_HTML)

@app.route("/logout")
def logout(): session.clear(); return redirect("/")

@app.route("/upload", methods=["POST"])
def upload():
    f=request.files.get('file')
    if not f: return jsonify({"text":""}),400
    tmp=os.path.join(tempfile.gettempdir(), f.filename); f.save(tmp)
    text=""; img_desc=""; preview=None
    is_img=f.filename.lower().endswith(('.jpg','.jpeg','.png','.webp','.bmp'))
    try:
        if is_img:
            from PIL import Image
            prev_name=f"prev_{uuid.uuid4().hex[:6]}_{os.path.basename(tmp)}"; prev_path=os.path.join(GENERATED_DIR, prev_name)
            try: im=Image.open(tmp); im.thumbnail((800,800)); im.save(prev_path); preview=f"/download/{prev_name}"
            except: pass
            GEMINI_KEY=os.getenv("GEMINI_API_KEY")
            if GEMINI_KEY:
                try:
                    from google import genai
                    client=genai.Client(api_key=GEMINI_KEY)
                    uploaded=client.files.upload(file=tmp)
                    resp=client.models.generate_content(model="gemini-2.0-flash", contents=["Describe this image in detail, read any text, who is it?", uploaded])
                    img_desc=resp.text or ""
                except Exception as e: img_desc=f"Image {f.filename} uploaded"
            text=f"[IMAGE: {f.filename}] {img_desc}"
        elif f.filename.lower().endswith('.pdf'):
            import PyPDF2; r=PyPDF2.PdfReader(tmp); text=" ".join([(p.extract_text() or "") for p in r.pages[:10]])[:10000]
        elif f.filename.lower().endswith(('.txt','.csv','.py','.js','.html','.json','.md')):
            with open(tmp,'r',errors='ignore') as file: text=file.read()[:10000]
        elif f.filename.lower().endswith('.docx'):
            import docx; doc=docx.Document(tmp); text=" ".join([p.text for p in doc.paragraphs])[:10000]
    except Exception as e: text=f"File read error: {e}"
    return jsonify({"text":text, "image_desc":img_desc, "preview":preview})

@app.route("/ask", methods=["POST"])
def ask_route():
    d=request.get_json(); q=d.get("question","") or ""; file_ctx=d.get("file_context",""); img_ctx=d.get("image_context",""); lang=d.get("language","English")
    web=search_whole_internet(q if q else file_ctx[:100] or img_ctx[:100])
    ans=ask_smart_brain(q, web["text"], file_ctx, img_ctx, lang, [])
    audio_url=None
    try:
        from gtts import gTTS
        fname=f"morr_{uuid.uuid4().hex[:6]}.mp3"; fpath=os.path.join(GENERATED_DIR, fname)
        gTTS(text=ans[:400], lang='en').save(fpath); audio_url=f"/audio/{fname}"
    except: pass
    return jsonify({"answer":ans, "sources":web["sources"], "audio_url":audio_url})

@app.route("/voice", methods=["POST"])
def voice():
    f=request.files.get("audio"); tmp=os.path.join(tempfile.gettempdir(), f"voice_{uuid.uuid4().hex}.webm"); f.save(tmp); txt=""
    try:
        GEMINI_KEY=os.getenv("GEMINI_API_KEY")
        if GEMINI_KEY:
            from google import genai
            client=genai.Client(api_key=GEMINI_KEY); uploaded=client.files.upload(file=tmp)
            resp=client.models.generate_content(model="gemini-2.0-flash", contents=["Transcribe this audio exactly:", uploaded]); txt=resp.text or ""
    except: pass
    try: os.remove(tmp)
    except: pass
    return jsonify({"text": txt.strip()})

@app.route("/download/<filename>")
def dl(filename):
    p=os.path.join(GENERATED_DIR, filename)
    if os.path.exists(p): return send_file(p, as_attachment=True)
    return "not found",404
@app.route("/audio/<filename>")
def au(filename):
    p=os.path.join(GENERATED_DIR, filename)
    if os.path.exists(p): return send_file(p, mimetype="audio/mpeg")
    return "not found",404

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
