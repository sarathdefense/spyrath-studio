DASHBOARD_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Spyrath Studio</title>
<style>
:root { color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif; }
body { margin:0; background:#0b0d12; color:#f7f8fb; }
header { padding:28px 34px 18px; border-bottom:1px solid #242936; background:#10131a; }
h1 { margin:0; font-size:26px; } .sub { color:#9ca6b8; margin-top:7px; }
main { max-width:1100px; margin:auto; padding:28px 24px 60px; }
.toolbar { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }
button { border:0; border-radius:9px; padding:10px 14px; font-weight:650; cursor:pointer; }
.primary { background:#f1f4f8; color:#11151d; } .secondary { background:#232937; color:#eef1f7; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(330px,1fr)); gap:18px; }
.card { background:#141821; border:1px solid #282e3b; border-radius:14px; padding:20px; box-shadow:0 10px 30px #0003; }
.row { display:flex; justify-content:space-between; gap:12px; align-items:center; }
.title { font-size:19px; font-weight:750; } .status { text-transform:capitalize; color:#aab3c3; }
.progress { height:9px; border-radius:99px; overflow:hidden; background:#262c38; margin:16px 0 18px; }
.bar { height:100%; background:#e9edf4; transition:width .35s ease; }
.stage { display:flex; justify-content:space-between; padding:7px 0; border-bottom:1px solid #202531; font-size:14px; }
.stage:last-child { border:0; }.ok { color:#87d39c; }.bad { color:#ff9696; }.run { color:#f2cb7d; }.muted { color:#8c96a8; }
.actions { display:flex; gap:9px; margin-top:18px; }.error { color:#ffaaaa; font-size:13px; margin-top:12px; white-space:pre-wrap; }
.empty { color:#8994a6; padding:42px 0; text-align:center; }
a { color:inherit; }
</style>
</head>
<body>
<header><h1>Spyrath Studio</h1><div class="sub">Long-form AI presenter production</div></header>
<main>
<div class="toolbar"><strong>Projects</strong><button class="secondary" onclick="refresh()">Refresh</button></div>
<div id="projects" class="grid"></div>
<div id="empty" class="empty" hidden>No projects yet. Create one through the API to begin.</div>
</main>
<script>
const labels={narration:'Narration',audio_preparation:'Audio Preparation',presenter_video:'Presenter Generation',final_export:'Final Video'};
const marks={completed:'✓ Complete',running:'● Running',failed:'! Failed',pending:'○ Pending'};
function cls(s){return s==='completed'?'ok':s==='failed'?'bad':s==='running'?'run':'muted'}
async function action(id, name){
  await fetch(`/api/projects/${encodeURIComponent(id)}/${name}`,{method:'POST'});
  setTimeout(refresh,250);
}
function card(p){
 let stages=Object.entries(p.stages).map(([k,v])=>`<div class="stage"><span>${labels[k]||k}</span><span class="${cls(v.status)}">${marks[v.status]||v.status}</span></div>`).join('');
 let download=p.final_path?`<a href="/api/projects/${encodeURIComponent(p.project_id)}/download"><button class="secondary">Download</button></a>`:'';
 return `<section class="card"><div class="row"><div class="title">${escapeHtml(p.title)}</div><div class="status">${p.status}</div></div>
 <div class="progress"><div class="bar" style="width:${p.progress_percent}%"></div></div>${stages}
 ${p.last_error?`<div class="error">${escapeHtml(p.last_error)}</div>`:''}
 <div class="actions"><button class="primary" ${p.running?'disabled':''} onclick="action('${js(p.project_id)}','${p.status==='failed'||p.status==='partial'?'resume':'run'}')">${p.running?'Running…':(p.status==='failed'||p.status==='partial'?'Resume Production':'Run Production')}</button>${download}</div></section>`;
}
function escapeHtml(v){return String(v).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));}
function js(v){return String(v).replace(/\\/g,'\\\\').replace(/'/g,"\\'");}
async function refresh(){
 const res=await fetch('/api/projects'); const data=await res.json();
 document.getElementById('projects').innerHTML=data.projects.map(card).join('');
 document.getElementById('empty').hidden=data.projects.length>0;
}
refresh(); setInterval(refresh,3000);
</script>
</body></html>'''
