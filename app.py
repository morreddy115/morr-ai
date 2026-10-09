import os, tempfile, base64, mimetypes
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
<title>MORR AI GH - Smart AI</title>
<style>
body{background:#0a0a0a;color:white;font-family:system-ui;margin:0;padding:0;display:flex;flex-direction:column;height:100vh}
.header{padding:12px;text-align:center;border-bottom:1px solid #222}
h1{color:#FFD700;font-size:28px;margin:0}.sub{color:#aaa;font-size:13px}
#chat{flex:1;overflow-y:auto;padding:16px;max-width:850px;width:100%;margin:0 auto;box-sizing:border-box}
.msg{padding:14px 18px;border-radius:18px;margin:8px 0;max-width:85%;line-height:1.6;white-space:pre-wrap;word-wrap:break-word}
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
let chatHistory = []; let uploadedText = ""; let uploadedImage = null;
let recorder,chunks=[],recording=false;

function addMsg(role, text, isImage=false){
 let chat=document.getElementById('chat');
 let div=document.createElement('div'); div.className='msg '+role;
 if(isImage){ div.innerHTML = text + `<br><img src="${isImage}" />`; } else { div.innerText = text; }
 if(role==='ai' &&!isImage) div.innerHTML = text.replace(/\\n/g,'<br>'); // allow html for files
 chat.appendChild(div); chat.scrollTop=chat.scrollHeight;
}

async function sendText(){
 let input=document.getElementById('q'); let q=input.value.trim(); if(!q &&!uploadedText) return;
 if(q) addMsg('user', q);
 input.value=''; // <-- THIS FIXES YOUR STUCK INPUT PROBLEM!
 document.getElementById('status').innerText="MORR dey think...";

 // IMAGE GENERATION
 if(q.toLowerCase().startsWith('generate image') || q.toLowerCase().startsWith('create image') || q.toLowerCase().includes('/image')){
   let prompt = q.replace(/generate image of/i,'').replace(/create image of/i,'').replace('/image','').trim();
   let imgUrl = `https://image.pollinations.ai/prompt/${encodeURIComponent(prompt)}?width=1024&height=1024&nologo=true&seed=${Date.now()}`;
   document.getElementById('status').innerText="";
   addMsg('ai', `🎨 Generated: ${prompt}`, imgUrl);
   chatHistory.push({role:'user',content:q},{role:'assistant',content:`Generated image: ${prompt}`});
   clearFile(); return;
 }

 // NORMAL CHAT + FILE
 try{
  let res=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({question:q, file_context: uploadedText, language: document.getElementById('lang').value, history: chatHistory})});
  let data=await res.json();
  document.getElementById('status').innerText="";
  addMsg('ai', data.answer);
  chatHistory.push({role:'user',content:q},{role:'assistant',content:data.answer});
  if(data.audio_url){let p=document.getElementById('player');p.style.display='block';p.src=data.audio_url+"?t="+Date.now();}
  if(data.download_url){ addMsg('ai', `📄 File ready: <a href='${data.download_url}' target='_blank' style='color:#FFD700'>Download ${data.download_name}</a>`); }
 }catch(e){ document.getElementById('status').innerText="Error, try again"; }
 clearFile();
}

function clearFile(){ uploadedText=""; uploadedImage=null; document.getElementById('fileName').innerText=""; document.getElementById('fileInput').value=""; }

async function handleFile(){
 let file=document.getElementById('fileInput').files[0]; if(!file) return;
 document.getElementById('fileName').innerText="📄 "+file.name+" uploading...";
 let fd=new FormData(); fd.append('file',file);
 let res=await fetch('/upload',{method:'POST',body:fd}); let data=await res.json();
 uploadedText = data.text || "";
 document.getElementById('fileName').innerText="✅ "+file.name+" attached - now ask about it";
 if(data.type==='image'){ uploadedImage=data.text; }
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
addMsg('ai','Akwaaba! I am MORR AI GH 🇬🇭\\nI can now:\\n• Chat like ChatGPT\\n• Generate images (say: generate image of a Ghanaian astronaut)\\n• Read your uploaded files & pictures\\n• Create files for you\\nWhat should we do today?');
</script></body></html>"""

def build_prompt(lang, has_file=False):
    extra = " The user also uploaded a file. Read and use its content to answer." if has_file else ""
    return f"""You are MORR AI GH, a powerful general AI assistant from Ghana, like Meta AI / ChatGPT.
You can chat, explain, code, create essays, solve math, analyze files, and generate files.
If user asks to create a file (PDF, DOCX, TXT, HTML), say you are creating it and put the content in a code block marked as FILE_CONTENT.
Answer in {lang}. Be friendly, smart, step-by-step. Under 400 words unless file content.{extra} 🇬🇭"""

@app.route("/")
def home(): return render_template_string(HTML)

@app.route("/upload", methods=["POST"])
def upload():
    f=request.files.get('file')
    if not f: return jsonify({"text":""})
    name=f.filename.lower()
    # Save temp
    tmp=os.path.join(tempfile.gettempdir(), f.filename)
    f.save(tmp)
    text=""
    try:
        if name.endswith(('.png','.jpg','.jpeg','.webp')):
            # For images, we will use vision model later, for now just note it
            with open(tmp,"rb") as img:
                b64=base64.b64encode(img.read()).decode()
            text=f"[IMAGE UPLOADED: {f.filename}. User wants you to describe/analyze this image.]"
            return jsonify({"text":text, "type":"image", "b64":b64})
        elif name.endswith('.pdf'):
            try:
                import PyPDF2
                reader=PyPDF2.PdfReader(tmp)
                text="\\n".join([p.extract_text() for p in reader.pages[:10]])
            except:
                text="[PDF uploaded but could not extract text. Ask user what to do.]"
        elif name.endswith(('.txt','.csv','.py','.js','.html','.json','.md')):
            with open(tmp,'r',errors='ignore') as file:
                text=file.read()[:8000]
        elif name.endswith(('.docx')):
            try:
                import docx
                doc=docx.Document(tmp)
                text="\\n".join([p.text for p in doc.paragraphs])[:8000]
            except:
                text="[DOCX uploaded]"
        else:
            text=f"[File uploaded: {f.filename}]"
    except Exception as e:
        text=f"[File uploaded: {f.filename}, error reading: {e}]"
    return jsonify({"text":text[:8000], "type":"text"})

@app.route("/ask", methods=["POST"])
def ask():
    d=request.get_json()
    q=d.get("question","")
    lang=d.get("language","English")
    file_ctx=d.get("file_context","")
    history=d.get("history",[])[:10] # last 10 messages for context

    full_q = q
    if file_ctx:
        full_q = f"FILE CONTENT:\\n{file_ctx}\\n\\nUSER QUESTION: {q}"

    messages=[{"role":"system","content":build_prompt(lang, bool(file_ctx))}]
    for h in history:
        messages.append(h)
    messages.append({"role":"user","content":full_q})

    ans="Error"
    download_url=None
    download_name=None
    try:
        # Use vision model if image was uploaded
        model = "openai/gpt-oss-20b"
        if "IMAGE UPLOADED" in file_ctx:
            model = "meta-llama/llama-4-scout-17b-16e-instruct" # Groq vision model
        resp=client.chat.completions.create(model=model, messages=messages, temperature=0.7, max_tokens=1500)
        ans=resp.choices[0].message.content

        # FILE GENERATION DETECTION
        if "FILE_CONTENT" in ans or "create file" in q.lower() or "generate pdf" in q.lower() or "generate doc" in q.lower():
            # Try to extract file to create
            try:
                # Create a simple txt file from answer if requested
                if "pdf" in q.lower() or "document" in q.lower():
                    fn=f"morr_generated_{int(os.times()[4])}.txt"
                    fp=os.path.join(tempfile.gettempdir(), fn)
                    with open(fp,'w',encoding='utf-8') as out:
                        out.write(ans)
                    download_url=f"/download/{fn}"
                    download_name=fn
            except: pass

    except Exception as e:
        ans=f"Error: {e}. Check GROQ_API_KEY on Render."

    try:
        fn=f"morr_{lang}.mp3"; fp=os.path.join(os.path.dirname(__file__), fn)
        if HAS_GTTS: gTTS(text=ans[:350], lang='en').save(fp); audio=f"/audio/{fn}"
        else: audio=None
    except: audio=None

    return jsonify({"answer":ans,"audio_url":audio,"download_url":download_url,"download_name":download_name})

@app.route("/download/<filename>")
def download_file(filename):
    p=os.path.join(tempfile.gettempdir(), filename)
    if os.path.exists(p): return send_file(p, as_attachment=True)
    return "not found",404

@app.route("/voice", methods=["POST"])
def voice():
    lang=request.form.get("language","English"); f=request.files.get("audio")
    tmp=os.path.join(tempfile.gettempdir(),"in.webm"); f.save(tmp); txt=""
    try:
        with open(tmp,"rb") as af: txt=client.audio.transcriptions.create(model="whisper-large-v3", file=af).text
    except: txt=""
    if not txt: txt="Hi"
    return jsonify({"text":txt,"language":lang})

@app.route("/audio/<filename>")
def serve_audio(filename):
    p=os.path.join(os.path.dirname(__file__), filename)
    if os.path.exists(p): return send_file(p, mimetype="audio/mpeg")
    return "not found",404

if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
