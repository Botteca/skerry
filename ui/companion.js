'use strict';
// Optional animated companion: a tiny SVG face in the place of the status dot that shows the island state at a glance.
// mood() is pure and knows nothing about drawing; a style (register()) only supplies markup and CSS keyed on
// data-mood, so new styles (e.g. "puffin") plug in without touching the rest. Only transform and opacity move;
// nothing runs per frame: CSS/WAAPI animations, a blink timeout every few seconds, and all of it stops when hidden.
const Companion = (() => {
  const MOODS = ['rest', 'work', 'perm', 'happy', 'worry', 'meet', 'sleep'];
  const SLEEP_AFTER = 600;   // seconds without anything happening before the eyes doze off
  const STYLES = {};

  // What the companion should show. S = get_state() snapshot (S.now in seconds), quiet = seconds since last activity.
  function mood(S, quiet){
    const ss = S.sessions || [], now = S.now;
    if ((S.pending || []).length) return 'perm';
    if (ss.some(s => s.status === 'done' && now - s.done_at < 2)) return 'happy';
    if (ss.some(s => s.status === 'error' && now - s.done_at < 30) || (S.alerts || []).some(a => a.level === 'danger')) return 'worry';
    if (ss.some(s => s.status === 'working')) return 'work';
    const L = S.limits || {}, lim = ((S.settings || {}).alerts || {}).limits || [90];
    const near = lim.length ? Math.max(...lim) : 90;
    if (['five_hour', 'seven_day'].some(k => L[k] && L[k].used_percentage >= near)) return 'worry';
    const m = S.meeting;
    if (m && !m.in_progress && m.start > now && m.start - now <= 300) return 'meet';
    return quiet > SLEEP_AFTER ? 'sleep' : 'rest';
  }

  // Style chosen in settings, or null when the classic dot ('dot') or nothing ('off') is wanted.
  function style(S){
    const c = (S.settings || {}).companion || {};
    return STYLES[c.style] ? c.style : null;
  }

  // {svg, css}: svg is drawn in a w x h box; css is scoped with .cmp[data-style=<name>].
  function register(name, def){ STYLES[name] = def; }

  // ---------------- live element ----------------
  const BASE_CSS = `
.cmp{display:inline-flex;flex:none;align-items:center;justify-content:center;line-height:0;
  --e-acc:var(--accent);--e-perm:var(--amber);--e-happy:var(--green);--e-worry:var(--red);--e-sleep:var(--muted)}
:root[data-theme=light] .cmp{--e-acc:color-mix(in srgb,var(--accent) 70%,#000);--e-perm:#a65300;--e-happy:#1b7a32;--e-worry:#c4271d}
.cmp svg{display:block;overflow:visible}
.cmp svg *{transform-box:fill-box;transform-origin:center}
.cmp[data-paused] *{animation-play-state:paused!important}
@media (prefers-reduced-motion:reduce){.cmp *{animation:none!important}}`;
  let el = null, cur = '', energy = 'lively', paused = false, timer = 0, plan = '', label = '';
  let quietSince = Date.now() / 1000, pointer = null, raf = 0;
  const reduced = () => !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);

  function create(name){
    if (!document.getElementById('cmp-css')){
      const tag = document.createElement('style'); tag.id = 'cmp-css';
      tag.textContent = BASE_CSS + Object.values(STYLES).map(s => s.css).join('\n');
      document.head.appendChild(tag);
    }
    const e = document.createElement('span');
    e.className = 'cmp'; e.dataset.style = name; e.dataset.mood = 'rest'; e.setAttribute('role', 'img');
    e.style.width = STYLES[name].w + 'px'; e.style.height = STYLES[name].h + 'px';
    e.innerHTML = STYLES[name].svg;
    return e;
  }

  // Freeze what is on screen, switch mood, then let the CSS transitions run from there (no jump out of an animation).
  function setMood(m){
    if (m === cur) return;
    const parts = [...el.querySelectorAll('svg *:not(.look)')];   // .look belongs to the pointer
    el.getAnimations({subtree: true}).forEach(a => { if (!(a instanceof CSSAnimation)) a.cancel(); });   // blink, glance
    parts.forEach(n => { const cs = getComputedStyle(n); n.style.transform = cs.transform; n.style.opacity = cs.opacity; });
    el.dataset.mood = cur = m;
    void el.getBoundingClientRect();
    parts.forEach(n => { n.style.transform = ''; n.style.opacity = ''; });
  }

  // Blink every few seconds (and now and then look aside) while idle-ish; nothing scheduled when hidden or reduced.
  function schedule(){
    const want = !paused && !reduced() && ['rest', 'work', 'meet'].includes(cur) ? `${cur}|${energy}` : '';
    if (want === plan) return;
    plan = want; clearTimeout(timer); timer = 0;
    if (!want) return;
    const [a, b] = energy === 'calm' ? [5, 9] : [4, 7];
    const next = () => { timer = setTimeout(() => {
      const s = STYLES[el.dataset.style];
      s.blink && s.blink(el);
      if (cur === 'rest' && s.glance && Math.random() < (energy === 'calm' ? 0.1 : 0.3)) s.glance(el, Math.random() < 0.5 ? -1 : 1);
      next();
    }, (a + Math.random() * (b - a)) * 1000); };
    next();
  }

  // Called after every render: mount the face in .cslot (if the view has one) and bring it to the current mood.
  // visible = the window is shown; text = accessible label of the mood.
  function render(root, S, visible, text){
    const name = style(S);
    if (!name){ if (el){ el.remove(); el = null; cur = ''; schedule(); } return; }
    if (!el || el.dataset.style !== name){ el && el.remove(); el = create(name); cur = 'rest'; }
    energy = ((S.settings || {}).companion || {}).energy === 'calm' ? 'calm' : 'lively';
    el.dataset.energy = energy;
    const slot = root.querySelector('.cslot');
    if (slot && el.parentNode !== slot){ slot.appendChild(el); void el.getBoundingClientRect(); }
    paused = !visible || document.visibilityState === 'hidden' || !el.isConnected;   // no slot in this view = parked
    el.toggleAttribute('data-paused', paused);
    const m = mood(S, S.now - quietSince);
    if (m !== 'rest' && m !== 'sleep') quietSince = S.now;
    setMood(m);
    if (text !== label){ label = text; el.setAttribute('aria-label', text); el.title = text; }
    schedule();
  }

  // Pupils follow the pointer while it is over the island (one transform per mouse move, no loop).
  function follow(){
    raf = 0;
    const look = el && el.isConnected && el.querySelector('.look');
    if (!look) return;
    if (!pointer){ look.style.transform = ''; return; }
    const r = el.getBoundingClientRect(), dx = pointer[0] - (r.left + r.width / 2), dy = pointer[1] - (r.top + r.height / 2);
    const d = Math.hypot(dx, dy) || 1, k = Math.min(1, d / 120), s = STYLES[el.dataset.style].reach || [2, 1.5];
    look.style.transform = `translate(${(dx / d * s[0] * k).toFixed(2)}px,${(dy / d * s[1] * k).toFixed(2)}px)`;
  }
  if (typeof document !== 'undefined'){
    document.addEventListener('mousemove', e => {
      pointer = [e.clientX, e.clientY]; quietSince = Date.now() / 1000;
      if (el && !raf) raf = requestAnimationFrame(follow);
    });
    document.addEventListener('mouseleave', () => { pointer = null; if (el && !raf) raf = requestAnimationFrame(follow); });
    document.addEventListener('visibilitychange', () => { if (el){ paused = document.visibilityState === 'hidden' || paused;
      el.toggleAttribute('data-paused', paused); schedule(); } });
  }

  // Static element in a given mood, for previews (tools/companion.html); render() manages the live one.
  function make(name, m){ const e = create(name); e.dataset.mood = m || 'rest'; return e; }
  const moodNow = S => mood(S, S.now - quietSince);
  const debug = () => ({mood: cur, paused, timer: !!timer, mounted: !!(el && el.isConnected)});
  return {MOODS, mood, moodNow, style, register, render, make, debug, styles: STYLES};
})();

// ---------------- style "eyes": two rounded eyes ----------------
Companion.register('eyes', {
  w: 24, h: 16, reach: [2.2, 1.6],
  svg: `<svg viewBox="0 0 24 16" width="24" height="16" aria-hidden="true"><g class="look"><g class="gaze">
    <g class="eye l"><rect class="ball" x="4.5" y="4" width="5" height="8" rx="2.5"/><path class="arc" d="M4.2 10 Q7 5.2 9.8 10"/></g>
    <g class="eye r"><rect class="ball" x="14.5" y="4" width="5" height="8" rx="2.5"/><path class="arc" d="M14.2 10 Q17 5.2 19.8 10"/></g>
    </g></g><circle class="ping" cx="23" cy="2.5" r="1.7"/></svg>`,
  css: `
.cmp[data-style=eyes]{color:var(--e-acc)}
.cmp[data-style=eyes] .ball{fill:currentColor}
.cmp[data-style=eyes] .arc{fill:none;stroke:currentColor;stroke-width:2.2;stroke-linecap:round;opacity:0}
.cmp[data-style=eyes] .ping{fill:var(--e-acc);opacity:0}
.cmp[data-style=eyes] .look{transition:transform .18s ease-out}
.cmp[data-style=eyes] .gaze,.cmp[data-style=eyes] .ball,.cmp[data-style=eyes] .arc,.cmp[data-style=eyes] .ping{
  transition:transform .22s cubic-bezier(.3,.7,.4,1),opacity .2s ease}
.cmp[data-style=eyes][data-mood=work] .gaze{animation:cmp-read 3.6s cubic-bezier(.45,0,.55,1) infinite}
.cmp[data-style=eyes][data-mood=work][data-energy=calm] .gaze{animation-duration:6s}
.cmp[data-style=eyes][data-mood=perm]{color:var(--e-perm)}
.cmp[data-style=eyes][data-mood=perm] .gaze{transform:translateY(2.4px)}
.cmp[data-style=eyes][data-mood=perm] .ball{transform:scale(1.22)}
.cmp[data-style=eyes][data-mood=happy]{color:var(--e-happy)}
.cmp[data-style=eyes][data-mood=happy] .ball{opacity:0;transform:scaleY(.3)}
.cmp[data-style=eyes][data-mood=happy] .arc{opacity:1}
.cmp[data-style=eyes][data-mood=worry]{color:var(--e-worry)}
.cmp[data-style=eyes][data-mood=worry] .l .ball{transform:rotate(-14deg) scaleY(.38)}
.cmp[data-style=eyes][data-mood=worry] .r .ball{transform:rotate(14deg) scaleY(.38)}
.cmp[data-style=eyes][data-mood=meet] .gaze{transform:translate(2.6px,-.8px)}
.cmp[data-style=eyes][data-mood=meet] .ping{opacity:1;animation:cmp-ping 1.6s ease-in-out infinite}
.cmp[data-style=eyes][data-mood=sleep]{color:var(--e-sleep)}
.cmp[data-style=eyes][data-mood=sleep] .gaze{transform:translateY(1.6px)}
.cmp[data-style=eyes][data-mood=sleep] .ball{transform:scaleY(.22)}
@keyframes cmp-read{0%{transform:translateX(-2.4px)}70%{transform:translateX(2.4px)}82%,100%{transform:translateX(-2.4px)}}
@keyframes cmp-ping{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.25;transform:scale(.6)}}`,
  blink(el){
    el.querySelectorAll('.eye').forEach(e => e.animate([{transform: 'scaleY(1)'}, {transform: 'scaleY(.08)'}, {transform: 'scaleY(1)'}],
      {duration: 170, easing: 'ease-in-out'}));
  },
  glance(el, dir){
    const x = `translateX(${dir * 2.6}px)`;
    el.querySelector('.gaze').animate([{transform: 'none'}, {transform: x, offset: 0.2}, {transform: x, offset: 0.75}, {transform: 'none'}],
      {duration: 1500, easing: 'ease-in-out'});
  },
});

if (typeof module !== 'undefined') module.exports = Companion;   // lets tests/test_companion.py run mood() under Node
