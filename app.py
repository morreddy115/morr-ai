import os, tempfile, urllib.parse
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
<title>MORR AI GH</title>
<link rel="manifest" href="/manifest.json">
<style>
body{background:#0a0a0a;color:white;font-family:system-ui;margin:0;padding:0;display:flex;flex-direction:column;height:100vh}
.header{padding:14px;text-align:center;border-bottom:1px solid #222}
h1{color:#FFD700;font-size:32px;margin:0;display:flex;align-items:center;justify-content:center;gap:8px}
.sub{color:#aaa;font-size:13px;margin-top:4px}
#chat{flex:1;overflow-y:auto;padding:16px;max-width:850px;width:100%;margin:0 auto;box-sizing:border-box}
.msg{padding:14px 18px;border-radius:18px;margin:8px 0;max-width:85%;line-height:1.7;word-wrap:break-word;font-size:14.5px;white-space:pre-wrap}
.user{background:#FFD700;color:black;margin-left:auto;border-bottom-right-radius:4px}
.ai{background:#1f1f1f;border:1px solid #333;border-bottom-left-radius:4px}
.input-area{border-top:1px solid #222;padding:12px;background:#0a0a0a;max-width:850px;margin:0 auto;width:100%;box-sizing:border-box}
.row{display:flex;gap:8px;align-items:center}
select{background:#2a2a2a;color:white;padding:10px;border-radius:10px;border:none}
#q{flex:1;padding:14px;border-radius:12px;border:none;background:#1e1e1e;color:white;font-size:16px}
.btn{padding:12px 16px;background:#FFD700;color:black;border:none;border-radius:12px;font-weight:bold;cursor:pointer}
.btn2{background:#333;color:white}
</style></head><body>
<div class="header"><h1>MORR AI GH <img src="https://flagcdn.com/w20/gh.png" style="width:24px;height:18px;border-radius:3px;vertical-align:middle" alt="GH"></h1><div class="sub">Smart AI • Chat • Images • Files • Like Meta AI</div></div>
<div id="chat"></div>
<div class="input-area">
<div id="status" style="color:#FFD700;font-size:12px;margin-top:6px"></div>
<div class="row">
<select id="lang"><option>English</option><option>Pidgin</option><option>Twi</option><option>Hausa</option></select>
<input type="file" id="fileInput" hidden onchange="handleFile()">
<button class="btn btn2" onclick="document.getElementById('fileInput').click()">📎</button>
<input id="q" placeholder="Ask anything or 'generate image of...'">
<button class="btn" onclick="sendText()">➤</button>
<button class="btn btn2" id="micBtn" onclick="toggleMic()">🎤</button>
</div>
<audio id="player" controls style="display:none;width:100%;margin-top:8px"></audio>
</div>
<script>
let chatHistory = []; let uploadedText = "";
let recorder,chunks=[],recording=false;
function addMsg(role, text, isHtml=false){
 let chat=document.getElementById('chat');
 let div=document.createElement('div'); div.className='msg '+role;
 if(!text ||!text.trim()){ text = "Sorry, try again."; }
 if(isHtml){ div.innerHTML = text; } else { div.innerHTML = text.replace(/\\n/g,'<br>'); }
 chat.appendChild(div); chat.scrollTop=chat.scrollHeight;
}
function isImageRequest(q){
 q=q.toLowerCase();
 return q.includes('generate image')||q.includes('create image')||q.includes('draw')||q.includes('picture of')||q.includes('photo of')||q.includes('image of')||q.includes('/image')||q.includes('generate picture');
}
async function sendText(){
 let input=document.getElementById('q'); let q=input.value.trim(); if(!q &&!uploadedText) return;
 if(q) addMsg('user', q);
 input.value='';
 if(isImageRequest(q)){
   let prompt = q.replace(/generate image of/gi,'').replace(/create image of/gi,'').replace(/generate image/gi,'').replace(/create image/gi,'').replace(/generate picture/gi,'').replace(/draw/gi,'').replace(/picture of/gi,'').replace(/image of/gi,'').replace(/photo of/gi,'').replace(/\\/image/gi,'').trim() || q;
   document.getElementById('status').innerText="🎨 MORR generating image (free model)...";
   let p = encodeURIComponent(prompt);
   // Primary = turbo (still free), Backup = Unsplash real photo (100% free unlimited, no payment ever)
   let imgUrl = `https://image.pollinations.ai/prompt/${p}?model=turbo&width=512&height=512&nologo=true&seed=${Date.now()}`;
   let backup1 = `https://source.unsplash.com/512x512/?${p}`;
   let backup2 = `https://loremflickr.com/512/512/${p}`;
   setTimeout(()=>{
     document.getElementById('status').innerText="";
     addMsg('ai', `🎨 Here is your image for: <b>${prompt}</b><br><img src="${imgUrl}" onerror="this.onerror=null; this.src='${backup1}'; this.onerror=function(){this.src='${backup2}'}" style="max-width:100%;border-radius:12px;margin-top:10px;border:1px solid #333"><br><a href="${imgUrl}" target="_blank" style="color:#FFD700">📥 Download</a>`, true);
   }, 500);
   return;
 }
 document.getElementById('status').innerText="MORR dey think via higher AI...";
 try{
  let res=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({question:q, file_context: uploadedText, language: document.getElementById('lang').value, history: chatHistory})});
  let data=await res.json();
  document.getElementById('status').innerText="";
  let answer = data.answer || "Sorry, try again.";
  if(data.image_url){
    addMsg('ai', answer + `<br><img src="${data.image_url}" onerror="this.src='https://source.unsplash.com/512x512/?${encodeURIComponent(q)}'" style="max-width:100%;border-radius:12px;margin-top:10px"><br><a href="${data.image_url}" target="_blank" style="color:#FFD700">📥 Download</a>`, true);
  } else if(data.file_url){
    addMsg('ai', answer + `<br><a href="${data.file_url}" target="_blank" style="color:#FFD700;font-weight:bold">📄 Download: ${data.file_name}</a>`, true);
  } else {
    addMsg('ai', answer, true);
  }
  chatHistory.push({role:'user',content:q},{role:'assistant',content:answer});
  if(data.audio_url){let p=document.getElementById('player');p.style.display='block';p.src=data.audio_url+"?t="+Date.now();}
 }catch(e){ document.getElementById('status').innerText=""; addMsg('ai', "Network error: "+e); }
 uploadedText=""; document.getElementById('fileInput').value="";
}
async function handleFile(){
 let file=document.getElementById('fileInput').files[0]; if(!file) return;
 document.getElementById('status').innerText="📄 "+file.name+" uploading...";
 let fd=new FormData(); fd.append('file',file);
 let res=await fetch('/upload',{method:'POST',body:fd}); let data=await res.json();
 uploadedText = data.text || "";
 document.getElementById('status').innerText="✅ "+file.name+" attached";
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
addMsg('ai','Akwaaba! I am MORR AI GH 🇬🇭<br>Ghana\\'s Smart Assistant for Studies, Business & Afro culture<br>I help with chat, images, files and voice — what would you like to do today?', true);
if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js');}
</script></body></html>"""

def build_prompt(lang, has_file=False):
    return f"""You are MORR AI GH. Ghana's Smart Assistant for Studies, Business & Afro culture. Date: May 13, 2026. Language: {lang}.
- You CAN generate images and files. NEVER say text-only. FORBIDDEN.
- Be helpful, concise.
File:{has_file}"""

@app.route("/")
def home(): return render_template_string(HTML)
@app.route("/manifest.json")
def manifest():
    return jsonify({"name":"MORR AI GH","short_name":"MORR GH","start_url":"/","display":"standalone","background_color":"#0a0a0a","theme_color":"#FFD700","icons":[{"src":"https://flagcdn.com/w192/gh.png","sizes":"192x192","type":"image/png"}]})
@app.route("/sw.js")
def sw(): return "self.addEventListener('fetch',e=>{});",200,{'Content-Type':'application/javascript'}
@app.route("/upload", methods=["POST"])
def upload():
    f=request.files.get('file')
    if not f: return jsonify({"text":""})
    name=f.filename.lower(); tmp=os.path.join(tempfile.gettempdir(), f.filename); f.save(tmp); text=""
    try:
        if name.endswith(('.png','.jpg','.jpeg','.webp')): text=f"[IMAGE: {f.filename}]"
        elif name.endswith('.pdf'):
            import PyPDF2; r=PyPDF2.PdfReader(tmp); text=" ".join([p.extract_text() or "" for p in r.pages[:10]])
        elif name.endswith(('.txt','.csv','.py','.js','.html','.json','.md')):
            with open(tmp,'r',errors='ignore') as file: text=file.read()[:8000]
        elif name.endswith('.docx'):
            import docx; doc=docx.Document(tmp); text=" ".join([p.text for p in doc.paragraphs])[:8000]
        else: text=f"[File {f.filename}]"
    except: text=f"[File {f.filename}]"
    return jsonify({"text":text[:8000]})
@app.route("/ask", methods=["POST"])
def ask():
    d=request.get_json(); q_raw=d.get("question",""); q=q_raw.lower(); lang=d.get("language","English"); file_ctx=d.get("file_context",""); history=d.get("history",[])[:10]
    if any(k in q for k in ["generate image","create image","draw","picture of","image of","photo of","/image","generate picture"]):
        prompt=q_raw
        for k in ["generate image of","create image of","generate image","create image","generate picture","create picture","draw","picture of","image of","photo of","/image"]: prompt=prompt.lower().replace(k,"")
        prompt=prompt.strip() or "beautiful Ghanaian scene"; clean=urllib.parse.quote(prompt)
        img_url=f"https://image.pollinations.ai/prompt/{clean}?model=turbo&width=512&height=512&nologo=true&seed={abs(hash(prompt))%1000000}"
        return jsonify({"answer":f"🎨 Here is your image for: <b>{prompt}</b>","image_url":img_url})
    if any(k in q for k in ["create pdf","generate pdf","create document","create file","generate file","create docx","create doc"]):
        try:
            c_path=os.path.join(tempfile.gettempdir(),"morr_doc.pdf")
            try:
                from reportlab.pdfgen import canvas; c=canvas.Canvas(c_path); c.setFont("Helvetica-Bold",16); c.drawString(80,750,"MORR AI GH - Document"); c.setFont("Helvetica",11); c.drawString(80,720,f"Topic: {q_raw[:120]}"); c.drawString(80,700,"Generated by MORR AI GH"); y=670; words=q_raw.split()
                for i in range(0,min(len(words),200),12): c.drawString(80,y," ".join(words[i:i+12])); y-=18
                if y<50: break
                c.save()
            except: open(c_path,"w").write(f"MORR AI GH Document\n{q_raw}")
            return jsonify({"answer":f"📄 Created: {q_raw}","file_url":"/download/morr_doc.pdf","file_name":"morr_doc.pdf"})
        except Exception as e: return jsonify({"answer":f"File error: {e}"})
    messages=[{"role":"system","content":build_prompt(lang,bool(file_ctx))}]
    for h in history: messages.append(h)
    messages.append({"role":"user","content":(f"FILE:{file_ctx}\nQ:{q_raw}" if file_ctx else q_raw)})
    ans=None; last_err=""
    for model_name in ["llama-3.3-70b-versatile","llama-3.1-8b-instant","gemma2-9b-it"]:
        try:
            resp=client.chat.completions.create(model=model_name,messages=messages,temperature=0.3,max_tokens=900)
            ans=resp.choices[0].message.content
            if ans and ans.strip(): break
        except Exception as e: last_err=str(e); continue
    if not ans: ans=f"Connection issue: {last_err}. Try again."
    try:
        fn=f"morr_{lang}.mp3"; fp=os.path.join(os.path.dirname(__file__),fn)
        if HAS_GTTS: gTTS(text=ans[:300],lang='en').save(fp); audio=f"/audio/{fn}"
        else: audio=None
    except: audio=None
    return jsonify({"answer":ans,"audio_url":audio})
@app.route("/voice", methods=["POST"])
def voice():
    f=request.files.get("audio"); tmp=os.path.join(tempfile.gettempdir(),"in.webm")
    if f: f.save(tmp); txt=""
    try:
        with open(tmp,"rb") as af: txt=client.audio.transcriptions.create(model="whisper-large-v3",file=af).text
    except: txt=""
    return jsonify({"text":txt or "Hi"})
@app.route("/download/<filename>")
def download_file(filename):
    p=os.path.join(tempfile.gettempdir(),filename)
    if os.path.exists(p): return send_file(p,as_attachment=True)
    return "not found",404
@app.route("/audio/<filename>")
def serve_audio(filename):
    p=os.path.join(os.path.dirname(__file__),filename)
    if os.path.exists(p): return send_file(p,mimetype="audio/mpeg")
    return "not found",404
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
