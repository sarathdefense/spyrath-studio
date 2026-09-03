DASHBOARD_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Spyrath Studio</title>
<style>
:root { color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif; }
* { box-sizing:border-box; }
body { margin:0; background:#0b0d12; color:#f7f8fb; }
header { padding:28px 34px 18px; border-bottom:1px solid #242936; background:#10131a; }
h1 { margin:0; font-size:26px; } .sub { color:#9ca6b8; margin-top:7px; }
main { max-width:1120px; margin:auto; padding:28px 24px 60px; }
.toolbar { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; gap:12px; }
.toolbar-actions { display:flex; gap:9px; }
button { border:0; border-radius:9px; padding:10px 14px; font-weight:650; cursor:pointer; }
button:disabled { opacity:.55; cursor:not-allowed; }
.primary { background:#f1f4f8; color:#11151d; } .secondary { background:#232937; color:#eef1f7; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(330px,1fr)); gap:18px; }
.card { background:#141821; border:1px solid #282e3b; border-radius:14px; padding:20px; box-shadow:0 10px 30px #0003; }
.row { display:flex; justify-content:space-between; gap:12px; align-items:center; }
.title { font-size:19px; font-weight:750; } .status { text-transform:capitalize; color:#aab3c3; }
.progress { height:9px; border-radius:99px; overflow:hidden; background:#262c38; margin:16px 0 18px; }
.bar { height:100%; background:#e9edf4; transition:width .35s ease; }
.stage { display:flex; justify-content:space-between; padding:7px 0; border-bottom:1px solid #202531; font-size:14px; }
.stage:last-child { border:0; }.ok { color:#87d39c; }.bad { color:#ff9696; }.run { color:#f2cb7d; }.muted { color:#8c96a8; }
.actions { display:flex; gap:9px; margin-top:18px; flex-wrap:wrap; }.error { color:#ffaaaa; font-size:13px; margin-top:12px; white-space:pre-wrap; }
.empty { color:#8994a6; padding:42px 0; text-align:center; }
a { color:inherit; }
.modal-backdrop { position:fixed; inset:0; background:#000a; display:grid; place-items:center; padding:20px; z-index:10; }
.modal { width:min(680px,100%); max-height:92vh; overflow:auto; background:#141821; border:1px solid #313848; border-radius:16px; padding:22px; box-shadow:0 24px 80px #0009; }
.modal h2 { margin:0 0 6px; }.hint { color:#939eaf; font-size:13px; margin:0 0 20px; line-height:1.5; }
.form-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; }.full { grid-column:1/-1; }
label { display:block; color:#aab3c3; font-size:13px; margin-bottom:6px; }
input, select { width:100%; border:1px solid #343c4d; background:#0f131a; color:#f4f6fa; padding:11px 12px; border-radius:9px; }
input[type=file] { padding:9px; }
.modal-actions { display:flex; justify-content:flex-end; gap:9px; margin-top:20px; }
.form-error { color:#ffaaaa; font-size:13px; margin-top:12px; white-space:pre-wrap; }
.badge { font-size:12px; color:#8f9aab; margin-top:10px; }
@media (max-width:640px){ .form-grid{grid-template-columns:1fr}.full{grid-column:auto}.toolbar{align-items:flex-start;flex-direction:column} }
</style>
</head>
<body>
<header><h1>Spyrath Studio</h1><div class="sub">Long-form AI presenter production</div></header>
<main>
<div class="toolbar"><strong>Projects</strong><div class="toolbar-actions"><button class="secondary" onclick="refresh()">Refresh</button><button class="primary" onclick="openNewProject()">+ New Project</button></div></div>
<div id="projects" class="grid"></div>
<div id="empty" class="empty" hidden>No projects yet. Create your first presenter project.</div>
</main>
<div id="newProjectModal" class="modal-backdrop" hidden>
  <div class="modal">
    <div class="row"><div><h2>New Project</h2><p class="hint">Upload a UTF-8 .txt/.md manuscript, a voice sample, and a presenter image. Spyrath copies these assets into the project before production begins.</p></div><button class="secondary" onclick="closeNewProject()">✕</button></div>
    <form id="projectForm" onsubmit="createProject(event)">
      <div class="form-grid">
        <div><label>Project ID</label><input id="projectId" name="project_id" required pattern="[A-Za-z0-9._-]+" placeholder="ml-book" /></div>
        <div><label>Project title</label><input id="projectTitle" name="title" required placeholder="Machine Learning for Beginners" /></div>
        <div class="full"><label>Manuscript (.txt or .md)</label><input name="manuscript" type="file" accept=".txt,.md,.markdown,text/plain,text/markdown" required /></div>
        <div><label>Voice sample</label><input name="voice_reference" type="file" accept=".wav,.mp3,.m4a,.flac,.ogg,audio/*" required /></div>
        <div><label>Presenter image</label><input name="presenter_image" type="file" accept=".png,.jpg,.jpeg,.webp,image/*" required /></div>
        <div><label>Language</label><select name="language"><option value="en">English</option></select></div>
      </div>
      <div class="badge">Markdown # / ## headings become chapters automatically. Plain text becomes one chapter and is split into narration-sized segments.</div>
      <div id="formError" class="form-error"></div>
      <div class="modal-actions"><button type="button" class="secondary" onclick="closeNewProject()">Cancel</button><button id="createButton" type="submit" class="primary">Create Project</button></div>
    </form>
  </div>
</div>
<script>
const labels={narration:'Narration',audio_preparation:'Audio Preparation',presenter_video:'Presenter Generation',final_export:'Final Video'};
const marks={completed:'✓ Complete',running:'● Running',failed:'! Failed',pending:'○ Pending'};
function cls(s){return s==='completed'?'ok':s==='failed'?'bad':s==='running'?'run':'muted'}
async function action(id, name){
  const res=await fetch(`/api/projects/${encodeURIComponent(id)}/${name}`,{method:'POST'});
  if(!res.ok){ const body=await res.json().catch(()=>({detail:'Request failed'})); alert(body.detail||'Request failed'); }
  setTimeout(refresh,250);
}
function card(p){
 let stages=Object.entries(p.stages).map(([k,v])=>`<div class="stage"><span>${labels[k]||k}</span><span class="${cls(v.status)}">${marks[v.status]||v.status}</span></div>`).join('');
 let download=p.final_path?`<a href="/api/projects/${encodeURIComponent(p.project_id)}/download"><button class="secondary">Download Video</button></a>`:'';
 let actionName=p.status==='failed'||p.status==='partial'?'resume':'run';
 let actionLabel=p.running?'Running…':(actionName==='resume'?'Resume Production':p.status==='completed'?'Run Again':'Start Production');
 return `<section class="card"><div class="row"><div class="title">${escapeHtml(p.title)}</div><div class="status">${p.status}</div></div>
 <div class="badge">${escapeHtml(p.project_id)}</div><div class="progress"><div class="bar" style="width:${p.progress_percent}%"></div></div>${stages}
 ${p.last_error?`<div class="error">${escapeHtml(p.last_error)}</div>`:''}
 <div class="actions"><button class="primary" ${p.running?'disabled':''} onclick="action('${js(p.project_id)}','${actionName}')">${actionLabel}</button>${download}</div></section>`;
}
function escapeHtml(v){return String(v).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));}
function js(v){return String(v).replace(/\\/g,'\\\\').replace(/'/g,"\\'");}
async function refresh(){
 const res=await fetch('/api/projects'); const data=await res.json();
 document.getElementById('projects').innerHTML=data.projects.map(card).join('');
 document.getElementById('empty').hidden=data.projects.length>0;
}
function openNewProject(){ document.getElementById('newProjectModal').hidden=false; }
function closeNewProject(){ document.getElementById('newProjectModal').hidden=true; document.getElementById('formError').textContent=''; }
async function createProject(event){
 event.preventDefault(); const form=event.target; const button=document.getElementById('createButton'); const error=document.getElementById('formError');
 error.textContent=''; button.disabled=true; button.textContent='Creating…';
 try{
   const res=await fetch('/api/projects/upload',{method:'POST',body:new FormData(form)});
   const body=await res.json().catch(()=>({detail:'Unable to create project'}));
   if(!res.ok) throw new Error(body.detail||'Unable to create project');
   form.reset(); closeNewProject(); await refresh();
 }catch(e){ error.textContent=e.message; }
 finally{ button.disabled=false; button.textContent='Create Project'; }
}
refresh(); setInterval(refresh,3000);
</script>
</body></html>'''
