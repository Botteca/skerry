'use strict';
const $c = document.getElementById('c');
const A = () => window.pywebview.api;

let S = null, expanded = false, lastKey = '', lastSize = '', uiSeq = null, view = null;
let thumbId = 0, thumbSrc = null, dropping = false, dropTimer = null, collapseTimer = null;
let drag = null, suppressClick = false, volFlash = 0, lastKind = '';
let grantMenu = null;                 // pid whose "allow for N minutes" choices are open
let onbStep = 0, onbActive = false;   // guided setup: current step, shown while S.onboarding is set
const dismissedDone = new Set();

// ---------------- utilities ----------------
const esc = s => String(s ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const mmss = s => { s = Math.max(0, Math.floor(s || 0)); const h = Math.floor(s/3600), m = Math.floor(s%3600/60), x = s%60;
  return h ? `${h}:${String(m).padStart(2,'0')}:${String(x).padStart(2,'0')}` : `${m}:${String(x).padStart(2,'0')}`; };
const pctColor = p => p >= 90 ? 'var(--red)' : p >= 70 ? 'var(--amber)' : 'var(--green)';
const until = e => { const d = Math.max(0, e - S.now), h = Math.floor(d/3600), m = Math.floor(d%3600/60); return h ? `${h}h ${m}m` : `${m}m`; };
const when = e => I18N.weekdayTime(e);
const AGENT = {claude:'Claude Code', codex:'Codex', gemini:'Gemini CLI', copilot:'Copilot CLI'};
// Data Factory run status -> [dot class, translation key]
const ADF_STATUS = {Succeeded: ['done', 'adf.succeeded'], Failed: ['error', 'adf.failed'], InProgress: ['working', 'adf.running'],
  Queued: ['working', 'adf.queued'], Cancelled: ['idle', 'adf.cancelled'], Canceling: ['idle', 'adf.cancelled'], none: ['idle', 'adf.none']};
const SQL_DOT = {green: 'done', amber: 'waiting', red: 'error', error: 'error'};
const GLYPH = {claude:'✦', codex:'◆', gemini:'✧', copilot:'⬢'};
const GRANT_MINUTES = [5, 15, 60];   // same as skerry/store.py GRANT_MINUTES
const glyph = (agent, spin) => `<span class="ag ${agent} ${spin ? 'spin' : ''}">${GLYPH[agent] || '✦'}</span>`;
const mod = m => !S.settings.modules || S.settings.modules[m] !== false;
const vertical = () => ['left','right'].includes(S.settings.edge);

function ring(p, size = 16, color, sw = 2.5){
  const r = size/2 - sw/2 - 0.5, c = 2*Math.PI*r, off = c*(1 - Math.min(100, Math.max(0, p))/100), h = size/2;
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="flex:none">
    <circle cx="${h}" cy="${h}" r="${r}" fill="none" stroke="var(--chip2)" stroke-width="${sw}"/>
    <circle cx="${h}" cy="${h}" r="${r}" fill="none" class="rc" style="--c:${c}" stroke="${color || pctColor(p)}" stroke-width="${sw}" stroke-linecap="round"
      stroke-dasharray="${c}" stroke-dashoffset="${off}" transform="rotate(-90 ${h} ${h})"/></svg>`;
}
const art = cls => thumbSrc ? `<img class="${cls}" src="${thumbSrc}">` : `<div class="${cls}">♪</div>`;
function mediaPos(m){ let p = m.position + (m.playing ? Math.max(0, S.now - m.updated) : 0); return m.duration ? Math.min(p, m.duration) : p; }

function artColor(src){
  if (!src){ document.documentElement.style.removeProperty('--art'); return; }
  const img = new Image();
  img.onload = () => {
    const cv = document.createElement('canvas'); cv.width = cv.height = 16;
    const x = cv.getContext('2d'); x.drawImage(img, 0, 0, 16, 16);
    const d = x.getImageData(0, 0, 16, 16).data; let r = 0, g = 0, b = 0, n = 0;
    for (let i = 0; i < d.length; i += 4){
      const R = d[i], G = d[i+1], B = d[i+2], mx = Math.max(R,G,B), mn = Math.min(R,G,B);
      if (mx < 35) continue; const w = 1 + (mx - mn)/24; r += R*w; g += G*w; b += B*w; n += w;
    }
    if (!n) return;
    [r, g, b] = [r/n, g/n, b/n]; const k = Math.max(1, 170/Math.max(r, g, b));
    document.documentElement.style.setProperty('--art', `rgb(${Math.min(255,r*k)|0},${Math.min(255,g*k)|0},${Math.min(255,b*k)|0})`);
  };
  img.src = src;
}

// ---------------- derived data ----------------
const active = () => S.sessions.filter(s => ['working','waiting','permission'].includes(s.status));
function current(){ const a = active(); return a.find(s => s.sid === S.selected) || a[0]; }
function badges(skipTimer){
  const sy = S.system || {}; let h = '';
  if ((sy.mic || []).length) h += `<span class="pd mic" title="${tx('privacy.mic', {apps: sy.mic.join(', ')})}"></span>`;
  if ((sy.cam || []).length) h += `<span class="pd cam" title="${tx('privacy.cam', {apps: sy.cam.join(', ')})}"></span>`;
  if (S.timer && !skipTimer) h += `<span class="chip on" data-live="tmc">${mmss(S.timer.left)}</span>`;
  for (const g of S.grants || []) h += `<span class="chip on grant" data-act="revoke" data-arg="${g.id}"
    title="${tx('grant.tip', {tool: g.tool, project: g.project || AGENT[g.agent]})}">⏱ ${vertical() ? '' : esc(g.tool) + ' '}<span data-live="gr" data-until="${g.until}">${mmss(g.until - S.now)}</span></span>`;
  return h;
}
const badgeKey = () => { const sy = S.system || {}; return [(sy.mic||[]).length, (sy.cam||[]).length, !!S.timer, (S.grants||[]).map(g => g.id)].join(); };

function compactMain(){
  const s = current();
  if (s) return {type:'agent', s};
  if (S.media && S.media.playing) return {type:'media'};
  if (S.timer) return {type:'timer'};
  return {type:'idle'};
}

// ---------------- compact views ----------------
function vCompact(){
  const m = compactMain(), vert = vertical(), b = badges(m.type === 'timer'), f = S.limits && S.limits.five_hour;
  const base = {r: vert ? 22 : 18, auto: !vert, w: vert ? 44 : null, type: m.type};
  if (m.type === 'agent'){
    const s = m.s, n = active().length, idx = active().indexOf(s), tk = s.tasks;
    const spin = s.status === 'working';
    if (vert) return {...base, key:`va${s.sid}${s.status}${tk&&tk.done}${badgeKey()}`, html:`<div class="tab">${glyph(s.agent, spin)}
      ${s.status === 'waiting' ? '<span class="dot waiting"></span>' : ''}
      ${tk ? `<div class="t">${tk.done}/${tk.total}</div>` : ''}${n > 1 ? `<div class="t">${idx+1}/${n}</div>` : ''}${b}</div>`};
    return {...base, key:`a${s.sid}${s.status}${s.action}${n}${idx}${tk&&[tk.done,tk.total]}${badgeKey()}`, html:`<div class="bar">
      ${glyph(s.agent, spin)}<span>${esc(s.icon)}</span><span class="txt">${esc(s.action)}</span>
      ${tk ? `<span class="chip on">☑ ${tk.done}/${tk.total}</span>` : ''}
      <span class="chip">${esc(s.project || AGENT[s.agent])}</span>${n > 1 ? `<span class="chip">${idx+1}/${n}</span>` : ''}
      ${s.status === 'waiting' ? '<span class="dot waiting"></span>' : ''}${b}</div>`};
  }
  if (m.type === 'media'){
    const md = S.media, vf = Date.now() - volFlash < 1300 && S.audio;
    const right = vf ? `<span class="vmini"><i data-live="vmini" style="width:${(S.audio.volume||0)*100}%"></i></span>`
                     : `<span class="eq"><i></i><i></i><i></i><i></i></span>`;
    if (vert) return {...base, key:`vm${thumbId}${badgeKey()}`, html:`<div class="tab">${art('art-s')}<span class="eq"><i></i><i></i><i></i></span>${b}</div>`};
    return {...base, key:`m${md.title}${thumbId}${vf}${badgeKey()}`, html:`<div class="bar">${art('art-s')}
      <span class="txt">${esc(md.title)}<span class="muted"> · ${esc(md.artist)}</span></span>${right}${b}</div>`};
  }
  if (m.type === 'timer'){
    const tm = S.timer, p = 100 * (1 - tm.left / tm.duration), col = tm.phase === 'focus' || tm.mode === 'timer' ? 'var(--accent)' : 'var(--green)';
    if (vert) return {...base, key:`vt${tm.label}${tm.paused}${badgeKey()}`, html:`<div class="tab">${ring(p, 20, col)}<div class="t" data-live="tmb">${mmss(tm.left)}</div>${b}</div>`};
    return {...base, key:`t${tm.label}${tm.paused}${badgeKey()}`, html:`<div class="bar">${ring(p, 18, col)}
      <span class="muted sm">${esc(tm.label)}${tm.paused ? ' · ' + tx('timer.paused') : ''}</span><span class="big" data-live="tmb">${mmss(tm.left)}</span>${b}</div>`};
  }
  const lim = f && mod('claude') ? `${ring(f.used_percentage)}<span class="sm">${Math.round(f.used_percentage)}%</span><span class="muted xs">${tx('usage.fiveHourShort')}</span>` : '';
  if (vert) return {...base, key:`vi${f&&Math.round(f.used_percentage)}${badgeKey()}`, html:`<div class="tab">${glyph('claude')}${f ? ring(f.used_percentage) : ''}${b}</div>`};
  return {...base, key:`i${f&&Math.round(f.used_percentage)}${badgeKey()}`,
    html:`<div class="bar">${glyph('claude')}${lim || '<span class="muted sm">Skerry</span>'}${b}</div>`};
}

// ---------------- cards ----------------
function vPermission(){
  const p = S.pending[0], more = S.pending.length - 1, menu = grantMenu === p.id;
  const btns = menu
    ? `${GRANT_MINUTES.map(m => `<button class="b-always" data-act="decide" data-arg="grant:${m}">${tx('perm.minutes', {n: m})}</button>`).join('')}
      <button data-act="grant-menu">${tx('perm.back')}</button>`
    : `<button class="b-allow" data-act="decide" data-arg="allow">${tx('perm.allow')}</button>
      ${p.can_grant ? `<button class="b-grant" data-act="grant-menu" title="${tx('perm.grantTip')}">⏱▾</button>` : ''}
      ${p.can_always ? `<button class="b-always" data-act="decide" data-arg="always" title="${tx('perm.alwaysTip')}">${tx('perm.always')}</button>` : ''}
      <button class="b-deny" data-act="decide" data-arg="deny">${tx('perm.deny')}</button>
      <button data-act="decide" data-arg="terminal" title="${tx('perm.terminalTip')}">${tx('perm.terminal')}</button>`;
  return {w:480, r:26, key:'p'+p.id+more+menu, pid:p.id, html:`<div class="card">
    <div class="hd">${glyph(p.agent)}<b>${esc(p.project || AGENT[p.agent])}</b><span class="muted">· ${tx('perm.asks', {agent: AGENT[p.agent]})}</span>
      <span class="sp"></span>${more ? `<span class="chip">+${more}</span>` : ''}</div>
    <div class="title">${esc(p.icon)} ${esc(p.text)}</div>
    ${p.detail && p.detail !== p.text ? `<div class="detail mono">${esc(p.detail)}</div>` : ''}
    <div class="btns">${btns}</div></div>`};
}
function vAlert(a){
  return {w:420, r:24, key:'al'+a.id, aid:a.id, html:`<div class="alert ${a.level}" data-act="dismiss" data-arg="${a.id}">
    <span class="aico">${esc(a.icon)}</span><span>${esc(a.text)}</span></div>`};
}
function vDone(s){
  const ok = s.status === 'done';
  return {w:440, r:24, key:'d'+s.sid+s.done_at, done:s.sid+s.done_at, html:`<div class="card" ${s.has_window ? `data-act="focus" data-arg="${esc(s.sid)}"` : ''}>
    <div class="hd"><span class="dot ${s.status}"></span><b>${esc(s.project || AGENT[s.agent])}</b>
      <span class="muted">· ${tx(ok ? 'done.finished' : 'done.stopped', {agent: AGENT[s.agent]})}</span></div>
    <div class="clamp2 ${ok ? '' : 'muted'}">${ok ? (s.done_msg ? esc(s.done_msg) : tx('done.default')) : esc(s.action)}</div></div>`};
}
const vDrop = () => ({w:340, r:28, key:'drop', html:`<div class="drop"><b>${tx('drop.title')}</b><span class="muted sm">${tx('drop.hint')}</span></div>`});

const BT_ICON = {mouse:'🖱️', keyboard:'⌨️', headset:'🎧', speaker:'🔊', pen:'✒️', gamepad:'🎮', phone:'📱', device:'🔹'};
const fmtTok = n => n >= 1e6 ? I18N.number(n/1e6, n >= 1e7 ? 0 : 1) + 'M' : n >= 1e3 ? Math.round(n/1e3) + 'k' : String(n);
function claudeBlock(){
  if (!mod('claude')) return '';
  const L = S.limits, sl = S.statusline || {}, u = mod('usage') && S.usage;
  const g = (label, w, sub) => `<div class="gauge">${ring(w.used_percentage, 46, undefined, 4.5)}
    <div class="gv"><b>${Math.floor(w.used_percentage)}%</b><span>${label}</span><span class="muted">${sub}</span></div></div>`;
  const age = L && L.received_at ? Math.max(0, S.now - L.received_at) : 0;
  const ago = age > 120 ? ' · ' + t('usage.dataAge', {age: age >= 3600 ? Math.floor(age/3600) + 'h' : Math.floor(age/60) + 'm'}) : '';
  const hasPct = !!(L && (L.five_hour || L.seven_day || L.spend_limit));
  let body = '';
  if (hasPct){
    if (L.five_hour) body += g(tx('usage.session5h'), L.five_hour, esc(t('usage.resetsIn', {time: until(L.five_hour.resets_at)}) + ago));
    if (L.seven_day) body += g(tx('usage.week'), L.seven_day, tx('usage.resetsAt', {when: when(L.seven_day.resets_at)}));
    const sp = L.spend_limit;
    if (sp) body += g(tx('usage.spend') + (sp.period ? ' · ' + esc(sp.period) : ''), sp,
      sp.used_usd != null && sp.limit_usd != null ? `$${(+sp.used_usd).toFixed(0)} / $${(+sp.limit_usd).toFixed(0)}` : (sp.resets_at ? tx('usage.resetsIn', {time: until(sp.resets_at)}) : ''));
    body = `<div class="gauges">${body}</div>`;
  }
  if (u){
    const card = (label, w) => `<div class="ucard" title="${tx('usage.breakdown', {input: fmtTok(w.input), output: fmtTok(w.output), cacheWrite: fmtTok(w.cache_write), cacheRead: fmtTok(w.cache_read)})}">
      <span class="muted">${label}</span><div class="n"><b>${fmtTok(w.tokens)}</b><em>${tx('usage.tokens')}</em></div><span class="muted">${tx('usage.responses', {n: w.requests})}</span></div>`;
    const max = Math.max(1, ...u.days);
    const bars = u.days.map((v, i) => `<div class="bc" title="${tx('usage.tokensTip', {tokens: fmtTok(v)})}"><i class="${i === 6 ? 'now' : ''}" style="height:${Math.max(4, Math.round(86 * v / max))}%"></i>
      <span>${esc(I18N.weekdayNarrow(S.now - (6 - i) * 86400))}</span></div>`).join('');
    body += `<div class="usage">${card(tx('usage.last5h'), u.h5)}${card(tx('usage.last7d'), u.d7)}<div class="bars">${bars}</div></div>`;
  }
  if (!hasPct){
    body += `<div class="fn-note">${!sl.seen ? tx('usage.noData')
      : tx('usage.noPlan', {cmd: I18N.html('<span class="mono">/usage</span>')})}</div>`;
  }
  return `<div class="sec"><div class="sec-h"><b>${tx('usage.title')}</b><span class="sp"></span>${u ? `<span class="xs">${tx('usage.local')}</span>` : ''}</div>${body}</div>`;
}

// Update offer above the footer: "Update to vX ready" + "Update now" (auto) or "vX available" + "Update" (notify).
function updateBar(){
  const u = S.update;
  if (!u) return '';
  const v = {version: u.version}, busy = u.status === 'downloading' || u.status === 'installing';
  const text = u.status === 'ready' ? tx('update.ready', v) : u.status === 'downloading' ? tx('update.downloading', v)
    : u.status === 'installing' ? tx('update.installing') : tx('update.available', v);
  const btn = busy || !u.can_install ? '' : `<button class="b-join" data-act="update">${tx('update.now')}</button>`;
  return `<div class="updbar"><span class="ui">⬆</span><span class="ut">${text}</span>${btn}</div>`;
}

function vExpanded(){
  const md = mod('media') && S.media, L = S.limits, sy = S.system || {}, au = S.audio;
  const sess = S.sessions.slice(0, 4);
  let h = '<div class="card">';
  // media
  if (md){
    h += `<div class="sec" data-wheel="vol"><div class="media">${art('art')}<div class="mi">
      <div class="title">${md.title ? esc(md.title) : tx('media.nowPlaying')}</div>
      <div class="muted sm" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(md.artist)}${md.app ? ' · ' + esc(md.app) : ''}</div>
      ${md.duration ? `<div class="prog" data-act="seek"><i data-live="pg"></i></div>
        <div class="times"><span data-live="pt"></span><span>${mmss(md.duration)}</span></div>` : ''}
      </div></div>
      <div class="ctl"><span class="k" data-act="media" data-arg="prev">⏮</span>
        <span class="k" data-act="media" data-arg="toggle">${md.playing ? '⏸' : '▶'}</span>
        <span class="k" data-act="media" data-arg="next">⏭</span><span class="sp"></span>
        ${au ? `<div class="vol"><span class="k" data-act="mute" style="font-size:14px">${au.muted ? '🔇' : '🔊'}</span>
          <input type="range" min="0" max="100" data-live="vol" value="${Math.round((au.volume||0)*100)}"></div>` : ''}
      </div></div>`;
  }
  // meeting (Microsoft 365)
  if (mod('calendar') && S.meeting){
    const m = S.meeting, hm = ts => I18N.time(ts);
    const left = m.start - S.now;
    const whenTxt = m.in_progress ? t('meeting.inProgress', {time: hm(m.end)})
      : left < 3600 ? t('meeting.inMinutes', {n: Math.max(1, Math.round(left / 60))}) : t('meeting.at', {time: hm(m.start)});
    const sub = [whenTxt, m.provider, m.location].filter(Boolean).map(esc).join(' · ');
    h += `<div class="sec"><div class="sec-h"><b>${tx('meeting.title')}</b></div><div class="meet ${m.in_progress ? 'live' : (left < 300 ? 'soon' : '')}">
      <div class="mt"><b>${hm(m.start)}</b><span>${hm(m.end)}</span></div>
      <div class="mi2"><div class="mn">${m.title ? esc(m.title) : tx('meeting.untitled')}</div><div class="muted sm">${sub}</div></div>
      ${m.join_url ? `<button class="b-join" data-act="join">${tx('meeting.join')}</button>` : ''}</div></div>`;
  }
  // Azure Data Factory: latest run of the chosen pipelines
  if (mod('adf') && S.adf){
    h += `<div class="sec"><div class="sec-h"><b>${tx('adf.title')}</b></div>`;
    for (const r of S.adf){
      const [dot, label] = ADF_STATUS[r.status] || ['idle', 'adf.none'];
      const at = r.end || r.start;
      h += `<div class="sess" title="${esc(r.message)}"><span class="dot ${dot}"></span><span class="p">${esc(r.pipeline)}</span>
        <span class="a">${tx(label)}${at ? ' · ' + esc(when(at)) : ''}</span></div>`;
    }
    h += '</div>';
  }
  // SQL Server / Azure SQL widgets: first value of a read-only query, green/amber/red
  if (mod('sql') && S.sql){
    h += `<div class="sec"><div class="sec-h"><b>${tx('sql.title')}</b></div>`;
    for (const w of S.sql){
      const v = w.value === null ? '—' : typeof w.value === 'number' ? I18N.number(w.value, 2) : String(w.value);
      h += `<div class="sess" title="${esc(w.error)}"><span class="dot ${SQL_DOT[w.level] || 'idle'}"></span><span class="p">${esc(w.name)}</span>
        <span class="a">${w.error ? tx('sql.error') : esc(v)}</span></div>`;
    }
    h += '</div>';
  }
  // agents
  if (['claude', 'codex', 'gemini', 'copilot'].some(mod)){
    h += `<div class="sec"><div class="sec-h"><b>${tx('agents.title')}</b><span class="sp"></span>${sess.length ? '' : `<span>${tx('agents.none')}</span>`}</div>`;
    for (const s of sess){
      const tk = s.tasks;
      h += `<div class="sess ${s.has_window ? 'click' : ''}" ${s.has_window ? `data-act="focus" data-arg="${esc(s.sid)}" title="${tx('agents.focusTip')}"` : ''}>
        <span class="dot ${s.status}"></span>${glyph(s.agent)}<span class="p">${esc(s.project || AGENT[s.agent])}</span>
        <span class="a">${esc(tk && tk.current && s.status === 'working' ? tk.current : (s.action || s.model || ''))}</span>
        ${tk ? `<span class="chip on">☑ ${tk.done}/${tk.total}</span>` : ''}
        ${s.context_pct != null ? `<span class="chip" style="color:${s.context_pct >= 80 ? 'var(--amber)' : ''}">${tx('agents.context', {pct: Math.round(s.context_pct)})}</span>` : ''}</div>`;
    }
    h += '</div>';
  }
  h += claudeBlock();
  // system
  const chips = [];
  (sy.mic || []).forEach(a => chips.push(`<span class="chip on"><span class="pd mic"></span> 🎙 ${esc(a)}</span>`));
  (sy.cam || []).forEach(a => chips.push(`<span class="chip on"><span class="pd cam"></span> 📷 ${esc(a)}</span>`));
  if (sy.battery) chips.push(`<span class="chip on">${sy.battery.plugged ? '⚡' : '🔋'} ${sy.battery.percent}%</span>`);
  const devs = [];
  (sy.bluetooth || []).forEach(d => devs.push(`<span title="${esc(d.name)}" class="chip on dev ${d.battery <= 15 ? 'low' : ''}"><span class="di">${BT_ICON[d.kind] || '🔹'}</span><span class="dn">${esc(d.name.replace(/\s*Bluetooth\s*/i,' ').trim())}</span>
    <span class="bt"><i style="width:${d.battery}%;background:${d.battery <= 15 ? 'var(--red)' : d.battery <= 30 ? 'var(--amber)' : 'var(--green)'}"></i></span><b>${d.battery}%</b></span>`));
  if (chips.length || devs.length) h += `<div class="sec"><div class="sec-h"><b>${tx('system.title')}</b></div>${chips.length ? `<div class="chips">${chips.join('')}</div>` : ''}${devs.length ? `<div class="devs">${devs.join('')}</div>` : ''}</div>`;
  // timer
  if (mod('timer')){
    const tm = S.timer;
    h += `<div class="sec"><div class="sec-h"><b>${tx('timer.title')}</b>${tm ? `<span class="muted">· ${esc(tm.label)}${tm.mode === 'pomodoro' ? ' #' + tm.cycle : ''}</span>` : ''}</div>`;
    h += tm ? `<div class="timer">${ring(100*(1 - tm.left/tm.duration), 26, tm.phase === 'focus' || tm.mode === 'timer' ? 'var(--accent)' : 'var(--green)')}
          <span class="big" data-live="tm">${mmss(tm.left)}</span><span class="sp"></span>
          <span class="chip act" data-act="tpause">${tm.paused ? '▶ ' + tx('timer.resume') : '⏸ ' + tx('timer.pause')}</span><span class="chip act" data-act="tstop">✕ ${tx('timer.stop')}</span></div>`
       : `<div class="chips">${[5, 15, 25, 45].map(m => `<span class="chip act" data-act="timer" data-arg="${m}">${tx('timer.minutes', {n: m})}</span>`).join('')}
          <span class="chip act" data-act="pomo">🍅 ${tx('timer.pomodoro')}</span></div>`;
    h += '</div>';
  }
  // shelf
  if (mod('shelf')){
    const it = S.shelf || [];
    h += `<div class="sec"><div class="sec-h"><b>${tx('shelf.title')}</b><span class="sp"></span>
      ${it.length ? `<span class="link" data-act="shelf-copyall">${tx('shelf.copyAll')}</span><span class="link" data-act="shelf-clear">${tx('shelf.clear')}</span>` : ''}</div>`;
    if (!it.length) h += `<div class="muted xs">${tx('shelf.empty')}</div>`;
    it.forEach((f, i) => {
      h += `<div class="file" title="${esc(f.path)}"><span class="fi">${f.ext === 'dir' ? '📁' : esc((f.ext || '?').slice(0, 4))}</span>
        <span class="fn ${f.exists ? '' : 'gone'}">${esc(f.name)}</span><span class="fa">
        ${f.exists ? `<span data-act="shelf-copy" data-arg="${i}">${tx('shelf.copy')}</span><span data-act="shelf-open" data-arg="${i}">${tx('shelf.open')}</span><span data-act="shelf-reveal" data-arg="${i}">${tx('shelf.folder')}</span>` : ''}
        <span data-act="shelf-remove" data-arg="${i}">✕</span></span></div>`;
    });
    h += '</div>';
  }
  h += updateBar();
  h += `<div class="foot"><span>Skerry ${esc(S.version)}</span>
    <span class="sp"></span><span class="link" data-act="settings">⚙ ${tx('foot.settings')}</span></div></div>`;
  const u = S.update;
  const key = 'x' + JSON.stringify([md && [md.title, md.artist, md.playing, md.duration, thumbId, !!au, au && au.muted],
    sess.map(s => [s.sid, s.status, s.action, s.tasks, s.context_pct, s.has_window]), L, S.statusline && S.statusline.seen, S.usage && [S.usage.h5, S.usage.d7, S.usage.days],
    Math.floor(S.now/30), sy, S.adf, S.sql, S.timer && [S.timer.label, S.timer.paused, S.timer.cycle], S.shelf, u && [u.status, u.version]]);
  return {w:480, r:28, key, html:h};
}

// ---------------- guided setup (first run) ----------------
const EDGE_KEYS = {top: 'look.top', bottom: 'look.bottom', left: 'look.left', right: 'look.right'};
const hotkeyLabel = hk => String(hk || '').split('+').map(p => p.length > 1 ? p[0].toUpperCase() + p.slice(1) : p.toUpperCase()).join('+');
function vOnboarding(){
  const o = S.onboarding, step = onbStep;
  const opt = (on, act, arg, label) => `<button class="opt ${on ? 'on' : ''}" data-act="${act}" data-arg="${esc(arg)}">${label}</button>`;
  let body = '';
  if (step === 0){
    const edges = Object.entries(EDGE_KEYS).map(([e, k]) => opt(S.settings.edge === e, 'onb-edge', e, tx(k))).join('');
    const mon = S.settings.monitor || '';
    const screens = o.monitors.length > 1 ? `<div class="olabel">${tx('onb.screen')}</div><div class="opts">${o.monitors.map(m =>
      opt(mon === m.value, 'onb-mon', m.value, tx('onb.screenN', {n: m.index, w: m.width, h: m.height}) + (m.primary ? ` · ${tx('onb.primary')}` : ''))).join('')}${
      opt(mon === 'mouse', 'onb-mon', 'mouse', tx('onb.mouse'))}</div>` : '';
    body = `<div class="otitle">${tx('onb.s1.title')}</div><div class="muted sm">${tx('onb.s1.text')}</div><div class="opts">${edges}</div>${screens}`;
  } else if (step === 1){
    const row = (agent, name, st) => `<div class="oagent">${glyph(agent)}<b>${name}</b><span class="sp"></span>${
      st.installed ? `<span class="chip on">✓ ${tx('status.connected')}</span>`
      : st.available === false ? `<span class="muted sm">${tx('onb.notFound')}</span>`
      : `<button class="b-join" data-act="onb-connect" data-arg="${agent}">${tx('btn.connect')}</button>`}</div>`;
    body = `<div class="otitle">${tx('onb.s2.title')}</div><div class="muted sm">${tx('onb.s2.text')}</div>
      ${row('claude', 'Claude Code', o.claude)}${o.codex.available ? row('codex', 'Codex', o.codex) : ''}
      ${o.codex.available && o.codex.installed ? `<div class="muted xs">${tx('onb.codexHint')}</div>` : ''}`;
  } else {
    body = `<div class="otitle">${tx('onb.s3.title')}</div><ul class="otips">
      ${o.hotkey ? `<li>${tx('onb.tip.hotkey', {hotkey: I18N.html(`<kbd>${esc(hotkeyLabel(o.hotkey))}</kbd>`)})}</li>` : ''}
      <li>${tx('onb.tip.click')}</li><li>${tx('onb.tip.settings')}</li></ul>`;
  }
  const dots = [0, 1, 2].map(i => `<i class="${i === step ? 'on' : ''}"></i>`).join('');
  const left = step < 2 ? `<span class="link" data-act="onb-skip">${tx('onb.skip')}</span>` : '';
  const back = step > 0 ? `<button class="b-ghost" data-act="onb-back">${tx('onb.back')}</button>` : '';
  const next = step < 2 ? `<button class="b-join" data-act="onb-next">${tx('onb.next')}</button>`
                        : `<button class="b-join" data-act="onb-done">${tx('onb.start')}</button>`;
  return {w: 460, r: 26, key: 'onb' + step + JSON.stringify([o, S.settings.edge, S.settings.monitor]), html: `<div class="card onb">
    <div class="hd">${glyph('claude')}<b>Skerry</b><span class="muted">· ${tx('onb.step', {n: step + 1})}</span><span class="sp"></span><span class="odots">${dots}</span></div>
    ${body}<div class="ofoot">${left}<span class="sp"></span>${back}${next}</div></div>`};
}

// ---------------- view choice and rendering ----------------
const K = (kind, v) => (v.kind = kind, v);
function pick(){
  if (S.pending.length) return K('perm', vPermission());
  if (S.alerts.length){ const a = S.alerts[S.alerts.length - 1]; return K('al' + a.id, vAlert(a)); }
  if (S.onboarding) return K('onb', vOnboarding());
  if (dropping && mod('shelf')) return K('drop', vDrop());
  if (expanded) return K('exp', vExpanded());
  const done = S.sessions.find(s => (s.status === 'done' || s.status === 'error') && S.now - s.done_at < 7 && !dismissedDone.has(s.sid + s.done_at));
  if (done) return K('done' + done.sid + done.done_at, vDone(done));
  const c = vCompact();
  return K('c-' + c.type + (vertical() ? 'v' : ''), c);
}

function live(){
  const set = (k, fn) => document.querySelectorAll(`[data-live="${k}"]`).forEach(fn);
  if (S.media){
    const p = mediaPos(S.media);
    set('pg', el => el.style.width = (S.media.duration ? 100*p/S.media.duration : 0) + '%');
    set('pt', el => el.textContent = mmss(p));
  }
  set('gr', el => el.textContent = mmss(+el.dataset.until - S.now));
  if (S.timer){ ['tm','tmb','tmc'].forEach(k => set(k, el => el.textContent = mmss(S.timer.left))); }
  if (S.audio){
    set('vol', el => { if (document.activeElement !== el) el.value = Math.round((S.audio.volume || 0)*100); });
    set('vmini', el => el.style.width = (S.audio.volume || 0)*100 + '%');
  }
}

function render(){
  if (!S) return;
  document.documentElement.dataset.theme = S.settings.theme || 'dark';
  document.documentElement.style.setProperty('--accent', S.settings.accent || '#d97757');
  view = pick();
  const key = `${S.settings.edge}|${S.settings.theme}|${I18N.lang}|${view.key}`;
  const root = document.documentElement;
  root.dataset.edge = S.settings.edge || 'top';
  root.dataset.state = S.pending.length ? 'perm' : (S.alerts.length ? 'alert' : '');
  if (key !== lastKey){
    const fresh = view.kind !== lastKind;      // entry animations only when the view really changes
    lastKey = key; lastKind = view.kind;
    $c.className = (view.auto ? 'auto ' : '') + (fresh ? 'fresh' : '');
    $c.style.width = view.auto ? '' : view.w + 'px';
    $c.innerHTML = `<div class="${fresh ? 'enter' : ''}">${view.html}</div>`;
  }
  live();
  const rect = $c.getBoundingClientRect();
  const w = view.auto ? Math.min(460, Math.max(96, Math.ceil(rect.width))) : view.w, h = Math.ceil(rect.height);
  const r = Math.min(view.r, h/2, w/2), size = `${w}x${h}x${r}`;
  document.documentElement.style.setProperty('--r', r + 'px');
  if (size !== lastSize){ lastSize = size; A().resize(w, h, r); }
}

async function tick(){
  let st;
  try { st = await A().get_state(); } catch (e) { return; }
  S = st;
  I18N.setLang(S.lang);
  if (!!S.onboarding !== onbActive){ onbActive = !!S.onboarding; onbStep = 0; expanded = false; }
  if (uiSeq === null) uiSeq = S.ui_seq;
  if (S.ui_seq !== uiSeq){ uiSeq = S.ui_seq; expanded = !expanded; }
  const m = S.media;
  if (m && m.thumb_id && m.thumb_id !== thumbId){
    thumbId = m.thumb_id; thumbSrc = await A().get_thumb(); artColor(thumbSrc); lastKey = '';
  } else if ((!m || !m.thumb_id) && thumbSrc){ thumbSrc = null; thumbId = 0; artColor(null); lastKey = ''; }
  render();
}

// ---------------- interactions ----------------
function act(name, arg, ev, el){
  const api = A();
  switch (name){
    case 'decide': grantMenu = null; return api.decide(view.pid, arg);
    case 'grant-menu': grantMenu = grantMenu ? null : view.pid; return render();
    case 'revoke': api.revoke_grant(+arg); return tick();
    case 'dismiss': api.dismiss_alert(+arg); return tick();
    case 'focus': if (view.done){ dismissedDone.add(view.done); setTimeout(tick, 50); } return api.focus_session(arg);
    case 'media': return api.media(arg);
    case 'mute': return api.toggle_mute();
    case 'seek': { const r = el.getBoundingClientRect(); return api.media_seek(S.media.duration * (ev.clientX - r.left) / r.width); }
    case 'timer': return api.timer_start(+arg);
    case 'pomo': return api.pomodoro_start();
    case 'tstop': return api.timer_stop();
    case 'tpause': return api.timer_toggle_pause();
    case 'shelf-copy': return api.shelf_copy(+arg).then(ok => ok && flash(el, t('shelf.copied')));
    case 'shelf-copyall': return api.shelf_copy_all().then(ok => ok && flash(el, t('shelf.copiedAll')));
    case 'shelf-open': return api.shelf_open(+arg);
    case 'shelf-reveal': return api.shelf_reveal(+arg);
    case 'shelf-remove': return api.shelf_remove(+arg);
    case 'shelf-clear': return api.shelf_clear();
    case 'join': return api.join_meeting();
    case 'settings': return api.open_settings();
    case 'update': return api.install_update();
    case 'onb-edge': return api.set_setting('edge', arg).then(tick);
    case 'onb-mon': return api.set_monitor(arg).then(tick);
    case 'onb-connect': el.disabled = true; return api.agent_connect(arg, true).then(tick);
    case 'onb-next': onbStep = Math.min(2, onbStep + 1); return render();
    case 'onb-back': onbStep = Math.max(0, onbStep - 1); return render();
    case 'onb-skip': case 'onb-done': return api.onboarding_finish().then(tick);
  }
}
function flash(el, text){ const old = el.textContent; el.textContent = text; setTimeout(() => el.textContent = old, 1200); }

document.addEventListener('click', e => {
  if (suppressClick || !S) return;
  const tg = e.target.closest('[data-act]');
  if (tg){ e.stopPropagation(); act(tg.dataset.act, tg.dataset.arg, e, tg); return; }
  if (e.target.closest('input')) return;
  if (S.pending.length || (view && view.kind === 'onb')) return;
  if (view && view.done){ dismissedDone.add(view.done); tick(); return; }
  expanded = !expanded; tick();
});
document.addEventListener('input', e => { if (e.target.dataset.live === 'vol') A().set_volume(e.target.value/100); });

document.addEventListener('wheel', e => {
  e.preventDefault();
  if (!S) return;
  const d = e.deltaY < 0 ? 1 : -1;
  const onMedia = e.target.closest('[data-wheel="vol"]') || (view && view.type === 'media');
  if (onMedia && S.audio){ A().volume_step(d*0.04); volFlash = Date.now(); setTimeout(tick, 60); }
  else if (view && view.type === 'agent') A().cycle_session(d);
}, {passive:false});

// drag to move the pill to another edge
document.addEventListener('mousedown', e => {
  if (e.button !== 0 || e.target.closest('button,input,[data-act]')) return;
  drag = {x: e.screenX, y: e.screenY, started: false};
});
document.addEventListener('mousemove', e => {
  if (!drag || drag.started) return;
  if (e.buttons !== 1){ drag = null; return; }
  if (Math.hypot(e.screenX - drag.x, e.screenY - drag.y) > 6){
    drag.started = true; suppressClick = true; clearTimeout(collapseTimer); A().drag_start();
  }
});
document.addEventListener('mouseup', () => { drag = null; setTimeout(() => { suppressClick = false; lastSize = ''; }, 80); });

// auto-collapse of the expanded view
document.addEventListener('mouseleave', () => {
  clearTimeout(collapseTimer);
  collapseTimer = setTimeout(() => { if (expanded && !drag){ expanded = false; tick(); } }, 1500);
});
document.addEventListener('mouseenter', () => clearTimeout(collapseTimer));

// files dropped on the pill
document.addEventListener('dragenter', e => {
  if (e.dataTransfer && [...e.dataTransfer.types].includes('Files')){ dropping = true; render(); }
});
document.addEventListener('dragover', e => {
  e.preventDefault(); clearTimeout(dropTimer);
  dropTimer = setTimeout(() => { dropping = false; render(); }, 450);
});
document.addEventListener('drop', e => { e.preventDefault(); dropping = false; expanded = true; setTimeout(tick, 250); });

window.addEventListener('pywebviewready', () => { tick(); setInterval(tick, 250); });
