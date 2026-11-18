import {store,load} from '../stores/research.js';
import {joints} from '../api/research.js';
import {table} from '../components/common/table.js';
import {status} from '../components/common/status.js';
import {esc} from '../utils/format.js';
import {bindForm} from '../hooks/forms.js';
const NOTE='各候选共用同次对照抽样；候选退出仍保留原检验族。源数据更新使未发布计算失效并重算，迟归旧计算不覆盖新结论，整族齐备才生效。';
function memberForm(){return `<form id="member-form" class="inline-form"><label>成员编号<input name="member_key" placeholder="如 CAND-D" required minlength="2"></label><label>角色<select name="role"><option value="candidate">候选</option><option value="control">共同对照</option></select></label><label>触达数<input name="impressions" type="number" min="1" step="1" required></label><label>点击数<input name="clicks" type="number" min="0" step="1" required></label><label>单次触达成本 (元)<input name="cost_per_contact" type="number" step="any" min="0" placeholder="候选必填"></label><label>预算 (元)<input name="budget" type="number" step="any" min="0" placeholder="候选必填"></label><button type="submit">登记成员</button><button type="button" id="cancel-edit" hidden>取消编辑</button></form>`;}
export async function render(id){
 const writable=localStorage.getItem('research-role')!=='viewer';
 if(!id)return `<div class="eyebrow">06 / JOINT FAMILY</div><h1>联合研究</h1><p class="lead">多名候选共用同一组对照时，逐项检验会放大整族误报。联合研究预先登记候选与共同对照的触达和点击，以联合零假设模拟校准双侧最大检验量，给出校正结论与预算下各候选功效。</p><div class="method-note">${NOTE}</div>${writable?`<details><summary>新建联合研究</summary><form id="joint-form" class="inline-form"><label>名称<input name="name" required minlength="2"></label><label>说明<input name="description"></label><button type="submit">创建联合研究</button></form></details>`:'<p class="method-note">观察员可阅读联合研究，分析师与负责人可以登记成员并封存计算。</p>'}<h2>联合研究列表</h2>${table(['名称','数据版本','成员 / 活跃候选','最新生效结论'],store.joints.map(s=>[{html:`<a href="#joint/${s.id}">${esc(s.name)}</a>`},'v'+s.data_version,`${s.member_count} / ${s.active_candidates}`,s.latest_run_id?{html:`<a href="#jrun/${s.latest_run_id}">运行 #${s.latest_run_id} →</a>`}:'尚无']))}`;
 const s=await joints.get(id);store.jointId=s.id;
 const op=writable?['操作']:[];
 return `<div class="eyebrow">JOINT FAMILY · 研究 #${s.id}</div><h1>${esc(s.name)}</h1><p>数据版本 v${s.data_version} · 整族随机依据种子 ${s.seed_base} · ${esc(s.description||'')}</p><div class="method-note">${NOTE}</div>
 <h2>检验族成员 <small>共同对照一名；退出候选仍计入检验族</small></h2>${table(['成员','角色','状态','触达','点击','点击率','单次成本 (元)','预算 (元)',...op],s.members.map(m=>[m.member_key,m.role==='control'?'共同对照':'候选',m.status==='active'?'活跃':'已退出',m.impressions,m.clicks,m.clicks/m.impressions,m.cost_per_contact??'—',m.budget??'—',...(writable?[{html:m.status==='active'?`<button class="text" data-edit="${m.id}">编辑</button>${m.role==='candidate'?` <button class="text" data-withdraw="${m.id}">退出</button>`:''}`:'—'}]:[])]))}
 ${writable?`<h2 id="member-heading">登记成员</h2>${memberForm()}<h2>封存联合计算</h2><form id="seal-form" class="worksheet"><label>本次计算名称<input name="name" required minlength="2" value="${esc(s.name)} · 联合校正"></label><div class="inline-form"><label>显著性 α (0.001–0.2)<input name="alpha" type="number" step="any" value="0.05" required></label><label>Monte Carlo 次数 (200–20000)<input name="simulations" type="number" step="1" value="10000" required></label></div><p>封存时锁定当前完整同版检验族（版本 v${s.data_version}）与整族随机依据，后台 worker 独立计算。</p><button type="submit">封存并排队计算 →</button></form>`:''}
 <h2>计算记录 <small>失效原因可在此查询</small></h2>${table(['运行','状态','数据版本','生效 / 失效原因','登记时间'],s.runs.map(r=>[{html:`<a href="#jrun/${r.id}">#${r.id} ${esc(r.name)}</a>`},{html:status(r.status)},'v'+r.data_version,r.published?'已生效':(r.invalidation_reason||r.error||'—'),r.created_at]))}`;
}
export function bind(refresh){
 const writable=localStorage.getItem('research-role')!=='viewer';
 bindForm('joint-form',async data=>{const s=await joints.create(data);store.jointId=s.id;await load();location.hash='joint/'+s.id;});
 let editing=null;
 bindForm('member-form',async data=>{const x={member_key:data.member_key,role:data.role,impressions:+data.impressions,clicks:+data.clicks,cost_per_contact:data.cost_per_contact===''?null:+data.cost_per_contact,budget:data.budget===''?null:+data.budget};if(editing)await joints.saveMember(store.jointId,editing,x);else await joints.addMember(store.jointId,x);await load();refresh();});
 bindForm('seal-form',async data=>{const r=await joints.seal(store.jointId,{name:data.name,parameters:{alpha:+data.alpha,simulations:+data.simulations}});await load();location.hash='jrun/'+r.id;});
 document.querySelectorAll('[data-edit]').forEach(el=>el.onclick=async()=>{const d=await joints.get(store.jointId),m=d.members.find(x=>x.id===+el.dataset.edit),form=document.getElementById('member-form');editing=m.id;form.elements.member_key.value=m.member_key;form.elements.role.value=m.role;form.elements.impressions.value=m.impressions;form.elements.clicks.value=m.clicks;form.elements.cost_per_contact.value=m.cost_per_contact??'';form.elements.budget.value=m.budget??'';document.getElementById('member-heading').textContent='更正成员 '+m.member_key;document.getElementById('cancel-edit').hidden=false;form.scrollIntoView({behavior:'smooth',block:'center'});});
 const cancel=document.getElementById('cancel-edit');if(cancel)cancel.onclick=()=>refresh();
 document.querySelectorAll('[data-withdraw]').forEach(el=>el.onclick=async()=>{try{await joints.withdraw(store.jointId,+el.dataset.withdraw);await load();refresh();}catch(e){document.getElementById('notice').textContent=e.message;}});
}
