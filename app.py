import os, tempfile
from flask import Flask, render_template_string, request, jsonify, send_file
app = Flask(__name__)

# For local + live - will work both places
MY_GROQ_KEY = os.getenv("GROQ_API_KEY") 

from openai import OpenAI
client = OpenAI(api_key=MY_GROQ_KEY, base_url="https://api.groq.com/openai/v1")

try:
    from gtts import gTTS
    HAS_GTTS = True
except:
    HAS_GTTS = False

HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MORR AI GH - Study Buddy</title>
<style>body{background:#0a0a0a;color:white;font-family:system-ui;padding:12px;text-align:center}
h1{color:#FFD700;font-size:38px}.sub{color:#aaa;margin-bottom:18px}
.card{background:#1a1a1a;max-width:800px;margin:0 auto;padding:20px;border-radius:20px;border:1px solid #333}
select,input{padding:14px;border-radius:12px;border:none;font-size:16px;width:94%;margin:6px 0}
select{background:#2a2a2a;color:white;width:97%}
.btn{padding:13px 24px;background:#FFD700;color:black;border:none;border-radius:12px;font-weight:bold;cursor:pointer;margin:6px}
.btn2{background:#ff3b30;color:white}
.answer{background:#252525;padding:18px;border-radius:12px;margin-top:16px;text-align:left;line-height:1.8;border-left:4px solid #FFD700;white-space:pre-wrap;font-size:15px}
</style></head><body>
<h1>MORR AI GH 🇬🇭</h1><div class="sub">Your Ghanaian Study Buddy • Assignments • Projects • Any Question</div>
<div class="card">
<select id="lang"><option value="English">English</option><option value="Pidgin">Pidgin</option><option value="Twi">Twi</option><option value="Hausa">Hausa</option></select>
<input id="q" placeholder="Ask anything... Explain photosynthesis, solve math, write essay">
<br><button class="btn" onclick="sendText()">Ask MORR 🧠</button>
<button class="btn btn2" id="micBtn" onclick="toggleMic()">🎤 Tap to Talk</button>
<div id="status" style="margin-top:10px;color:#FFD700;font-weight:bold"></div>
<div id="answer" class="answer" style="display:none"></div>
<audio id="player" controls style="display:none;width:100%;margin-top:12px"></audio>
</div>
<script>
let recorder,chunks=[],recording=false;
async function sendText(){let q=document.getElementById('q').value;if(!q)return;await callMORR(q,document.getElementById('lang').value,false)}
async function callMORR(text,lang,isVoice){
document.getElementById('status').innerText="MORR dey think...";
let res=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:text,language:lang})});
let data=await res.json();document.getElementById('status').innerText="";
let a=document.getElementById('answer');a.style.display='block';a.innerText=data.answer;
if(data.audio_url){let p=document.getElementById('player');p.style.display='block';p.src=data.audio_url+"?t="+Date.now();if(isVoice)p.play();}
}
async function toggleMic(){
let btn=document.getElementById('micBtn');
if(!recording){let s=await navigator.mediaDevices.getUserMedia({audio:true});recorder=new MediaRecorder(s);chunks=[];
recorder.ondataavailable=e=>chunks.push(e.data);
recorder.onstop=async()=>{let blob=new Blob(chunks,{type:'audio/webm'});let fd=new FormData();fd.append('audio',blob,'voice.webm');fd.append('language',document.getElementById('lang').value);
document.getElementById('status').innerText="Listening...";let res=await fetch('/voice',{method:'POST',body:fd});let data=await res.json();
if(data.text){document.getElementById('q').value=data.text;await callMORR(data.text,data.language,true);} };
recorder.start();recording=true;btn.innerText="🔴 Stop";}else{recorder.stop();recording=false;btn.innerText="🎤 Tap to Talk";}}
</script></body></html>"""

def build_prompt(lang):
    return f"""You are MORR AI GH, a powerful general AI assistant from Ghana, like Meta AI / ChatGPT.
Answer ANYTHING: assignments, projects, math, science, coding, essays, history, life advice.
Be friendly, teacher-like, step-by-step. Answer in {lang}. If Twi/Hausa, explain clearly.
If user says hi, greet warmly and ask how you can help with studies.
Under 350 words unless needed. 🇬🇭"""

@app.route("/")
def home(): return render_template_string(HTML)

@app.route("/ask", methods=["POST"])
def ask():
    d=request.get_json(); q=d.get("question",""); lang=d.get("language","English")
    try:
        resp=client.chat.completions.create(model="openai/gpt-oss-20b", messages=[{"role":"system","content":build_prompt(lang)},{"role":"user","content":q}], temperature=0.7, max_tokens=1200)
        ans=resp.choices[0].message.content
    except Exception as e:
        ans=f"Error: {e}"
    try:
        fn=f"morr_{lang}.mp3"; fp=os.path.join(os.path.dirname(__file__), fn)
        if HAS_GTTS: gTTS(text=ans[:350], lang='en').save(fp); audio=f"/audio/{fn}"
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
    if not txt: txt="Hi"
    return jsonify({"text":txt,"language":lang})

@app.route("/audio/<filename>")
def serve_audio(filename):
    p=os.path.join(os.path.dirname(__file__), filename)
    if os.path.exists(p): return send_file(p, mimetype="audio/mpeg")
    return "not found",404

if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))