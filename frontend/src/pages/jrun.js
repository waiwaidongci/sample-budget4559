import {store} from '../stores/research.js';
import {joints} from '../api/research.js';
import {esc,fmt} from '../utils/format.js';
import {table} from '../components/common/table.js';
import {status} from '../components/common/status.js';
const COLS=['成员','状态','触达','点击','点击率','z 值','未校正 p','校正后 p','未校正结论','校正后结论','预算可负担触达','预算下功效'];
function row(m){return [m.member_key+(m.role==='control'?'（共同对照）':''),m.status==='withdrawn'?'已退出':'活跃',m.impressions,m.clicks,m.rate,m.z??'—',m.p_raw??'—',m.p_adj??'—',m.verdict_raw,m.verdict_adj,m.affordable??'—',m.power_budget==null?'—':m.power_budget];}
export async function render(id){
 if(!id)return '<h1>联合校正结论</h1><p>从联合研究页选择一次计算查看。</p>';
 const r=await joints.getRun(id);store.jointRunStatus=r.status;
 const head=`<div class="eyebrow">JOINT FAMILY · RUN ${r.id}</div><h1>${esc(r.name)} ${status(r.status)}</h1><div class="checksum">INPUT SHA256 ${r.checksum}</div><p>数据版本 v${r.data_version} · 整族种子 ${r.seed} · ${esc(r.created_at)}${r.finished_at?' · 完成 '+esc(r.finished_at):''} · ${r.published?'结论已生效':'结论未生效'}</p>`;
 if(r.status==='invalidated')return `${head}<div class="error">本计算已失效：${esc(r.invalidation_reason||'源数据更新')}。系统已按最新版本重算，请以最新生效结论为准。</div><p><a href="#joint/${r.joint_id}">返回联合研究 →</a></p>`;
 if(r.status==='failed')return `${head}<div class="error">计算失败：${esc(r.error)}。请更正成员数据后重新封存。</div><p><a href="#joint/${r.joint_id}">返回联合研究 →</a></p>`;
 if(!r.result)return `${head}<p class="method-note">任务正在队列中。此页每2秒更新，整族齐备后结论才生效。</p>`;
 const res=r.result,adopted=res.members.filter(m=>m.verdict_adj==='采用'),changed=res.members.filter(m=>m.role==='candidate'&&m.status==='active'&&m.verdict_raw!==m.verdict_adj);
 return `${head}<section class="result-intro"><strong>${esc(res.interpretation)}</strong><p>${esc(res.caveat)}</p></section>
 <h2>采用成员</h2><div class="strip"><span>${adopted.length?`校正后采用：${adopted.map(m=>esc(m.member_key)).join('、')}`:'校正后无候选被采用'}</span><span>${changed.length} 名候选结论在校正前后改变</span></div>
 <h2>核心数值</h2>${table(['业务指标','计算值'],Object.entries(res.metrics).map(([k,v])=>[k,fmt(v)]))}
 <h2>校正前后对照 <small>未校正逐项检验 vs 联合最大统计量校正</small></h2>${table(COLS,res.members.map(row))}
 <details><summary>本次冻结的参数与检验族快照</summary><pre>${esc(JSON.stringify({parameters:r.parameters,snapshot:r.snapshot},null,2))}</pre></details>
 <div class="toolbar"><a class="button secondary" href="#joint/${r.joint_id}">返回联合研究 →</a></div>`;
}
export function bind(){}
