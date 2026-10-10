import os, tempfile, urllib.parse
from flask import Flask, render_template_string, request, jsonify, send_file
app = Flask(__name__)

MY_GROQ_KEY = os.getenv("GROQ_API_KEY")
from openai import OpenAI
client = OpenAI(api_key=MY_GROQ_KEY, base_url="https://api.groq.com/openai/v1")

HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MORR AI GH</title>
<style>
body{background:#0a0a0a;color:white;font-family:system-ui;margin:0;padding:0;display:flex;flex-direction:column;height:100vh}
.header{padding:14px;text-align:center;border-bottom:1px solid #222}
h1{color:#FFD700;font-size:28px;margin:0}
.sub{color:#aaa;font-size:12px}
#chat{flex:1;overflow-y:auto;padding:14px;max-width:850px;width:100%;margin:0 auto;box-sizing:border-box}
.msg{padding:12px 16px;border-radius:16px;margin:8px 0;max-width:85%;line-height:1.6;font-size:14px;white-space:pre-wrap;word-wrap:break-word}
.user{background:#FFD700;color:black;margin-left:auto}
.ai{background:#1f1f1f;border:1px solid #333}
.row{display:flex;gap:8px;align-items:center}
#q{flex:1;padding:13px;border-radius:12px;border:none;background:#1e1e1e;color:white}
.btn{padding:12px 16px;background:#FFD700;color:black;border:none;border-radius:12px;font-weight:bold}
.input-area{border-top:1px solid #222;padding:10px;background:#0a0a0a;max-width:850px;margin:0 auto;width:100%;box-sizing:border-box}
</style></head><body>
<div class="header"><h1>MORR AI GH <img src="https://flagcdn.com/w20/gh.png" style="width:22px"></h1><div class="sub">Ghana's Smart Assistant for Studies, Business & Afro culture</div></div>
<div id="chat"></div>
<div class="input-area"><div class="row">
<input id="q" placeholder="Ask or 'draw a modern school in Ghana'"><button class="btn" onclick="sendText()">➤</button>
</div><div id="status" style="color:#FFD700;font-size:11px;margin-top:4px"></div></div>
<script>
let hist=[];
function addMsg(r,t,h=false){let c=document.getElementById('chat');let d=document.createElement('div');d.className='msg '+r;if(h)d.innerHTML=t;else d.innerText=t;c.appendChild(d);c.scrollTop=c.scrollHeight;}
function isImg(q){q=q.toLowerCase();return q.includes('generate image')||q.includes('create image')||q.includes('draw')||q.includes('picture of')||q.includes('image of')||q.includes('photo of');}
async function sendText(){
 let inp=document.getElementById('q');let q=inp.value.trim();if(!q)return;addMsg('user',q);inp.value='';
 if(isImg(q)){
  let prompt=q.replace(/generate image of/gi,'').replace(/create image of/gi,'').replace(/generate image/gi,'').replace(/draw/gi,'').replace(/picture of/gi,'').replace(/image of/gi,'').replace(/photo of/gi,'').trim()||q;
  document.getElementById('status').innerText='Generating image...';
  let p=encodeURIComponent(prompt);
  // 100% FREE - NO POLLINATIONS, NO BEE, NO PAYMENT EVER
  let url1=`https://source.unsplash.com/512x512/?${p}`;
  let url2=`https://loremflickr.com/512/512/${p}`;
  document.getElementById('status').innerText='';
  addMsg('ai',`🎨 Here is your image for: <b>${prompt}</b><br><img src="${url1}" onerror="this.src='${url2}'" style="max-width:100%;border-radius:12px;margin-top:8px"><br><a href="${url1}" target="_blank" style="color:#FFD700">📥 Download</a>`,true);
  return;
 }
 document.getElementById('status').innerText='MORR dey think...';
 try{
  let res=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q,history:hist})});
  let data=await res.json();document.getElementById('status').innerText='';addMsg('ai',data.answer);hist.push({role:'user',content:q},{role:'assistant',content:data.answer});
 }catch(e){document.getElementById('status').innerText='';addMsg('ai','Network error, try again');}
}
document.getElementById('q').addEventListener('keypress',e=>{if(e.key==='Enter')sendText();});
addMsg('ai','Akwaaba! I am MORR AI GH 🇬🇭\nGhana\\'s Smart Assistant for Studies, Business & Afro culture\nI do chat, images, files — what do you want today?');
</script></body></html>"""

@app.route("/")
def home(): return render_template_string(HTML)

@app.route("/ask", methods=["POST"])
def ask():
    d=request.get_json()
    q_raw=d.get("question","")
    history=d.get("history",[])[:6]
    msgs=[{"role":"system","content":"You are MORR AI GH, Ghana's Smart Assistant for Studies, Business & Afro culture. Be helpful and concise. Date May 2026."}]
    for h in history: msgs.append(h)
    msgs.append({"role":"user","content":q_raw})
    ans="Sorry connection issue, try again."
    for model in ["llama-3.3-70b-versatile","llama-3.1-8b-instant","gemma2-9b-it"]:
        try:
            r=client.chat.completions.create(model=model,messages=msgs,max_tokens=800,temperature=0.4)
            if r.choices[0].message.content: ans=r.choices[0].message.content; break
        except: continue
    return jsonify({"answer":ans})

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
