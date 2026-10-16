import os
import tempfile
import uuid
import urllib.parse
import requests
from flask import Flask, render_template_string, request, jsonify, send_file
from google import genai
from google.genai import types

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None
MODEL_NAME = "gemini-2.5-flash"

try:
    from gtts import gTTS
    HAS_GTTS = True
except:
    HAS_GTTS = False

GENERATED_DIR = os.path.join(tempfile.gettempdir(), "morr_ai_generated")
os.makedirs(GENERATED_DIR, exist_ok=True)

# ===== SMART MEMORY RESOLVER =====
def resolve_context(query, history):
    q_low = query.lower().strip()
    if any(p in q_low for p in ["his wife", "her husband", "his husband", "who is his", "who is her", "his children", "her children", "his wife name", "picture of him", "image of him", "photo of him", "him swearing"]):
        for h in reversed(history):
            c = h.get('content','')
            if not c: continue
            if 'John Dramani Mahama' in c or 'John Mahama' in c:
                if 'wife' in q_low: return "Lordina Mahama wife of John Mahama"
                if 'children' in q_low: return "John Mahama children"
                return "John Dramani Mahama"
            if 'Claudia Sheinbaum' in c:
                return "Claudia Sheinbaum"
            if 'Kwame Nkrumah' in c:
                return "Kwame Nkrumah"
            if 'President of Ghana' in c:
                return "John Dramani Mahama President of Ghana"
        if q_low in ["who is his wife", "who is her husband"]:
            return "John Dramani Mahama wife Lordina Mahama"
    return query

# ===== REAL WIKIPEDIA SEARCH + REAL IMAGE =====
def get_wikipedia_real(query):
    clean_q = query.strip()
    if not clean_q:
        return {"text":"Please ask a question.", "image":None, "url":None, "title":None}
    headers = {"User-Agent": "MORR AI GH/1.0 (Educational Bot; Ghana)"}
    result = {"text":"", "image":None, "url":None, "title":None}
    try:
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(clean_q)}&format=json&srlimit=1"
        r = requests.get(search_url, timeout=12, headers=headers)
        if r.status_code == 200:
            data = r.json()
            hits = data.get("query", {}).get("search", [])
            if hits:
                title = hits[0].get("title", "")
                result["title"] = title
                summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
                r2 = requests.get(summary_url, timeout=12, headers=headers)
                if r2.status_code == 200:
                    j = r2.json()
                    result["text"] = j.get("extract", "")
                    result["url"] = j.get("content_urls", {}).get("desktop", {}).get("page", "")
                    if j.get("originalimage"):
                        result["image"] = j.get("originalimage", {}).get("source")
                    elif j.get("thumbnail"):
                        result["image"] = j.get("thumbnail", {}).get("source")
                if not result["image"]:
                    img_url = f"https://en.wikipedia.org/w/api.php?action=query&titles={urllib.parse.quote(title)}&prop=pageimages&format=json&pithumbsize=800"
                    r3 = requests.get(img_url, timeout=12, headers=headers)
                    if r3.status_code == 200:
                        pages = r3.json().get("query", {}).get("pages", {})
                        for p in pages.values():
                            if p.get("thumbnail"):
                                result["image"] = p.get("thumbnail", {}).get("source")
                                break
    except Exception as e:
        print(f"Wiki real error: {e}")
    if not result["text"]:
        low = clean_q.lower()
        if "lordina" in low or "mahama wife" in low:
            result["text"] = "Lordina Mahama is the First Lady of Ghana since 7 January 2025 (also 2012-2017). Married to John Mahama in 1992, 5 children: Shafik, Shahid, Sharaf, Jesse and Farida. Met at Ghana Secondary School, Tamale. Degree in Hospitality Management from GIMPA."
            result["image"] = "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6a/Lordina_Mahama.jpg/440px-Lordina_Mahama.jpg"
            result["url"] = "https://en.wikipedia.org/wiki/Lordina_Mahama"
            result["title"] = "Lordina Mahama"
        elif "john mahama" in low or "president of ghana" in low:
            result["text"] = "John Dramani Mahama is the 14th President of Ghana since 7 January 2025. He previously served 2012-2017. He won the 2024 election with 56.42% against Mahamudu Bawumia (41.75%). He is a member of NDC."
            result["image"] = "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/John_Dramani_Mahama.jpg/440px-John_Dramani_Mahama.jpg"
            result["url"] = "https://en.wikipedia.org/wiki/John_Dramani_Mahama"
            result["title"] = "John Dramani Mahama"
    return result

HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>MORR AI - Real Wiki</title>
<style>
body{background:#0a0a0a;color:white;font-family:system-ui;margin:0;padding:0;display:flex;flex-direction:column;height:100vh}
.header{padding:14px;text-align:center;border-bottom:1px solid #222}
h1{color:#FFD700;font-size:28px;margin:0}
.sub{color:#aaa;font-size:12px;margin-top:4px}
#chat{flex:1;overflow-y:auto;padding:16px;max-width:900px;width:100%;margin:0 auto;box-sizing:border-box}
.msg{padding:14px 18px;border-radius:18px;margin:10px 0;max-width:88%;line-height:1.7;word-wrap:break-word;font-size:14.5px;white-space:pre-wrap}
.user{background:#FFD700;color:black;margin-left:auto;border-bottom-right-radius:4px}
.ai{background:#1e1e1e;border:1px solid #333;border-bottom-left-radius:4px}
.input-area{border-top:1px solid #222;padding:12px;background:#0a0a0a;max-width:900px;margin:0 auto;width:100%;box-sizing:border-box}
.row{display:flex;gap:8px;align-items:center}
select{background:#2a2a2a;color:white;padding:10px;border-radius:10px;border:none}
#q{flex:1;padding:14px;border-radius:12px;border:none;background:#1e1e1e;color:white;font-size:16px;min-width:0}
.btn{padding:12px 16px;background:#FFD700;color:black;border:none;border-radius:12px;font-weight:bold;cursor:pointer}
.btn2{background:#333;color:white}
.msg img{max-width:100%;border-radius:12px;margin-top:10px;display:block}
.msg a{color:#FFD700}
.badge{display:inline-block;background:#333;color:#FFD700;padding:2px 8px;border-radius:8px;font-size:11px;margin-bottom:6px}
</style></head><body>
<div class="header"><h1>MORR AI GH <img src="https://flagcdn.com/w20/gh.png" style="width:20px;border-radius:3px"></h1><div class="sub">Real Wikipedia Photos • Smart Memory • File & Image Reader • Like Meta AI / GPT</div></div>
<div id="chat"></div>
<div class="input-area"><div id="status" style="color:#FFD700;font-size:12px"></div>
<div class="row"><select id="lang"><option>English</option><option>Pidgin</option><option>Twi</option><option>Hausa</option></select>
<input type="file" id="fileInput" hidden onchange="handleFile()" accept=".pdf,.docx,.txt,.csv,.json,.py,.js,.html,.md,.jpg,.jpeg,.png,.webp"><button class="btn btn2" onclick="document.getElementById('fileInput').click()">📎</button>
<input id="q" placeholder="Ask, upload image to analyze, or 'generate image of Kwame Nkrumah'"><button class="btn" onclick="sendText()">➤</button>
<button class="btn btn2" id="micBtn" onclick="toggleMic()">🎤</button></div>
<audio id="player" controls style="display:none;width:100%;margin-top:8px"></audio></div>
<script>
let chatHistory=[];let uploadedText="";let uploadedImageDesc="";let recorder,chunks=[],recording=false;
function addMsg(r,t,h=false){let c=document.getElementById('chat');let d=document.createElement('div');d.className='msg '+r;if(!t)t="...";if(h)d.innerHTML=t;else d.textContent=t;c.appendChild(d);c.scrollTop=c.scrollHeight;}
async function sendText(){
 let i=document.getElementById('q');let q=i.value.trim();if(!q&&!uploadedText&&!uploadedImageDesc)return;if(q)addMsg('user',q);i.value='';document.getElementById('status').innerText="MORR dey search real Wikipedia...";
 try{
  let body={question:q,file_context:uploadedText, image_context: uploadedImageDesc, language:document.getElementById('lang').value, history:chatHistory};
  let res=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  let data=await res.json();document.getElementById('status').innerText='';
  let out=""; if(data.badge) out+=`<span class='badge'>${data.badge}</span><br>`; out+=data.answer||"No answer";
  if(data.image_url) out+=`<br><img src="${data.image_url}"><br><a href="${data.image_url}" target="_blank">📥 Download Real Image</a>`;
  if(data.file_url) out+=`<br><a href="${data.file_url}">📥 Download File</a>`;
  if(data.source_url) out+=`<br><small><a href="${data.source_url}" target="_blank">🔗 Source: ${data.source_url}</a></small>`;
  addMsg('ai',out,true); chatHistory.push({role:'user',content:q},{role:'assistant',content:data.answer}); chatHistory=chatHistory.slice(-14);
  if(data.audio_url){let p=document.getElementById('player');p.style.display='block';p.src=data.audio_url+"?t="+Date.now();}
 }catch(e){document.getElementById('status').innerText=''; addMsg('ai','Error: '+e.message);}
 uploadedText=''; uploadedImageDesc=''; document.getElementById('fileInput').value='';
}
async function handleFile(){
 let f=document.getElementById('fileInput').files[0];if(!f)return;
 document.getElementById('status').innerText='📄 Analyzing '+f.name+'...';
 let fd=new FormData();fd.append('file',f);
 let res=await fetch('/upload',{method:'POST',body:fd});let data=await res.json();
 uploadedText=data.text||''; uploadedImageDesc=data.image_desc||'';
 document.getElementById('status').innerText='✅ '+f.name+' understood: '+(uploadedImageDesc||uploadedText||'ready').substring(0,80);
 if(data.preview){addMsg('user','[Uploaded: '+f.name+']<br><img src="'+data.preview+'">',true);}
}
async function toggleMic(){
 let btn=document.getElementById('micBtn');
 try{
  if(!recording){let s=await navigator.mediaDevices.getUserMedia({audio:true}); recorder=new MediaRecorder(s); chunks=[]; recorder.ondataavailable=e=>chunks.push(e.data);
   recorder.onstop=async()=>{let blob=new Blob(chunks,{type:'audio/webm'});let fd=new FormData();fd.append('audio',blob,'voice.webm');fd.append('language',document.getElementById('lang').value);document.getElementById('status').innerText='Transcribing...';let res=await fetch('/voice',{method:'POST',body:fd});let d=await res.json();if(d.text){document.getElementById('q').value=d.text;sendText();}else{document.getElementById('status').innerText='Could not transcribe';} s.getTracks().forEach(t=>t.stop());}; recorder.start(); recording=true; btn.innerText='🔴';
  }else{recorder.stop(); recording=false; btn.innerText='🎤';}
 }catch(e){document.getElementById('status').innerText='Mic error: '+e.message;}
}
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter')sendText();});
addMsg('ai',"Akwaaba! I am MORR AI 🇬🇭<br>I Operates In English, Pidgin, Twi & Hausa<br>How May I Help You Today?",true);
</script></body></html>"""

@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get('file')
    if not f: return jsonify({"text":"", "image_desc":"", "preview":None}),400
    name = f.filename.lower()
    tmp_path = os.path.join(tempfile.gettempdir(), f.filename)
    f.save(tmp_path)
    text = ""
    image_desc = ""
    preview_url = None
    is_image = name.endswith(('.jpg','.jpeg','.png','.webp','.bmp'))
    try:
        if is_image:
            preview_name = f"prev_{uuid.uuid4().hex[:8]}_{os.path.basename(tmp_path)}"
            preview_path = os.path.join(GENERATED_DIR, preview_name)
            from PIL import Image
            try:
                im = Image.open(tmp_path)
                im.thumbnail((800,800))
                im.save(preview_path)
                preview_url = f"/download/{preview_name}"
            except:
                preview_url = None
            if client:
                try:
                    uploaded = client.files.upload(file=tmp_path)
                    resp = client.models.generate_content(
                        model=MODEL_NAME,
                        contents=["Describe this image in detail. Who or what is in it? Read any text. If it's a person, who is it? This description will be used to answer user questions.", uploaded]
                    )
                    image_desc = resp.text or ""
                    text = f"[IMAGE UPLOADED: {f.filename}]\nVision Analysis: {image_desc}"
                except Exception as e:
                    image_desc = f"Image uploaded: {f.filename} (vision analysis failed: {e})"
                    text = image_desc
            else:
                image_desc = f"Image uploaded: {f.filename}. I can see it's an image file."
                text = image_desc
        elif name.endswith('.pdf'):
            import PyPDF2
            r = PyPDF2.PdfReader(tmp_path)
            text = " ".join([(p.extract_text() or "") for p in r.pages[:10]])[:10000]
        elif name.endswith(('.txt','.csv','.py','.js','.html','.json','.md')):
            with open(tmp_path,'r',errors='ignore') as file: text=file.read()[:10000]
        elif name.endswith('.docx'):
            import docx
            doc = docx.Document(tmp_path)
            text = " ".join([p.text for p in doc.paragraphs])[:10000]
        else:
            text=f"[File {f.filename} uploaded - type not fully supported but noted]"
    except Exception as e:
        text = f"[File {f.filename} read error: {e}]"
    return jsonify({"text":text, "image_desc":image_desc, "preview":preview_url})

@app.route("/ask", methods=["POST"])
def ask():
    try:
        d=request.get_json()
        q_raw=d.get("question","") or ""
        q_low=q_raw.lower()
        lang=d.get("language","English")
        file_ctx=d.get("file_context","")
        image_ctx=d.get("image_context","")
        history=d.get("history",[])[:12]
        resolved_q = resolve_context(q_raw, history)
        if any(k in q_low for k in ["generate image","create image","generate a picture","draw","picture of","image of","photo of","/image","show me picture","give me image"]):
            if image_ctx and any(w in q_low for w in ["like this","this image","this picture","this person","who is this","describe this","analyze this"]):
                wiki = get_wikipedia_real(image_ctx[:200])
                if wiki["image"]:
                    return jsonify({
                        "answer": f"🖼️ You uploaded an image. My analysis: {image_ctx}\n\nHere is the real Wikipedia photo that matches:\n{wiki['text'][:600]}",
                        "image_url": wiki["image"],
                        "source_url": wiki["url"],
                        "badge": f"Real Photo: {wiki['title']}"
                    })
                else:
                    return jsonify({
                        "answer": f"🖼️ Analysis of your uploaded image:\n{image_ctx}",
                        "badge": "Image Understanding"
                    })
            prompt=q_raw
            for k in ["generate image of","create image of","generate a picture of","generate a image of","generate image","create image","generate a","generate","draw","picture of","image of","photo of","/image","show me picture of","give me image of","picture of him","image of him","photo of him","him swearing in","swearing in"]:
                if k in prompt.lower():
                    prompt = prompt.lower().replace(k,"")
            prompt=prompt.strip() or resolved_q
            search_term = prompt if len(prompt)>2 else resolved_q
            if not search_term or len(search_term)<2:
                search_term = "John Dramani Mahama"
            wiki = get_wikipedia_real(search_term)
            if wiki["image"]:
                return jsonify({
                    "answer": f"📸 Real Wikipedia photo for: {search_term.title()}\n\n{wiki['text'][:800]}",
                    "image_url": wiki["image"],
                    "source_url": wiki["url"],
                    "badge": f"Real Photo: {wiki['title']} | Wikipedia"
                })
            else:
                return jsonify({
                    "answer": f"🔍 I searched Wikipedia for '{search_term}' - {wiki['text'][:800] if wiki['text'] else 'No real photo found, but here is info.'}\n\nTry a more specific name like 'Kwame Nkrumah' or 'John Mahama'",
                    "source_url": wiki["url"],
                    "badge": "Wikipedia Search"
                })
        if any(k in q_low for k in ["create pdf","generate pdf","create document","export to pdf","create file","generate doc","make pdf"]):
            try:
                from reportlab.pdfgen import canvas
                from reportlab.lib.pagesizes import A4
                search_term = resolved_q.replace("create pdf","").replace("generate pdf","").replace("about","").strip() or "Ghana"
                wiki = get_wikipedia_real(search_term)
                fname=f"morr_{uuid.uuid4().hex[:8]}.pdf"
                fpath=os.path.join(GENERATED_DIR, fname)
                local_img = None
                if wiki["image"]:
                    try:
                        r = requests.get(wiki["image"], timeout=10, headers={"User-Agent":"MORR AI GH"})
                        if r.status_code == 200:
                            ext = ".jpg"
                            if ".png" in wiki["image"]: ext=".png"
                            local_img = os.path.join(GENERATED_DIR, f"img_{uuid.uuid4().hex[:6]}{ext}")
                            with open(local_img, "wb") as f: f.write(r.content)
                    except: pass
                c=canvas.Canvas(fpath, pagesize=A4)
                w,h = A4
                c.setFont("Helvetica-Bold",18)
                c.drawString(50,h-60,f"MORR AI GH - Real Document")
                c.setFont("Helvetica-Bold",14)
                c.drawString(50,h-90,f"Topic: {wiki['title'] or search_term}")
                c.setFont("Helvetica",10)
                c.drawString(50,h-110,f"Source: {wiki['url'] or 'Wikipedia'}")
                if local_img and os.path.exists(local_img):
                    try:
                        c.drawImage(local_img, 50, h-300, width=200, height=150, preserveAspectRatio=True)
                        y_start = h-320
                    except:
                        y_start = h-140
                else:
                    y_start = h-140
                y = y_start
                c.setFont("Helvetica",11)
                full_text = wiki["text"] or f"No Wikipedia summary found for {search_term}"
                words = full_text.split()
                line=""
                for word in words:
                    if len(line+word) > 85:
                        c.drawString(50,y,line)
                        y-=15
                        line=word+" "
                        if y<80:
                            c.showPage()
                            y=h-50
                            c.setFont("Helvetica",11)
                    else:
                        line+=word+" "
                if line:
                    c.drawString(50,y,line)
                if file_ctx or image_ctx:
                    c.showPage()
                    c.setFont("Helvetica-Bold",12)
                    c.drawString(50,h-60,"Uploaded File Context:")
                    c.setFont("Helvetica",10)
                    y=h-80
                    combined = (file_ctx + "\n" + image_ctx)[:3000]
                    for line in combined.split("\n")[:60]:
                        c.drawString(50,y,line[:90])
                        y-=12
                        if y<50: break
                c.save()
                return jsonify({
                    "answer": f"📄 Created PDF with REAL Wikipedia data for: {wiki['title'] or search_term}\n\n{wiki['text'][:500]}",
                    "file_url": f"/download/{fname}",
                    "source_url": wiki["url"],
                    "badge": "Real Wiki PDF with Photo"
                })
            except Exception as e:
                return jsonify({"answer": f"PDF error: {e}"})
        ans = None
        wiki_data = None
        try:
            if client:
                system_prompt = f"You are MORR AI GH, Ghana's smartest AI like Meta AI, GPT, DeepSeek, Kimi. Language: {lang}. Be helpful, concise, smart. Remember history."
                full_prompt = system_prompt + "\n\n"
                if file_ctx:
                    full_prompt += f"UPLOADED FILE CONTENT TO STUDY:\n{file_ctx[:4000]}\n\n"
                if image_ctx:
                    full_prompt += f"UPLOADED IMAGE ANALYSIS:\n{image_ctx[:2000]}\n\n"
                if history:
                    full_prompt += "CONVERSATION HISTORY (use this for 'his wife' etc):\n"
                    for h in history[-6:]:
                        full_prompt += f"{h.get('role')}: {h.get('content','')[:400]}\n"
                full_prompt += f"\nUser question (resolved context: {resolved_q}): {q_raw}\nIf question is about a real person/place, I will search Wikipedia for you, but answer directly.\nAssistant:"
                resp = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        tools=[types.Tool(google_search=types.GoogleSearch())]
                    )
                )
                ans = resp.text
        except Exception as e:
            print(f"Gemini failed: {e}")
            ans = None
        if not ans:
            wiki_data = get_wikipedia_real(resolved_q)
            if wiki_data["text"]:
                ans = f"{wiki_data['text']}\n"
            else:
                ans = f"I couldn't get live answer, but here's what I know about '{resolved_q}'. Please rephrase."
        image_url = None
        source_url = None
        badge = None
        if not any(k in q_low for k in ["generate image","create image"]):
            wiki_for_image = wiki_data or get_wikipedia_real(resolved_q)
            if wiki_for_image["image"]:
                image_url = wiki_for_image["image"]
                source_url = wiki_for_image["url"]
                badge = f"Real Photo: {wiki_for_image['title']}"
        audio_url=None
        try:
            if HAS_GTTS and ans:
                fname_a=f"morr_{uuid.uuid4().hex[:6]}.mp3"
                fpath_a=os.path.join(GENERATED_DIR, fname_a)
                gTTS(text=ans[:400], lang='en').save(fpath_a)
                audio_url=f"/audio/{fname_a}"
        except: pass
        return jsonify({
            "answer": ans,
            "image_url": image_url,
            "source_url": source_url,
            "badge": badge,
            "audio_url": audio_url
        })
    except Exception as e:
        return jsonify({"answer": f"Server error: {str(e)[:600]}"}), 500

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
            resp = client.models.generate_content(model=MODEL_NAME, contents=["Transcribe this audio exactly:", uploaded])
            txt = resp.text or ""
    except: txt=""
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
