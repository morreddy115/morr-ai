import os
import time
import tempfile
import uuid
import urllib.parse
from flask import Flask, render_template_string, request, jsonify, send_file
from google import genai

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

# Updated to a stable, current model version
MODEL_NAME = "gemini-3.8-flash"

try:
    from gtts import gTTS
    HAS_GTTS = True
except:
    HAS_GTTS = False

GENERATED_DIR = os.path.join(tempfile.gettempdir(), "morr_ai_generated")
os.makedirs(GENERATED_DIR, exist_ok=True)

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
.msg img{max-width:100%;border-radius:12px;margin-top:10px}
.msg a{color:#FFD700}
</style></head><body>
<div class="header"><h1>MORR AI GH <img src="https://flagcdn.com/w20/gh.png" style="width:24px;height:18px;border-radius:3px"></h1><div class="sub">Smart AI - Chat - Images - Files - Powered by Gemini</div></div>
<div id="chat"></div>
<div class="input-area"><div id="status" style="color:#FFD700;font-size:12px"></div>
<div class="row"><select id="lang"><option>English</option><option>Pidgin</option><option>Twi</option><option>Hausa</option></select>
<input type="file" id="fileInput" hidden onchange="handleFile()"><button class="btn btn2" onclick="document.getElementById('fileInput').click()">📎</button>
<input id="q" placeholder="Ask anything or 'generate image of...'"><button class="btn" onclick="sendText()">➤</button>
<button class="btn btn2" id="micBtn" onclick="toggleMic()">🎤</button></div>
<audio id="player" controls style="display:none;width:100%;margin-top:8px"></audio></div>
<script>
let chatHistory=[];let uploadedText="";let recorder,chunks=[],recording=false;
function addMsg(r,t,h=false){let c=document.getElementById('chat');let d=document.createElement('div');d.className='msg '+r;if(!t)t="...";if(h)d.innerHTML=t;else d.textContent=t;c.appendChild(d);c.scrollTop=c.scrollHeight;}
async function sendText(){
 let i=document.getElementById('q');let q=i.value.trim();if(!q&&!uploadedText)return;if(q)addMsg('user',q);i.value='';document.getElementById('status').innerText="MORR dey think...";
 try{
  let res=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q,file_context:uploadedText,language:document.getElementById('lang').value,history:chatHistory})});
  let data=await res.json();document.getElementById('status').innerText='';
  let out=data.answer||"No answer"; if(data.image_url) out+=`<br><img src="${data.image_url}"><br><a href="${data.image_url}" target="_blank">Download image</a>`; if(data.file_url) out+=`<br><a href="${data.file_url}">📥 Download file</a>`;
  addMsg('ai',out,true); chatHistory.push({role:'user',content:q},{role:'assistant',content:data.answer}); chatHistory=chatHistory.slice(-12);
  if(data.audio_url){let p=document.getElementById('player');p.style.display='block';p.src=data.audio_url+"?t="+Date.now();}
 }catch(e){document.getElementById('status').innerText=''; addMsg('ai','Error: '+e.message);}
 uploadedText=''; document.getElementById('fileInput').value='';
}
async function handleFile(){let f=document.getElementById('fileInput').files[0];if(!f)return;document.getElementById('status').innerText='📄 '+f.name+' uploading...'; let fd=new FormData();fd.append('file',f);let res=await fetch('/upload',{method:'POST',body:fd});let data=await res.json();uploadedText=data.text||'';document.getElementById('status').innerText='✅ '+f.name+' attached';}
async function toggleMic(){
 let btn=document.getElementById('micBtn');
 try{
  if(!recording){let s=await navigator.mediaDevices.getUserMedia({audio:true}); recorder=new MediaRecorder(s); chunks=[]; recorder.ondataavailable=e=>chunks.push(e.data);
   recorder.onstop=async()=>{let blob=new Blob(chunks,{type:'audio/webm'});let fd=new FormData();fd.append('audio',blob,'voice.webm');fd.append('language',document.getElementById('lang').value);document.getElementById('status').innerText='Transcribing...';let res=await fetch('/voice',{method:'POST',body:fd});let d=await res.json();if(d.text){document.getElementById('q').value=d.text;sendText();}else{document.getElementById('status').innerText='Could not transcribe';} s.getTracks().forEach(t=>t.stop());}; recorder.start(); recording=true; btn.innerText='🔴';
  }else{recorder.stop(); recording=false; btn.innerText='🎤';}
 }catch(e){document.getElementById('status').innerText='Mic error: '+e.message;}
}
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter')sendText();});
addMsg('ai',"Akwaaba! I am MORR AI GH 🇬🇭<br>Now powered by Gemini — faster & stable<br>Chat, images, files and voice — what do you want to do today?",true);
</script></body></html>"""

@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/upload", methods=["POST"])
def upload():
    f=request.files.get('file')
    if not f: return jsonify({"text":""}),400
    name=f.filename.lower()
    tmp=os.path.join(tempfile.gettempdir(), f.filename)
    f.save(tmp)
    text=""
    try:
        if name.endswith('.pdf'):
            import PyPDF2
            r=PyPDF2.PdfReader(tmp)
            text=" ".join([(p.extract_text() or "") for p in r.pages[:8]])[:8000]
        elif name.endswith(('.txt','.csv','.py','.js','.html','.json','.md')):
            with open(tmp,'r',errors='ignore') as file: text=file.read()[:8000]
        elif name.endswith('.docx'):
            import docx
            doc=docx.Document(tmp)
            text=" ".join([p.text for p in doc.paragraphs])[:8000]
        else:
            text=f"[File {f.filename} uploaded]"
    except:
        text=f"[File {f.filename}]"
    return jsonify({"text":text})

@app.route("/ask", methods=["POST"])
def ask():
    try:
        d=request.get_json()
        q_raw=d.get("question","") or ""
        q_low=q_raw.lower()
        lang=d.get("language","English")
        file_ctx=d.get("file_context","")
        history=d.get("history",[])[:10]

        if not GEMINI_KEY or not client:
            return jsonify({"answer":"GEMINI_API_KEY not set in Render. Go to Render → Environment → Add GEMINI_API_KEY"})

        if any(k in q_low for k in ["generate image","create image","draw","picture of","image of","photo of","/image"]):
            prompt=q_raw
            for k in ["generate image of","create image of","generate image","create image","draw","picture of","image of","photo of","/image"]:
                prompt=prompt.lower().replace(k,"")
            prompt=prompt.strip() or "beautiful Ghanaian culture"
            clean=urllib.parse.quote(prompt)
            url=f"https://source.unsplash.com/800x600/?{clean}"
            return jsonify({"answer": f"🎨 Here is your image for: {prompt}", "image_url": url})

        if any(k in q_low for k in ["create pdf","generate pdf","create document","export to pdf"]):
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
                for line in q_raw.split(".")[:20]:
                    c.drawString(80,y,line[:90])
                    y-=18
                    if y<50: break
                c.save()
                return jsonify({"answer":f"📄 Created PDF for: {q_raw}", "file_url": f"/download/{fname}"})
            except Exception as e:
                return jsonify({"answer": f"PDF error: {e}"})

        system_prompt = f"You are MORR AI GH, Ghana's Smart Assistant for Studies, Business & Afro culture. Language: {lang}. Be helpful, friendly, concise. If file context provided, use it. File context present: {bool(file_ctx)}"

        full_prompt = system_prompt + "\n\n"
        if file_ctx:
            full_prompt += f"FILE: {file_ctx[:4000]}\n\n"
        for h in history[-6:]:
            if h.get('role')=='user':
                full_prompt += f"User: {h.get('content')}\n"
            else:
                full_prompt += f"Assistant: {h.get('content')}\n"
        full_prompt += f"User: {q_raw}\nAssistant:"

        # Automatic retry mechanism for temporary high-demand 503 errors
        resp = None
        retries = 3
        for attempt in range(retries):
            try:
                resp = client.models.generate_content(model=MODEL_NAME, contents=full_prompt)
                break
            except Exception as api_err:
                if "503" in str(api_err) and attempt < retries - 1:
                    time.sleep(2)  # Wait 2 seconds before retrying
                    continue
                raise api_err

        ans = resp.text if resp and resp.text else "I could not generate a response, try again."

        audio_url=None
        try:
            if HAS_GTTS:
                fname_a=f"morr_{uuid.uuid4().hex[:6]}.mp3"
                fpath_a=os.path.join(GENERATED_DIR, fname_a)
                gTTS(text=ans[:350], lang='en').save(fpath_a)
                audio_url=f"/audio/{fname_a}"
        except:
            pass

        return jsonify({"answer": ans, "audio_url": audio_url})

    except Exception as e:
        return jsonify({"answer": f"Server error: {str(e)[:500]}"}), 500

@app.route("/voice", methods=["POST"])
def voice():
    f=request.files.get("audio")
    if not f:
        return jsonify({"text":""})
    tmp=os.path.join(tempfile.gettempdir(), f"voice_{uuid.uuid4().hex}.webm")
    f.save(tmp)
    txt=""
    try:
        if client:
            uploaded = client.files.upload(file=tmp)
            resp = client.models.generate_content(model=MODEL_NAME, contents=["Transcribe this audio exactly, only return transcription:", uploaded])
            txt = resp.text or ""
    except Exception as e:
        txt=""
    try: os.remove(tmp)
    except: pass
    return jsonify({"text": txt.strip()})

@app.route("/download/<filename>")
def download_file(filename):
    p=os.path.join(GENERATED_DIR, filename)
    if os.path.exists(p):
        return send_file(p, as_attachment=True)
    return "not found",404

@app.route("/audio/<filename>")
def serve_audio(filename):
    p=os.path.join(GENERATED_DIR, filename)
    if os.path.exists(p):
        return send_file(p, mimetype="audio/mpeg")
    return "not found",404

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
