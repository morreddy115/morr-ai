import os, tempfile
from flask import Flask, render_template_string, request, jsonify, send_file
app = Flask(__name__)

MY_GROQ_KEY = os.getenv("GROQ_API_KEY")
from openai import OpenAI
client = OpenAI(api_key=MY_GROQ_KEY, base_url="https://api.groq.com/openai/v1")

try:
    from gtts import gTTS
    HAS_GTTS = True
except:
    HAS_GTTS = False

HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MORR AI GH 🇬🇭</title>
<style>
body{background:#0a0a0a;color:white;font-family:system-ui;margin:0;padding:0;display:flex;flex-direction:column;height:100vh}
.header{padding:14px;text-align:center;border-bottom:1px solid #222}
h1{color:#FFD700;font-size:32px;margin:0}
.sub{color:#aaa;font-size:13px;margin-top:4px}
#chat{flex:1;overflow-y:auto;padding:16px;max-width:850px;width:100%;margin:0 auto;box-sizing:border-box}
.msg{padding:14px 18px;border-radius:18px;margin:8px 0;max-width:85%;line-height:1.7;white-space:pre-wrap;word-wrap:break-word;font-size:14.5px}
.user{background:#FFD700;color:black;margin-left:auto;border-bottom-right-radius:4px}
.ai{background:#1f1f1f;border:1px solid #333;border-bottom-left-radius:4px}
.ai img{max-width:100%;border-radius:12px;margin-top:10px}
.input-area{border-top:1px solid #222;padding:12px;background:#0a0a0a;max-width:850px;margin:0 auto;width:100%;box-sizing:border-box}
.row{display:flex;gap:8px;align-items:center}
select{background:#2a2a2a;color:white;padding:10px;border-radius:10px;border:none}
#q{flex:1;padding:14px;border-radius:12px;border:none;background:#1e1e1e;color:white;font-size:16px}
.btn{padding:12px 16px;background:#FFD700;color:black;border:none;border-radius:12px;font-weight:bold;cursor:pointer}
.btn2{background:#333;color:white}
#fileName{color:#FFD700;font-size:12px;margin:4px 0}
</style></head><body>
<div class="header"><h1>MORR AI GH 🇬🇭</h1><div class="sub">Smart AI • Chat • Images • Files • Like ChatGPT</div></div>
<div id="chat"></div>
<div class="input-area">
<div id="fileName"></div>
<div class="row">
<select id="lang"><option>English</option><option>Pidgin</option><option>Twi</option><option>Hausa</option></select>
<input type="file" id="fileInput" hidden onchange="handleFile()">
<button class="btn btn2" onclick="document.getElementById('fileInput').click()">📎</button>
<input id="q" placeholder="Ask anything, or say 'generate image of...' ">
<button class="btn" onclick="sendText()">➤</button>
<button class="btn btn2" id="micBtn" onclick="toggleMic()">🎤</button>
</div>
<div id="status" style="color:#FFD700;font-size:12px;margin-top:6px"></div>
<audio id="player" controls style="display:none;width:100%;margin-top:8px"></audio>
</div>
<script>
let chatHistory = []; let uploadedText = "";
let recorder,chunks=[],recording=false;
function addMsg(role, text, isImage=false){
 let chat=document.getElementById('chat');
 let div=document.createElement('div'); div.className='msg '+role;
 if(isImage){ div.innerHTML = text + `<br><img src="${isImage}" />`; } else { div.innerText = text; }
 if(role==='ai' &&!isImage) div.innerHTML = text.replace(/\\n/g,'<br>');
 chat.appendChild(div); chat.scrollTop=chat.scrollHeight;
}
async function sendText(){
 let input=document.getElementById('q'); let q=input.value.trim(); if(!q &&!uploadedText) return;
 if(q) addMsg('user', q);
 input.value='';
 document.getElementById('status').innerText="MORR dey think...";
 if(q.toLowerCase().startsWith('generate image') || q.toLowerCase().startsWith('create image') || q.toLowerCase().includes('/image')){
   let prompt = q.replace(/generate image of/i,'').replace(/create image of/i,'').replace('/image','').trim();
   let imgUrl = `https://image.pollinations.ai/prompt/${encodeURIComponent(prompt)}?width=1024&height=1024&nologo=true&seed=${Date.now()}`;
   document.getElementById('status').innerText="";
   addMsg('ai', `🎨 Generated: ${prompt}`, imgUrl);
   chatHistory.push({role:'user',content:q},{role:'assistant',content:`Generated image: ${prompt}`});
   clearFile(); return;
 }
 try{
  let res=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({question:q, file_context: uploadedText, language: document.getElementById('lang').value, history: chatHistory})});
  let data=await res.json();
  document.getElementById('status').innerText="";
  addMsg('ai', data.answer);
  chatHistory.push({role:'user',content:q},{role:'assistant',content:data.answer});
  if(data.audio_url){let p=document.getElementById('player');p.style.display='block';p.src=data.audio_url+"?t="+Date.now();}
 }catch(e){ document.getElementById('status').innerText="Error, try again"; }
 clearFile();
}
function clearFile(){ uploadedText=""; document.getElementById('fileName').innerText=""; document.getElementById('fileInput').value=""; }
async function handleFile(){
 let file=document.getElementById('fileInput').files[0]; if(!file) return;
 document.getElementById('fileName').innerText="📄 "+file.name+" uploading...";
 let fd=new FormData(); fd.append('file',file);
 let res=await fetch('/upload',{method:'POST',body:fd}); let data=await res.json();
 uploadedText = data.text || "";
 document.getElementById('fileName').innerText="✅ "+file.name+" attached - now ask about it";
}
async function toggleMic(){
 let btn=document.getElementById('micBtn');
 if(!recording){let s=await navigator.mediaDevices.getUserMedia({audio:true});recorder=new MediaRecorder(s);chunks=[];
 recorder.ondataavailable=e=>chunks.push(e.data);
 recorder.onstop=async()=>{let blob=new Blob(chunks,{type:'audio/webm'});let fd=new FormData();fd.append('audio',blob,'voice.webm');fd.append('language',document.getElementById('lang').value);
 document.getElementById('status').innerText="Listening...";let res=await fetch('/voice',{method:'POST',body:fd});let data=await res.json();
 if(data.text){document.getElementById('q').value=data.text;await sendText();} };
 recorder.start();recording=true;btn.innerText="🔴";}else{recorder.stop();recording=false;btn.innerText="🎤";}}
document.getElementById('q').addEventListener('keypress',function(e){if(e.key==='Enter')sendText();});
addMsg('ai','Akwaaba! I am MORR AI GH 🇬🇭\\nFixed & Accurate!\\n• Current President: John Mahama (2025)\\n• Ask me anything!\\nWhat should we do today?');
</script></body></html>"""

def build_prompt(lang, has_file=False):
    extra = " File provided, use it." if has_file else ""
    return f"""You are MORR AI GH, Ghana's accurate assistant. TODAY IS: October 2026.

MUST KNOW (CURRENT 2026):
- Ghana President: John Dramani Mahama (started Jan 7, 2025). Vice: Jane Naana Opoku-Agyemang. Previous: Nana Akufo-Addo (2017-Jan 2025).
- Never say Akufo-Addo is current president.
- Nigeria: Bola Tinubu. USA: Donald Trump (2nd term from Jan 2025).
- If unsure, say you will verify but give 2026 context.

Answer in {lang}, accurate, short, friendly. {extra} 🇬🇭"""

@app.route("/")
def home(): return render_template_string(HTML)

@app.route("/upload", methods=["POST"])
def upload():
    f=request.files.get('file')
    if not f: return jsonify({"text":""})
    name=f.filename.lower()
    tmp=os.path.join(tempfile.gettempdir(), f.filename)
    f.save(tmp)
    text=""
    try:
        if name.endswith(('.png','.jpg','.jpeg','.webp')): text=f"[IMAGE: {f.filename}]"
        elif name.endswith('.pdf'):
            import PyPDF2
            reader=PyPDF2.PdfReader(tmp)
            text="\\n".join([p.extract_text() for p in reader.pages[:10]])
        elif name.endswith(('.txt','.csv','.py','.js','.html','.json','.md')):
            with open(tmp,'r',errors='ignore') as file: text=file.read()[:8000]
        elif name.endswith('.docx'):
            import docx
            doc=docx.Document(tmp)
            text="\\n".join([p.text for p in doc.paragraphs])[:8000]
        else: text=f"[File {f.filename}]"
    except: text=f"[File {f.filename}]"
    return jsonify({"text":text[:8000]})

@app.route("/ask", methods=["POST"])
def ask():
    d=request.get_json(); q=d.get("question",""); lang=d.get("language","English")
    file_ctx=d.get("file_context",""); history=d.get("history",[])[:10]
    full_q = f"FILE:{file_ctx}\\nQ:{q}" if file_ctx else q
    messages=[{"role":"system","content":build_prompt(lang, bool(file_ctx))}]
    for h in history: messages.append(h)
    messages.append({"role":"user","content":full_q})
    ans="Error"
    # TRY CORRECT GROQ MODELS
    for model_name in ["llama-3.3-70b-versatile", "llama3-8b-8192", "openai/gpt-oss-20b", "openai/gpt-oss-120b"]:
        try:
            resp=client.chat.completions.create(model=model_name, messages=messages, temperature=0.2, max_tokens=1200)
            ans=resp.choices[0].message.content
            break
        except Exception as e:
            ans=f"Retrying... {e}"
            continue
    try:
        fn=f"morr_{lang}.mp3"; fp=os.path.join(os.path.dirname(__file__), fn)
        if HAS_GTTS: gTTS(text=ans[:300], lang='en').save(fp); audio=f"/audio/{fn}"
        else: audio=None
    except: audio=None
    return jsonify({"answer":ans,"audio_url":audio})

@app.route("/voice", methods=["POST"])
def voice():
    lang=request.form.get("language","English"); f=request.files.get("audio")
    tmp=os.path.join(tempfile.gettempdir(),"in.webm"); f.save(tmp); txt=""
    try:
        with open(tmp,"rb") as af: txt=client.audio.transcriptions.create(model="whisper-large-v3", file=af).text
    except: txt=""
    return jsonify({"text":txt or "Hi"})

@app.route("/audio/<filename>")
def serve_audio(filename):
    p=os.path.join(os.path.dirname(__file__), filename)
    if os.path.exists(p): return send_file(p, mimetype="audio/mpeg")
    return "not found",404

if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
