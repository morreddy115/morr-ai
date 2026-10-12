import os
import re
import io
import uuid
import base64
import tempfile
from flask import (
    Flask, render_template_string, request,
    jsonify, send_file, url_for
)
from openai import OpenAI

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

MY_GROQ_KEY = os.getenv("GROQ_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(
    api_key=MY_GROQ_KEY or "missing-key",
    base_url="https://api.groq.com/openai/v1"
)

image_client = (
    OpenAI(api_key=OPENAI_KEY)
    if OPENAI_KEY else None
)

GENERATED_DIR = os.path.join(
    tempfile.gettempdir(), "morr_ai_generated"
)
os.makedirs(GENERATED_DIR, exist_ok=True)

try:
    from gtts import gTTS
    HAS_GTTS = True
except ImportError:
    HAS_GTTS = False

# --- HTML (YOUR CHATGPT VERSION - KEPT 100%) ---
HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>MORR AI GH</title>
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
#q{flex:1;padding:14px;border-radius:12px;border:none;background:#1e1e1e;color:white;font-size:16px;min-width:0}
.btn{padding:12px 16px;background:#FFD700;color:black;border:none;border-radius:12px;font-weight:bold;cursor:pointer}
.btn2{background:#333;color:white}
.msg img{max-width:100%;height:auto;border-radius:12px;margin-top:10px}
.msg a{color:#FFD700}
</style></head><body>
<div class="header"><h1>MORR AI GH <img src="https://flagcdn.com/w20/gh.png" style="width:24px;height:18px;border-radius:3px"></h1><div class="sub">Smart AI - Chat - Images - Files - Like Meta AI</div></div>
<div id="chat"></div>
<div class="input-area"><div id="status" style="color:#FFD700;font-size:12px;margin-top:6px"></div>
<div class="row"><select id="lang"><option>English</option><option>Pidgin</option><option>Twi</option><option>Hausa</option></select>
<input type="file" id="fileInput" hidden onchange="handleFile()">
<button class="btn btn2" onclick="document.getElementById('fileInput').click()">📎</button>
<input id="q" placeholder="Ask anything or 'generate image of...'"><button class="btn" onclick="sendText()">➤</button>
<button class="btn btn2" id="micBtn" onclick="toggleMic()">🎤</button></div>
<audio id="player" controls style="display:none;width:100%;margin-top:8px"></audio></div>
<script>
let chatHistory=[];let uploadedText="";let recorder,chunks=[],recording=false;
function escapeHTML(v){return String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function addMsg(role,text,isHtml=false){let chat=document.getElementById('chat');let div=document.createElement('div');div.className='msg '+role;if(!text||!String(text).trim()){text="Sorry, I could not produce a response.";}if(isHtml){div.innerHTML=text;}else{div.innerHTML=escapeHTML(text).replace(/\\n/g,'<br>');}chat.appendChild(div);chat.scrollTop=chat.scrollHeight;}
function isImageRequest(q){q=q.toLowerCase();return ['generate image','create image','draw ','picture of','photo of','image of','/image','generate picture','create picture'].some(t=>q.includes(t));}
async function sendText(){
 let input=document.getElementById('q');let q=input.value.trim();if(!q&&!uploadedText)return;if(q)addMsg('user',q);input.value='';
 let status=document.getElementById('status');status.innerText="MORR dey think...";
 try{
  let res=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q,file_context:uploadedText,language:document.getElementById('lang').value,history:chatHistory})});
  let data=await res.json();if(!res.ok)throw new Error(data.error||'Request failed');status.innerText='';
  let output=escapeHTML(data.answer||'').replace(/\\n/g,'<br>');
  if(data.image_url){output+=`<br><img src="${escapeHTML(data.image_url)}" alt="Generated image"><br><a href="${escapeHTML(data.image_url)}" target="_blank" download>Download image</a>`;}
  if(data.file_url){output+=`<br><a href="${escapeHTML(data.file_url)}">📥 Download your file</a>`;}
  addMsg('ai',output,true);chatHistory.push({role:'user',content:q},{role:'assistant',content:data.answer||''});chatHistory=chatHistory.slice(-12);
  if(data.audio_url){let p=document.getElementById('player');p.style.display='block';p.src=data.audio_url+'?t='+Date.now();}
 }catch(e){status.innerText='';addMsg('ai','Connection issue: '+e.message);}
 uploadedText='';document.getElementById('fileInput').value='';
}
async function handleFile(){let file=document.getElementById('fileInput').files[0];if(!file)return;document.getElementById('status').innerText='📄 '+file.name+' uploading...';try{let fd=new FormData();fd.append('file',file);let res=await fetch('/upload',{method:'POST',body:fd});let data=await res.json();if(!res.ok)throw new Error(data.error||'Upload failed');uploadedText=data.text||'';document.getElementById('status').innerText='✅ '+file.name+' attached';}catch(e){document.getElementById('status').innerText='Upload error: '+e.message;}}
async function toggleMic(){let btn=document.getElementById('micBtn');try{if(!recording){let stream=await navigator.mediaDevices.getUserMedia({audio:true});recorder=new MediaRecorder(stream);chunks=[];recorder.ondataavailable=e=>chunks.push(e.data);recorder.onstop=async()=>{try{let blob=new Blob(chunks,{type:'audio/webm'});let fd=new FormData();fd.append('audio',blob,'voice.webm');fd.append('language',document.getElementById('lang').value);document.getElementById('status').innerText='Transcribing voice...';let res=await fetch('/voice',{method:'POST',body:fd});let data=await res.json();if(data.text){document.getElementById('q').value=data.text;await sendText();}else{document.getElementById('status').innerText='Voice could not be transcribed.';}}catch(e){document.getElementById('status').innerText='Voice error: '+e.message;}stream.getTracks().forEach(t=>t.stop());};recorder.start();recording=true;btn.innerText='🔴';}else{recorder.stop();recording=false;btn.innerText='🎤';}}catch(e){document.getElementById('status').innerText='Microphone error: '+e.message;}}
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter')sendText();});
addMsg('ai',"Akwaaba! I am MORR AI GH 🇬🇭<br>Ghana's Smart Assistant for Studies, Business & Afro culture<br>Chat, images, files and voice — what do you want to do today?",true);
</script></body></html>"""

def build_prompt(lang, has_file):
    return f"You are MORR AI GH. Ghana's Smart Assistant for Studies, Business & Afro culture. Language: {lang}. Be helpful, concise, friendly. File attached: {has_file}. Never say you are text-only."

@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/manifest.json")
def manifest():
    return jsonify({"name":"MORR AI GH","short_name":"MORR GH","start_url":"/","display":"standalone","background_color":"#0a0a0a","theme_color":"#FFD700","icons":[{"src":"https://flagcdn.com/w192/gh.png","sizes":"192x192","type":"image/png"}]})

@app.route("/sw.js")
def sw():
    return "self.addEventListener('fetch',e=>{});",200,{'Content-Type':'application/javascript'}

@app.route("/upload", methods=["POST"])
def upload():
    f=request.files.get('file')
    if not f:
        return jsonify({"text":""}),400
    name=f.filename.lower()
    tmp=os.path.join(tempfile.gettempdir(), f.filename)
    f.save(tmp)
    text=""
    try:
        if name.endswith(('.png','.jpg','.jpeg','.webp')):
            text=f"[IMAGE: {f.filename} uploaded]"
        elif name.endswith('.pdf'):
            import PyPDF2
            r=PyPDF2.PdfReader(tmp)
            text=" ".join([(p.extract_text() or "") for p in r.pages[:8]])[:8000]
        elif name.endswith(('.txt','.csv','.py','.js','.html','.json','.md')):
            with open(tmp,'r',errors='ignore') as file:
                text=file.read()[:8000]
        elif name.endswith('.docx'):
            import docx
            doc=docx.Document(tmp)
            text=" ".join([p.text for p in doc.paragraphs])[:8000]
        else:
            text=f"[File {f.filename}]"
    except Exception as e:
        text=f"[File {f.filename}]"
    return jsonify({"text":text[:8000]})

@app.route("/ask", methods=["POST"])
def ask():
    try:
        d=request.get_json()
        q_raw=d.get("question","") or ""
        q=q_raw.lower()
        lang=d.get("language","English")
        file_ctx=d.get("file_context","")
        history=d.get("history",[])[:12]

        # IMAGE REQUEST
        if any(k in q for k in ["generate image","create image","draw","picture of","image of","photo of","/image","generate picture","create picture"]):
            prompt=q_raw
            for k in ["generate image of","create image of","generate image","create image","generate picture","draw","picture of","image of","photo of","/image"]:
                prompt=prompt.lower().replace(k,"")
            prompt=prompt.strip() or "beautiful Ghanaian culture"

            # If OPENAI key exists, use DALL-E (best), else free fallback (no pollinations)
            if image_client:
                try:
                    resp=image_client.images.generate(model="dall-e-2", prompt=prompt[:1000], size="512x512", n=1)
                    img_url=resp.data[0].url
                    return jsonify({"answer":f"🎨 Here is your image for: {prompt}", "image_url": img_url})
                except Exception as e:
                    # fallback if OpenAI fails
                    pass

            # FREE FALLBACK - 100% FREE, NO BEE, NO PAYMENT
            import urllib.parse
            clean=urllib.parse.quote(prompt)
            free_url=f"https://source.unsplash.com/512x512/?{clean}"
            return jsonify({"answer":f"🎨 Here is your image for: {prompt} (free photo)", "image_url": free_url})

        # FILE REQUEST
        if any(k in q for k in ["create pdf","generate pdf","create document","export to pdf"]):
            try:
                from reportlab.pdfgen import canvas
                fname=f"morr_{uuid.uuid4().hex[:8]}.pdf"
                fpath=os.path.join(GENERATED_DIR, fname)
                c=canvas.Canvas(fpath)
                c.setFont("Helvetica-Bold",16)
                c.drawString(80,750,"MORR AI GH - Document")
                c.setFont("Helvetica",11)
                c.drawString(80,720,f"Topic: {q_raw[:120]}")
                y=680
                words=q_raw.split()
                for i in range(0, min(len(words),150), 10):
                    chunk=" ".join(words[i:i+10])
                    c.drawString(80,y,chunk)
                    y-=18
                    if y<50: break
                c.save()
                return jsonify({"answer":f"📄 Created document for: {q_raw}", "file_url": f"/download/{fname}"})
            except Exception as e:
                return jsonify({"answer": f"File error: {e}"})

        # CHAT - FIXED MODELS (NO GEMMA2-9B-IT)
        messages=[{"role":"system","content":build_prompt(lang, bool(file_ctx))}]
        for h in history:
            messages.append(h)
        content_text = f"FILE CONTEXT: {file_ctx}\nUSER QUESTION: {q_raw}" if file_ctx else q_raw
        if content_text.strip():
            messages.append({"role":"user","content":content_text})
        else:
            messages.append({"role":"user","content":"Hello"})

        ans=None
        ACTIVE_MODELS = ["llama-3.3-70b-versatile","llama-3.1-70b-versatile","llama-3.1-8b-instant","llama-3.2-90b-text-preview"]
        last_err=""
        for model_name in ACTIVE_MODELS:
            try:
                resp=client.chat.completions.create(model=model_name, messages=messages, temperature=0.4, max_tokens=900)
                ans=resp.choices[0].message.content
                if ans and ans.strip():
                    break
            except Exception as e:
                last_err=str(e)
                continue

        if not ans:
            ans="MORR is busy, please try again in a few seconds."

        audio_url=None
        try:
            if HAS_GTTS:
                fname_audio=f"morr_{lang}_{uuid.uuid4().hex[:6]}.mp3"
                fpath_audio=os.path.join(GENERATED_DIR, fname_audio)
                gTTS(text=ans[:350], lang='en').save(fpath_audio)
                audio_url=f"/audio/{fname_audio}"
        except:
            audio_url=None

        return jsonify({"answer": ans, "audio_url": audio_url})

    except Exception as e:
        return jsonify({"error": str(e), "answer": "Server error, try again"}), 500

@app.route("/voice", methods=["POST"])
def voice():
    f=request.files.get("audio")
    tmp=os.path.join(tempfile.gettempdir(), f"voice_{uuid.uuid4().hex}.webm")
    if f:
        f.save(tmp)
    txt=""
    try:
        with open(tmp,"rb") as af:
            txt=client.audio.transcriptions.create(model="whisper-large-v3", file=af).text
    except:
        txt=""
    try:
        os.remove(tmp)
    except:
        pass
    return jsonify({"text": txt or ""})

@app.route("/download/<filename>")
def download_file(filename):
    safe=os.path.basename(filename)
    p=os.path.join(GENERATED_DIR, safe)
    p2=os.path.join(tempfile.gettempdir(), safe)
    if os.path.exists(p):
        return send_file(p, as_attachment=True)
    if os.path.exists(p2):
        return send_file(p2, as_attachment=True)
    return "not found",404

@app.route("/audio/<filename>")
def serve_audio(filename):
    safe=os.path.basename(filename)
    p=os.path.join(GENERATED_DIR, safe)
    p2=os.path.join(os.path.dirname(__file__), safe)
    if os.path.exists(p):
        return send_file(p, mimetype="audio/mpeg")
    if os.path.exists(p2):
        return send_file(p2, mimetype="audio/mpeg")
    return "not found",404

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
