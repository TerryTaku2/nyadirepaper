/* Nyadire College Past Papers Portal - front-end logic.
   All data (accounts, intakes, papers, announcements) lives on the server; this file only
   talks to the /api endpoints. Nothing sensitive is stored in the browser. */
const state={session:{role:null},users:[],intakes:[],papers:[],studentPapers:[],announcements:[]};
let activeAdminRole='';

async function api(path,opts={}){
  const init={method:opts.method||'GET',credentials:'same-origin',headers:{}};
  if(opts.json!==undefined){init.headers['Content-Type']='application/json';init.body=JSON.stringify(opts.json)}
  if(opts.form)init.body=opts.form;
  let res;
  try{res=await fetch(path,init)}catch(e){throw new Error('Cannot reach the server. Check your connection and try again.')}
  let data=null;try{data=await res.json()}catch(e){}
  if(!res.ok){
    let msg=data&&data.detail;
    if(Array.isArray(msg))msg=msg.map(m=>{const f=(m.loc||[]).slice(-1)[0];return (f&&f!=='body'?f+': ':'')+String(m.msg||'').replace(/^Value error, /,'')}).join(' ');
    const err=new Error(msg||('Request failed ('+res.status+')'));err.status=res.status;
    if(res.status===401&&path.startsWith('/api/admin')&&path!=='/api/admin/login'&&activeAdminRole)adminSessionExpired();
    throw err;
  }
  return data;
}
function adminSessionExpired(){
  activeAdminRole='';state.session={role:null};
  document.getElementById('adminDashboard').classList.remove('show');
  refreshUltimatePanel();updateStudentLoginUI();
  notify('Your administrator session has ended. Please log in again.');
}

const modal=document.getElementById('modal'), toast=document.getElementById('toast');
document.getElementById('adminBtn').onclick=()=>{if(state.session.role==='admin')openAdminDashboard();else modal.classList.add('show')};document.getElementById('close').onclick=()=>modal.classList.remove('show');modal.onclick=e=>{if(e.target===modal)modal.classList.remove('show')};
function notify(t){toast.textContent=t;toast.style.display='block';clearTimeout(window.tt);window.tt=setTimeout(()=>toast.style.display='none',2600)}

function clearAuthFields(){['username','password','studentUsername','studentPassword','createStudentId','createDefaultPassword','createFullName','createNewPassword','createConfirmPassword','newStandardAdminPassword'].forEach(id=>{const e=document.getElementById(id);if(e)e.value='';});}
function refreshUltimatePanel(){const panel=document.getElementById('ultimateAdminPanel');if(!panel)return;panel.style.display=activeAdminRole==='ultimate'?'block':'none';document.getElementById('standardAdminPasswordView').value=activeAdminRole==='ultimate'?'Hidden - stored securely':'';document.getElementById('newStandardAdminPassword').value='';}
async function loadAdminData(){
  const [users,intakes,papers]=await Promise.all([api('/api/admin/students'),api('/api/admin/intakes'),api('/api/admin/papers')]);
  state.users=users;state.intakes=intakes;state.papers=papers;
}
function refreshOpenModals(){
  const vm=document.getElementById('intakeViewModal');if(vm&&vm.classList.contains('show'))renderIntakeView(vm.dataset.intake,vm.dataset.type);
  const am=document.getElementById('allAccountsModal');if(am&&am.classList.contains('show'))renderAllAccountsByIntake();
}
function renderAdminAll(){renderPapers();renderUsers();renderIntakes();populateIntakeSelect();refreshOpenModals();}
async function refreshStudents(){state.users=await api('/api/admin/students');renderUsers();renderIntakes();refreshOpenModals();}
async function openAdminDashboard(){
  try{await loadAdminData()}catch(e){if(e.status!==401)notify(e.message);return}
  document.getElementById('adminDashboard').classList.add('show');refreshUltimatePanel();renderAdminAll();
}
document.getElementById('login').onclick=async()=>{
  const u=document.getElementById('username').value.trim(),p=document.getElementById('password').value;
  if(!u||!p){notify('Enter the administrator username and password.');return}
  try{
    const r=await api('/api/admin/login',{method:'POST',json:{username:u,password:p}});
    state.session={role:'admin',adminRole:r.adminRole};activeAdminRole=r.adminRole;
    modal.classList.remove('show');clearAuthFields();updateStudentLoginUI();
    await openAdminDashboard();
    notify(r.adminRole==='ultimate'?'Ultimate Admin login successful. Security controls enabled.':'Admin login successful. Dashboard opened.');
  }catch(e){notify(e.message)}
};
document.getElementById('updateStandardAdminPassword').onclick=async()=>{
  if(activeAdminRole!=='ultimate'){notify('Ultimate Admin access is required.');return}
  const next=document.getElementById('newStandardAdminPassword').value;
  if(next.length<6){notify('Choose a standard admin password with at least 6 characters.');return}
  try{await api('/api/admin/standard-password',{method:'PUT',json:{new_password:next}});document.getElementById('newStandardAdminPassword').value='';notify('Standard admin password updated.')}catch(e){notify(e.message)}
};

const studentLoginModal=document.getElementById('studentLoginModal');
const studentBtn=document.getElementById('studentBtn');
function idSort(a,b){const ai=String(a.id||'').toUpperCase(),bi=String(b.id||'').toUpperCase();const an=ai.replace(/^E/,'').split('-').map(x=>parseInt(x,10)||0),bn=bi.replace(/^E/,'').split('-').map(x=>parseInt(x,10)||0);for(let i=0;i<Math.max(an.length,bn.length);i++){if((an[i]||0)!==(bn[i]||0))return (an[i]||0)-(bn[i]||0)}return ai.localeCompare(bi)}

function getUsers(){return state.users}
function renderUsers(){
  const list=document.getElementById('userList');
  const users=getUsers().slice().sort(idSort);
  const total=document.getElementById('totalStudents');
  if(total) total.textContent=String(users.length);
  if(!list)return;
  if(!users.length){list.innerHTML='<div class="intake-empty">No registered student accounts have been added yet.</div>';return;}
  list.innerHTML=users.map(u=>{
    const setup=!u.registered;
    const status=setup?'Not registered':'Login ready';
    const statusClass=setup?'pending':'ready';
    const action=setup ? `<span class="user-status ${statusClass}">${status}</span>` : `<button type="button" class="user-status ${statusClass} status-action" data-unregister="${esc(u.id)}" title="Reset this student to unregistered so they can register again">${status}</button>`;
    return `<div class="user-row"><div class="user-main"><div class="user-avatar">♙</div><div><strong>${esc(u.id)}</strong><span>${esc(u.name||'Name not set')}</span></div></div><div class="user-password" title="Programme and intake">${esc(u.type)} · ${esc(u.intake)}</div>${action}<button class="remove-user" data-id="${esc(u.id)}">Remove</button></div>`;
  }).join('');
  list.querySelectorAll('.remove-user').forEach(b=>b.onclick=()=>removeUser(b.dataset.id));
  list.querySelectorAll('[data-unregister]').forEach(b=>b.onclick=()=>unregisterStudent(b.dataset.unregister));
}
async function unregisterStudent(id){
  const user=getUsers().find(u=>String(u.id).toUpperCase()===String(id||'').toUpperCase());
  if(!user||!user.registered)return;
  if(!confirm('Unregister '+user.id+'? This signs the student out and resets the account to a temporary registration password so they can create a new password.'))return;
  try{
    const r=await api('/api/admin/students/'+encodeURIComponent(user.id)+'/unregister',{method:'POST'});
    await refreshStudents();
    notify(user.id+' is now unregistered. Temporary password: '+r.temporaryPassword);
  }catch(e){notify(e.message)}
}
async function removeUser(id){
  const user=getUsers().find(u=>String(u.id).toUpperCase()===String(id||'').toUpperCase());
  if(!user)return;
  if(!confirm('Remove student '+user.id+' from the portal? This will also prevent that account from logging in.'))return;
  try{await api('/api/admin/students/'+encodeURIComponent(user.id),{method:'DELETE'});await refreshStudents();notify('Student account removed successfully.')}catch(e){notify(e.message)}
}

function getIntakes(){return state.intakes}

function renderIntakes(){const list=document.getElementById('intakeList');if(!list)return;const ints=getIntakes();if(!ints.length){list.innerHTML='<div class="intake-empty">No intakes have been created.</div>';return}const ecdIcon='<span class="modern-intake-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21z"/><path d="M4 5.5V18a2.5 2.5 0 0 1 2.5-2.5H20M8 7h8M8 11h6"/></svg></span>';const juniorIcon='<span class="modern-intake-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="7" r="3"/><path d="M5 21c.7-4 3-6 7-6s6.3 2 7 6M8 11h8"/></svg></span>';const groups={};ints.forEach(it=>{const year=String(it.year||it.name||'2026');(groups[year]||(groups[year]=[])).push(it)});list.innerHTML=Object.entries(groups).sort((a,b)=>Number(b[0])-Number(a[0])).map(([year,items])=>{items.sort((a,b)=>Number(a.number)-Number(b.number));return `<div class="intake-year-group"><div class="intake-year-title">${esc(year)}</div><div class="intake-year-grid">${items.map(it=>{const fixedType=it.type||(String(it.number)==='20'?'ECD':String(it.number)==='31'?'Junior':'Both');const choices=fixedType==='ECD'?`<button class="intake-choice-btn ecd-choice" data-intake="${esc(it.number)}" data-type="ECD">${ecdIcon}<b>ECD</b><small>View ECD students</small></button>`:fixedType==='Junior'?`<button class="intake-choice-btn junior-choice" data-intake="${esc(it.number)}" data-type="Junior">${juniorIcon}<b>Junior</b><small>View Junior students</small></button>`:`<button class="intake-choice-btn ecd-choice" data-intake="${esc(it.number)}" data-type="ECD">${ecdIcon}<b>ECD</b><small>View ECD students</small></button><button class="intake-choice-btn junior-choice" data-intake="${esc(it.number)}" data-type="Junior">${juniorIcon}<b>Junior</b><small>View Junior students</small></button>`;return `<div class="intake-program-card"><div class="intake-program-head"><strong>Intake ${esc(it.number)}</strong><button class="delete-intake" data-intake="${esc(it.number)}">Remove</button></div><div class="intake-program-body"><div style="display:grid;grid-template-columns:minmax(0,1fr);gap:10px">${choices}</div></div></div>`}).join('')}</div></div>`}).join('');list.querySelectorAll('.delete-intake').forEach(b=>b.onclick=()=>removeIntake(b.dataset.intake));list.querySelectorAll('.intake-choice-btn').forEach(b=>b.onclick=()=>openIntakeView(b.dataset.intake,b.dataset.type))}
function openIntakeView(intake,type){const modal=document.getElementById('intakeViewModal');const intakeObj=getIntakes().find(x=>String(x.number)===String(intake)); document.getElementById('intakeViewTitle').textContent=(intakeObj?.name||intakeObj?.year||'2026')+' — '+type; document.getElementById('intakeViewSub').textContent=type+' students in Intake '+intake+' ('+(intakeObj?.name||intakeObj?.year||'2026')+'), sorted by Student ID.';renderIntakeView(intake,type);modal.classList.add('show');modal.dataset.intake=intake;modal.dataset.type=type;}
function renderIntakeView(intake,type){const box=document.getElementById('intakeViewList');const users=getUsers().filter(u=>String(u.intake)===String(intake)&&u.type===type).sort(idSort);if(!users.length){box.innerHTML='<div class="intake-empty">No '+type+' students have been added to Intake '+esc(intake)+' yet.</div>';return}box.innerHTML=users.map(u=>`<div class="intake-view-row"><div><div class="intake-view-id">${esc(u.id)}</div><div class="intake-view-meta">${esc(u.name||'Name not set')}</div></div><button class="intake-view-remove" data-id="${esc(u.id)}">Remove</button></div>`).join('');box.querySelectorAll('.intake-view-remove').forEach(b=>b.onclick=()=>{removeUser(b.dataset.id);renderIntakeView(intake,type);renderIntakes();})}
function renderAllAccountsByIntake(){
  const box=document.getElementById('allAccountsList');
  const users=getUsers().slice().sort((a,b)=>Number(a.intake||0)-Number(b.intake||0)||String(a.type||'').localeCompare(String(b.type||''))||idSort(a,b));
  if(!users.length){box.innerHTML='<div class="intake-empty">No student accounts have been created yet.</div>';return;}
  const groups={};users.forEach(u=>{const key=String(u.intake||'Unassigned');(groups[key]||(groups[key]=[])).push(u);});
  box.innerHTML=Object.keys(groups).sort((a,b)=>a==='Unassigned'?1:b==='Unassigned'?-1:Number(a)-Number(b)).map(intake=>{
    const arr=groups[intake];
    return `<section style="margin:12px 0;padding:14px;border:1px solid #e0e9f6;border-radius:12px;background:#fff"><h4 style="margin:0 0 10px;color:#063b91">${intake==='Unassigned'?'Unassigned accounts':'Intake '+esc(intake)} <span style="font-weight:500;color:#71819c">(${arr.length})</span></h4><div style="overflow:auto"><table style="width:100%;border-collapse:collapse;text-align:left;font-size:13px"><thead><tr>${['Student ID','Full Name','Status','Intake','Programme','Account Type','Action'].map(h=>`<th style="padding:8px;border-bottom:1px solid #e0e9f6">${h}</th>`).join('')}</tr></thead><tbody>${arr.map(u=>`<tr><td style="padding:8px;border-bottom:1px solid #eef2f8">${esc(u.id)}</td><td style="padding:8px;border-bottom:1px solid #eef2f8">${esc(u.name||'Name not set')}</td><td style="padding:8px;border-bottom:1px solid #eef2f8">${u.registered?'Login ready':'Not registered'}</td><td style="padding:8px;border-bottom:1px solid #eef2f8">${esc(u.intake||'Unassigned')}</td><td style="padding:8px;border-bottom:1px solid #eef2f8">${esc(u.type||'Not set')}</td><td style="padding:8px;border-bottom:1px solid #eef2f8">${esc(u.accountType||u.status||'Student')}</td><td style="padding:8px;border-bottom:1px solid #eef2f8"><button type="button" class="intake-view-remove" data-id="${esc(u.id)}">Remove</button></td></tr>`).join('')}</tbody></table></div></section>`;
  }).join('');
  box.querySelectorAll('.intake-view-remove').forEach(b=>b.onclick=()=>{removeUser(b.dataset.id);renderAllAccountsByIntake();});
}
document.getElementById('viewAllAccountsByIntake').onclick=()=>{renderAllAccountsByIntake();document.getElementById('allAccountsModal').classList.add('show');};
document.getElementById('closeAllAccounts').onclick=()=>document.getElementById('allAccountsModal').classList.remove('show');
document.getElementById('allAccountsModal').onclick=e=>{if(e.target.id==='allAccountsModal')e.currentTarget.classList.remove('show')};
function populateIntakeSelect(){const sel=document.getElementById('intakeStudentIntake');if(!sel)return;sel.innerHTML=getIntakes().map(x=>`<option value="${esc(x.number)}">Intake ${esc(x.number)}${x.name&&x.name!==`Intake ${x.number}`?' — '+esc(x.name):''}</option>`).join('')}

async function removeIntake(number){
  const target=String(number);
  const affected=getUsers().filter(u=>String(u.intake)===target);
  const message=affected.length?'Remove Intake '+target+' and permanently remove its '+affected.length+' student account'+(affected.length===1?'':'s')+'?':'Remove Intake '+target+' permanently?';
  if(!confirm(message))return;
  try{
    await api('/api/admin/intakes/'+encodeURIComponent(target),{method:'DELETE'});
    const [intakes,users]=await Promise.all([api('/api/admin/intakes'),api('/api/admin/students')]);
    state.intakes=intakes;state.users=users;
    renderUsers();renderIntakes();populateIntakeSelect();refreshOpenModals();
    notify('Intake '+target+' was permanently removed.');
  }catch(e){notify(e.message)}
}

function updateStudentLoginUI(){const logged=state.session.role==='student';document.body.classList.toggle('student-logged-in',logged);studentBtn.innerHTML=logged?'<span>✓</span> Student Logout':'<span>♙</span> Student Login';studentBtn.classList.toggle('logged',logged);}
studentBtn.onclick=async()=>{
  if(state.session.role==='student'){
    try{await api('/api/logout',{method:'POST'})}catch(e){}
    state.session={role:null};document.getElementById('studentUsername').value='';document.getElementById('studentPassword').value='';
    document.getElementById('studentPapersModal')?.classList.remove('show');
    updateStudentLoginUI();notify('Student logged out. Login fields cleared.');
  }else studentLoginModal.classList.add('show');
};

document.getElementById('closeStudentLogin').onclick=()=>{studentLoginModal.classList.remove('show');document.getElementById('studentUsername').value='';document.getElementById('studentPassword').value='';};
studentLoginModal.onclick=e=>{if(e.target===studentLoginModal)studentLoginModal.classList.remove('show')};
const studentCreateModal=document.getElementById('studentCreateModal');
document.getElementById('openStudentCreate').onclick=()=>{studentLoginModal.classList.remove('show');studentCreateModal.classList.add('show')};
document.getElementById('closeStudentCreate').onclick=()=>studentCreateModal.classList.remove('show');
studentCreateModal.onclick=e=>{if(e.target===studentCreateModal)studentCreateModal.classList.remove('show')};
document.getElementById('studentLogin').onclick=async()=>{
  const u=document.getElementById('studentUsername').value.trim(),p=document.getElementById('studentPassword').value;
  if(!u||!p){notify('Enter your Student ID and password.');return}
  try{
    const r=await api('/api/student/login',{method:'POST',json:{student_id:u,password:p}});
    if(activeAdminRole){activeAdminRole='';document.getElementById('adminDashboard').classList.remove('show');refreshUltimatePanel();}
    state.session={role:'student',student:r.student};
    document.getElementById('studentUsername').value='';document.getElementById('studentPassword').value='';
    studentLoginModal.classList.remove('show');updateStudentLoginUI();notify('Student login successful.');
  }catch(e){notify(e.message)}
};
document.getElementById('saveStudentAccount').onclick=async()=>{
  const rosterId=document.getElementById('createStudentId').value.trim(),tempPassword=document.getElementById('createDefaultPassword').value,full=document.getElementById('createFullName').value.trim(),np=document.getElementById('createNewPassword').value,cp=document.getElementById('createConfirmPassword').value;
  if(!rosterId||!tempPassword||!full||!np||!cp){notify('Complete all fields.');return}
  if(np!==cp){notify('The new passwords do not match.');return}
  if(np.length<6){notify('New password must be at least 6 characters long.');return}
  try{
    await api('/api/student/register',{method:'POST',json:{student_id:rosterId,temporary_password:tempPassword,full_name:full,new_password:np}});
    studentCreateModal.classList.remove('show');
    ['createStudentId','createDefaultPassword','createFullName','createNewPassword','createConfirmPassword'].forEach(id=>document.getElementById(id).value='');
    document.getElementById('studentUsername').value=rosterId;
    notify('Account registered successfully. Please sign in with your Student ID.');
    studentLoginModal.classList.add('show');
  }catch(e){notify(e.message)}
};

function updateSitePaperCount(count){const el=document.getElementById('sitePaperCount');if(el)el.textContent=String(count)}
function getPapers(){return state.papers}

function renderPapers(){
  const current=getPapers();updateSitePaperCount(current.length);
  const list=document.getElementById('paperList'), q=(document.getElementById('paperSearch').value||'').toLowerCase();
  const papers=getPapers().filter(x=>((x.moduleTitle||x.title||'')+' '+(x.moduleCode||'')+' '+(x.level||'')+' '+(x.programme||'')+' '+(x.subject||'')+' '+(x.department||'')+' '+(x.year||'')+' '+(x.file||'')).toLowerCase().includes(q));
  const all=getPapers();
  document.getElementById('totalPapers').textContent=all.length;
  document.getElementById('totalSubjects').textContent=new Set(all.map(x=>x.subject)).size;renderUsers();
  if(!papers.length){list.innerHTML='<div class="empty-papers"><div class="empty-icon">▤</div><h4>No past papers added yet</h4><p>Click “Add Past Paper” to upload and organise an examination paper.</p></div>';return}
  list.innerHTML=papers.map(x=>`<div class="paper-row"><div class="paper-icon">PDF</div><div><div class="paper-name">${esc(x.moduleTitle||x.title||'Untitled Module')}</div><div class="paper-meta">${esc(x.moduleCode||'No module code')} • ${esc(x.level||'Level not set')} • ${esc(x.semester||'Semester not set')} • ${esc(x.subject||'No subject')} • ${esc(x.file||'No file selected')}</div></div><div class="paper-tag">${esc(x.programme==='Both'?'Junior & ECD':(x.programme||'Both'))}</div><div class="paper-tag">${esc(x.year)}</div><button class="delete-paper" data-id="${x.id}">Delete</button></div>`).join('');
  list.querySelectorAll('.delete-paper').forEach(b=>b.onclick=()=>deletePaper(b.dataset.id));
}
function esc(v){return String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))}

async function deletePaper(id){
  const item=getPapers().find(x=>String(x.id)===String(id));if(!item)return;
  if(!confirm('Delete “'+(item.moduleTitle||item.title||'this paper')+'” from the paper list?'))return;
  try{await api('/api/admin/papers/'+encodeURIComponent(id),{method:'DELETE'});state.papers=await api('/api/admin/papers');renderPapers();notify('Past paper deleted successfully.')}catch(e){notify(e.message)}
}

document.getElementById('openAddPaper').onclick=()=>document.getElementById('paperFormModal').classList.add('show');
document.getElementById('closePaperForm').onclick=()=>document.getElementById('paperFormModal').classList.remove('show');
document.getElementById('cancelPaper').onclick=()=>document.getElementById('paperFormModal').classList.remove('show');
document.getElementById('paperFormModal').onclick=e=>{if(e.target.id==='paperFormModal')e.currentTarget.classList.remove('show')};
document.getElementById('paperSearch').oninput=renderPapers;
const departmentSubjects={
  'Natural Science':['Computer Science','Mathematics','Biology','Physics','Chemistry','Agriculture'],
  'Humanities':['English','Shona','Ndebele','Disaster Risk Management','Life Skills','Entrepreneurship','Communication Skills','Health and Life Skills in Education','Education Legal Frameworks, Leadership and Management','Citizenship for National Development'],
  'P.E and Arts':['Music','Art','Physical Education'],
  'Educational Foundation':['Psychology','Sociology','Philosophy','Legal Frameworks','Education Legal Frameworks, Leadership and Management','Transformative Psychological Perspectives of Education','Transformative Sociological Perspectives of Education','Transformative Philosophical Perspectives of Education']
};
function updateSubjectOptions(){
  const select=document.getElementById('paperSubject');
  const dept=document.getElementById('paperDept').value;
  const subjects=departmentSubjects[dept]||[];
  select.innerHTML=subjects.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('')+'<option value="__other__">Other — type a subject</option>';
  updateCustomSubjectVisibility();
}
function updateCustomSubjectVisibility(){
  const other=document.getElementById('paperSubject').value==='__other__';
  document.getElementById('customSubjectWrap').style.display=other?'block':'none';
  document.getElementById('customPaperSubject').required=other;
}
document.getElementById('paperDept').addEventListener('change',updateSubjectOptions);
document.getElementById('paperSubject').addEventListener('change',updateCustomSubjectVisibility);
const moduleTitleSelect=document.getElementById('paperModuleTitle');
function updateCustomModuleTitle(){const other=moduleTitleSelect.value==='__other__';document.getElementById('customModuleTitleWrap').style.display=other?'block':'none';document.getElementById('customPaperModuleTitle').required=other;}
moduleTitleSelect.addEventListener('change',updateCustomModuleTitle);
updateSubjectOptions();updateCustomModuleTitle();
document.getElementById('savePaper').onclick=async()=>{
  const selectedModuleTitle=document.getElementById('paperModuleTitle').value, customModuleTitle=document.getElementById('customPaperModuleTitle').value.trim(), moduleTitle=selectedModuleTitle==='__other__'?customModuleTitle:selectedModuleTitle, moduleCode=document.getElementById('paperModuleCode').value.trim(), level=document.getElementById('paperLevel').value, semester=document.getElementById('paperSemester').value, programme=document.getElementById('paperProgramme').value, dept=document.getElementById('paperDept').value, selectedSubject=document.getElementById('paperSubject').value, customSubject=document.getElementById('customPaperSubject').value.trim(), subject=selectedSubject==='__other__'?customSubject:selectedSubject, year=document.getElementById('paperYear').value.trim(), file=document.getElementById('paperFile').files[0];
  if(!moduleTitle||!moduleCode||!level||!semester||!subject||!year){notify('Please complete the Module Title, Module Code, Subject, Level, Semester and examination year.');return}
  if(!file){notify('Please choose a PDF examination paper.');return}
  if(file.type!=='application/pdf' && !/\.pdf$/i.test(file.name)){notify('Only PDF examination papers can be uploaded.');return}
  const saveBtn=document.getElementById('savePaper');saveBtn.disabled=true;
  const form=new FormData();
  form.append('moduleTitle',moduleTitle);form.append('moduleCode',moduleCode);form.append('level',level);form.append('semester',semester);
  form.append('programme',programme);form.append('department',dept);form.append('subject',subject);form.append('year',year);form.append('file',file);
  try{
    await api('/api/admin/papers',{method:'POST',form});
    state.papers=await api('/api/admin/papers');renderPapers();document.getElementById('paperFormModal').classList.remove('show');

  ['paperModuleTitle','paperModuleCode','paperYear','customPaperSubject'].forEach(k=>document.getElementById(k).value='');document.getElementById('paperFile').value='';document.getElementById('paperProgramme').value='Both';document.getElementById('paperLevel').value='Level 1';document.getElementById('paperSemester').value='Semester 1';document.getElementById('paperDept').value='Natural Science';updateSubjectOptions();
  notify('Past paper added successfully.');
  }catch(e){notify(e.message)}finally{saveBtn.disabled=false}
};
document.getElementById('logoutAdmin').onclick=async()=>{
  try{await api('/api/logout',{method:'POST'})}catch(e){}
  document.getElementById('adminDashboard').classList.remove('show');activeAdminRole='';state.session={role:null};
  state.users=[];state.papers=[];state.intakes=[];
  refreshUltimatePanel();clearAuthFields();updateStudentLoginUI();
  api('/api/papers/count').then(r=>updateSitePaperCount(r.count)).catch(()=>{});
  notify('Administrator logged out. Login and password fields cleared.');
};

document.getElementById('viewSite').onclick=()=>document.getElementById('adminDashboard').classList.remove('show');
document.getElementById('openAddIntake').onclick=()=>document.getElementById('intakeFormModal').classList.add('show');
document.getElementById('closeIntakeForm').onclick=()=>document.getElementById('intakeFormModal').classList.remove('show');
document.getElementById('cancelIntake').onclick=()=>document.getElementById('intakeFormModal').classList.remove('show');

document.getElementById('closeIntakeStudent').onclick=()=>document.getElementById('intakeStudentModal').classList.remove('show');
document.getElementById('closeIntakeView').onclick=()=>document.getElementById('intakeViewModal').classList.remove('show');
document.getElementById('addFromIntakeView').onclick=()=>{const modal=document.getElementById('intakeViewModal');const intake=modal.dataset.intake,type=modal.dataset.type;populateIntakeSelect();document.getElementById('intakeStudentIntake').value=intake;document.querySelectorAll('input[name=studentType]').forEach(r=>r.checked=r.value===type);document.getElementById('intakeStudentModal').classList.add('show');suggestNextStudentId();};
document.getElementById('cancelIntakeStudent').onclick=()=>document.getElementById('intakeStudentModal').classList.remove('show');
function currentStudentType(){return document.querySelector('input[name="studentType"]:checked')?.value||'Junior'}
function suggestNextStudentId(){const type=currentStudentType(),intake=document.getElementById('intakeStudentIntake').value||'31',users=getUsers();const nums=users.filter(u=>u.type===type&&String(u.intake)===String(intake)).map(u=>{const m=String(u.id).match(/(\d+)$/);return m?parseInt(m[1],10):0});const next=(Math.max(0,...nums)+1).toString().padStart(2,'0');document.getElementById('intakeStudentId').value=type==='ECD'?'E24-'+intake+'-'+next:'24-'+intake+'-'+next}
document.getElementById('suggestStudentId').onclick=suggestNextStudentId;document.querySelectorAll('input[name="studentType"]').forEach(r=>r.addEventListener('change',suggestNextStudentId));
document.getElementById('saveIntake').onclick=async()=>{
  const year=document.getElementById('newIntakeYear').value.trim(),ecd=document.getElementById('newEcdIntakeNumber').value.trim(),junior=document.getElementById('newJuniorIntakeNumber').value.trim();
  if(!year||!/^(19|20)\d{2}$/.test(year)){notify('Enter a valid 4-digit intake year.');return}
  if(!ecd||!/^[0-9]+$/.test(ecd)||!junior||!/^[0-9]+$/.test(junior)){notify('Enter valid numbers for both ECD and Junior intakes.');return}
  if(ecd===junior){notify('ECD and Junior must use different intake numbers.');return}
  try{
    state.intakes=await api('/api/admin/intakes',{method:'POST',json:{year:+year,ecd_number:+ecd,junior_number:+junior}});
    renderIntakes();populateIntakeSelect();document.getElementById('intakeFormModal').classList.remove('show');
    ['newEcdIntakeNumber','newJuniorIntakeNumber','newIntakeYear'].forEach(id=>document.getElementById(id).value='');
    notify('ECD '+ecd+' and Junior '+junior+' intakes for '+year+' added successfully.');
  }catch(e){notify(e.message)}
};
document.getElementById('saveIntakeStudent').onclick=async()=>{
  const intake=document.getElementById('intakeStudentIntake').value,type=currentStudentType(),id=document.getElementById('intakeStudentId').value.trim(),password=document.getElementById('intakeStudentPassword').value,name=document.getElementById('intakeStudentName').value.trim();
  if(!intake||!id||!password){notify('Select an intake and enter Student ID and temporary password.');return}
  try{
    await api('/api/admin/students',{method:'POST',json:{student_id:id,intake:+intake,type,password,name}});
    await refreshStudents();document.getElementById('intakeStudentModal').classList.remove('show');
    ['intakeStudentId','intakeStudentPassword','intakeStudentName'].forEach(x=>document.getElementById(x).value='');
    notify(id+' added to Intake '+intake+' as '+type+'. Give the student their temporary password so they can register.');
  }catch(e){notify(e.message)}
};

const bulkUploadModal=document.getElementById('bulkUploadModal');
const bulkFile=document.getElementById('bulkStudentFile');
const bulkText=document.getElementById('bulkStudentText');
function parseCSVRows(text){const lines=String(text||'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean);if(!lines.length)return [];const start=/student\s*id/i.test(lines[0])?1:0;return lines.slice(start).map(line=>{const parts=[];let cur='',quoted=false;for(let i=0;i<line.length;i++){const ch=line[i];if(ch==='"'){if(quoted&&line[i+1]==='"'){cur+='"';i++;}else quoted=!quoted}else if(ch===','&&!quoted){parts.push(cur.trim());cur=''}else cur+=ch}parts.push(cur.trim());return{id:parts[0]||'',name:parts[1]||'',password:parts[2]||''}})}
function openBulkUpload(intake,type){bulkUploadModal.dataset.intake=intake;bulkUploadModal.dataset.type=type;document.getElementById('bulkStudentType').value=type;document.getElementById('bulkUploadSub').textContent='Bulk add '+type+' students to Intake '+intake+'. Use Student ID, Name, Password columns.';bulkUploadModal.classList.add('show')}
document.getElementById('bulkFromIntakeView').onclick=()=>{const m=document.getElementById('intakeViewModal');openBulkUpload(m.dataset.intake,m.dataset.type)};
document.getElementById('closeBulkUpload').onclick=()=>bulkUploadModal.classList.remove('show');document.getElementById('cancelBulkUpload').onclick=()=>bulkUploadModal.classList.remove('show');bulkUploadModal.onclick=e=>{if(e.target===bulkUploadModal)bulkUploadModal.classList.remove('show')};
document.getElementById('saveBulkUpload').onclick=async()=>{
  let data=bulkText.value.trim();if(!data&&bulkFile.files[0])data=await bulkFile.files[0].text();
  const intake=bulkUploadModal.dataset.intake,type=bulkUploadModal.dataset.type||document.getElementById('bulkStudentType').value;
  if(!intake){notify('Select an intake first.');return}
  const rows=parseCSVRows(data);if(!rows.length){notify('Choose a CSV file or paste CSV rows.');return}
  try{
    const r=await api('/api/admin/students/bulk',{method:'POST',json:{intake:+intake,type,rows:rows.map(x=>({student_id:x.id,name:x.name,password:x.password}))}});
    if(!r.added){notify('No valid new students were found. Check IDs, passwords and duplicates.');return}
    await refreshStudents();bulkUploadModal.classList.remove('show');bulkText.value='';bulkFile.value='';
    notify(r.added+' '+type+' student'+(r.added===1?'':'s')+' added'+(r.skipped.length?' ('+r.skipped.length+' skipped)':'')+'.');
  }catch(e){notify(e.message)}
};

document.getElementById('searchBtn').onclick=()=>{const q=document.getElementById('searchInput').value.toLowerCase().trim();if(!q){notify('Enter a subject or examination to search.');return}const card=[...document.querySelectorAll('.card')].find(c=>c.dataset.subject.toLowerCase().includes(q)||c.innerText.toLowerCase().includes(q));if(card){card.scrollIntoView({behavior:'smooth',block:'center'});card.animate([{transform:'scale(1)'},{transform:'scale(1.03)'},{transform:'scale(1)'}],{duration:600});notify('Matching department found: '+card.dataset.subject)}else notify('No matching examination found.');};
const studentModal=document.getElementById('studentPapersModal');
document.getElementById('closeStudentPapers').onclick=()=>studentModal.classList.remove('show');
studentModal.onclick=e=>{if(e.target===studentModal)studentModal.classList.remove('show')};

function openStoredPaper(id){
  const record=state.studentPapers.find(x=>String(x.id)===String(id));
  const viewer=document.getElementById('paperViewerModal');
  document.getElementById('paperViewerTitle').textContent=record?.file||'Past Paper';
  document.getElementById('paperViewerFrame').src='/api/papers/'+encodeURIComponent(id)+'/file';
  viewer.classList.add('show');
}
function closePaperViewer(){
  document.getElementById('paperViewerFrame').src='about:blank';
  document.getElementById('paperViewerModal').classList.remove('show');
}
async function showDepartmentPapers(department){
  if(state.session.role!=='student'){
    notify('Please log in as a student to access past papers.');
    document.getElementById('studentLoginModal').classList.add('show');
    return;
  }
  let papers;
  try{papers=await api('/api/papers?department='+encodeURIComponent(department))}
  catch(e){
    if(e.status===401){state.session={role:null};updateStudentLoginUI();document.getElementById('studentLoginModal').classList.add('show')}
    notify(e.message);return;
  }
  state.studentPapers=papers;
  const studentType=String(state.session.student.type||'Student');

  document.getElementById('studentPapersTitle').textContent=department+' — Past Papers';
  document.getElementById('studentPapersSubtitle').textContent=papers.length?papers.length+' paper'+(papers.length===1?'':'s')+' available for '+(studentType==='ECD'?'ECD':studentType==='Junior'?'Junior':'your programme'):'No papers have been added for your programme yet';
  const list=document.getElementById('studentPaperList');
  if(!papers.length){list.innerHTML='<div class="student-empty"><div style="font-size:40px;margin-bottom:10px">▤</div><strong>No past papers available</strong><span>Please check again after the administrator adds papers.</span></div>';}
  else {list.innerHTML=papers.map(x=>`<div class="student-paper"><div class="student-paper-icon">${esc((x.file||'PDF').split('.').pop().toUpperCase())}</div><div><h4>${esc(x.moduleTitle||x.title||'Untitled Module')}</h4><p>${esc(x.moduleCode||'No module code')} • ${esc(x.level||'Level not set')} • ${esc(x.subject||'No subject')} • ${esc(x.year)} • ${esc(x.programme==='Both'?'Junior & ECD':(x.programme||'Both'))}</p></div><div class="paper-actions"><button class="open-paper" data-id="${x.id}">Open Paper ↗</button></div></div>`).join('');
    list.querySelectorAll('.open-paper').forEach(b=>b.onclick=()=>openStoredPaper(b.dataset.id));}
  studentModal.classList.add('show');
}
[...document.querySelectorAll('.card')].forEach(c=>c.addEventListener('click',()=>showDepartmentPapers(c.dataset.subject)));
const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('revealed');io.unobserve(e.target)}}),{threshold:.15});document.querySelectorAll('.card').forEach(c=>io.observe(c));

const paperViewerModal=document.createElement('div');
paperViewerModal.id='paperViewerModal';
paperViewerModal.innerHTML=`<div class="paper-viewer"><div class="paper-viewer-head"><strong id="paperViewerTitle">Past Paper</strong><div class="paper-viewer-actions"><button id="closePaperViewer" type="button">Close</button></div></div><iframe id="paperViewerFrame" title="Past Paper Viewer"></iframe></div>`;
document.body.appendChild(paperViewerModal);
document.getElementById('closePaperViewer').onclick=closePaperViewer;
paperViewerModal.onclick=e=>{if(e.target===paperViewerModal)closePaperViewer()};
// Polished ripple feedback for interactive controls
[...document.querySelectorAll('.nav a,.admin-btn,.explore,.search button,.login')].forEach(btn=>btn.addEventListener('click',function(e){const r=document.createElement('span');r.className='ripple';const rect=this.getBoundingClientRect();const size=Math.max(rect.width,rect.height);r.style.width=r.style.height=size+'px';r.style.left=(e.clientX-rect.left-size/2)+'px';r.style.top=(e.clientY-rect.top-size/2)+'px';this.appendChild(r);setTimeout(()=>r.remove(),700)}));
// Smooth active navigation state while scrolling
const sections=[document.getElementById('home'),document.getElementById('subjects')];const navLinks=[...document.querySelectorAll('.nav a')];const navIO=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){navLinks.forEach(a=>a.classList.remove('active'));const a=navLinks.find(x=>x.getAttribute('href')==='#'+entry.target.id);if(a)a.classList.add('active')}}),{threshold:.45});sections.forEach(s=>navIO.observe(s));

async function loadAnnouncements(){
  try{state.announcements=(await api('/api/announcements')).map(a=>({...a,date:new Date(a.createdAt).toLocaleDateString()}))}catch(e){}
  renderAnnouncements();
}
function getAnnouncements(){return state.announcements}
async function renderAnnouncements(){
 const list=document.getElementById('publicAnnouncements'), adminList=document.getElementById('adminAnnouncementsList');
 const items=getAnnouncements().sort((a,b)=>Number(b.createdAt||0)-Number(a.createdAt||0));
 if(list) list.innerHTML=items.length?items.map((a,i)=>`<article class="announcement-card ${i===0?'latest-announcement':''}"><div class="announcement-icon">!</div><div class="announcement-content">${i===0?`<span class="announcement-badge">New</span>`:''}<h3>${esc(a.title)}</h3>${a.body?`<p>${esc(a.body).replace(/\n/g,'<br>')}</p>`:''}${a.pdfName?`<p class="pdf-action"><a href="#" data-announcement-pdf="${esc(a.id)}" download="${esc(a.pdfName||'announcement.pdf')}">📄 View / Download PDF: ${esc(a.pdfName||'Announcement PDF')}</a></p>`:''}<span class="announcement-date">${esc(a.date||'')}</span></div></article>`).join(''):'<article class="announcement-card"><div class="announcement-icon">i</div><div><h3>College Announcements</h3><p>There are no announcements at the moment. Please check again later.</p></div></article>';
 if(adminList) adminList.innerHTML=items.length?items.map(a=>`<div class="announcement-admin-item"><div><strong>${esc(a.title)}</strong><div style="font-size:12px;color:#687b98;margin-top:4px">${esc(a.date||'')} · ${esc(a.body)}${a.pdfName?' · 📄 '+esc(a.pdfName)+' attached':''}</div></div><button type="button" data-delete-announcement="${esc(a.id)}">Delete</button></div>`).join(''):'<p style="color:#71819c;font-size:13px">No announcements published yet.</p>';
 if(list) list.querySelectorAll('[data-announcement-pdf]').forEach(link=>link.addEventListener('click',e=>{
  e.preventDefault();
  if(state.session.role!=='student'&&state.session.role!=='admin'){notify('Please log in with your student account to view or download announcement PDFs.');document.getElementById('studentLoginModal')?.classList.add('show');return;}
  window.open('/api/announcements/'+encodeURIComponent(link.dataset.announcementPdf)+'/pdf','_blank','noopener');
 }));
 if(adminList) adminList.querySelectorAll('[data-delete-announcement]').forEach(b=>b.onclick=async()=>{
  if(!confirm('Delete this announcement?'))return;
  try{await api('/api/admin/announcements/'+encodeURIComponent(b.dataset.deleteAnnouncement),{method:'DELETE'});await loadAnnouncements();}catch(e){notify(e.message)}
 });
}

document.getElementById('publishAnnouncement').addEventListener('click',async()=>{
 const button=document.getElementById('publishAnnouncement'),title=document.getElementById('announcementTitle').value.trim(),body=document.getElementById('announcementBody').value.trim(),fileInput=document.getElementById('announcementPdf'),file=fileInput.files&&fileInput.files[0];
 if(!title){notify('Enter an announcement title.');return;}
 if(!body&&!file){notify('Enter announcement details or attach a PDF file.');return;}
 if(file&&file.type!=='application/pdf'&&!file.name.toLowerCase().endsWith('.pdf')){notify('Please choose a PDF file.');return;}
 if(file&&file.size>10*1024*1024){notify('Please choose a PDF smaller than 10 MB.');return;}
 button.disabled=true;button.textContent='Publishing…';
 try{
  const form=new FormData();form.append('title',title);form.append('body',body);if(file)form.append('file',file);
  await api('/api/admin/announcements',{method:'POST',form});
  await loadAnnouncements();
  document.getElementById('announcementTitle').value='';document.getElementById('announcementBody').value='';fileInput.value='';notify('Announcement published on the home page.');
 }catch(e){notify(e.message)}
 finally{button.disabled=false;button.textContent='＋ Publish';}
});

// ---------------------------------------------------------------------- start-up
(async function init(){
  try{state.session=await api('/api/session')}catch(e){}
  if(state.session.role==='admin')activeAdminRole=state.session.adminRole;
  updateStudentLoginUI();
  api('/api/papers/count').then(r=>updateSitePaperCount(r.count)).catch(()=>{});
  loadAnnouncements();
})();

