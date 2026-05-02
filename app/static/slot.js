/* ===== DOMヘルパ ===== */
const $  = (q)=>document.querySelector(q);
const $$ = (q)=>Array.from(document.querySelectorAll(q));

/* ===== 効果音（Web Audio API） ===== */
const audioContext = new (window.AudioContext || window.webkitAudioContext)();

// AudioContextの状態を確認して自動再開
function ensureAudioContext() {
  if (audioContext.state === 'suspended') {
    console.log('[AUDIO] AudioContext is suspended, resuming...');
    audioContext.resume().then(() => {
      console.log('[AUDIO] AudioContext resumed successfully');
    });
  }
}

// スピン開始音（上昇トーン）
function playSoundSpinStart() {
  const oscillator = audioContext.createOscillator();
  const gainNode = audioContext.createGain();
  
  oscillator.connect(gainNode);
  gainNode.connect(audioContext.destination);
  
  oscillator.type = 'sine';
  oscillator.frequency.setValueAtTime(200, audioContext.currentTime);
  oscillator.frequency.exponentialRampToValueAtTime(600, audioContext.currentTime + 0.2);
  
  gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
  gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.2);
  
  oscillator.start(audioContext.currentTime);
  oscillator.stop(audioContext.currentTime + 0.2);
}

// リール停止音（クリック音）
function playSoundReelStop() {
  const oscillator = audioContext.createOscillator();
  const gainNode = audioContext.createGain();
  
  oscillator.connect(gainNode);
  gainNode.connect(audioContext.destination);
  
  oscillator.type = 'square';
  oscillator.frequency.setValueAtTime(150, audioContext.currentTime);
  
  gainNode.gain.setValueAtTime(0.2, audioContext.currentTime);
  gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.1);
  
  oscillator.start(audioContext.currentTime);
  oscillator.stop(audioContext.currentTime + 0.1);
}

// 結果発表音（点数に応じた音）
function playSoundResult(totalScore) {
  if (totalScore >= 300) {
    // 高得点：ファンファーレ
    playFanfare();
  } else if (totalScore >= 150) {
    // 中得点：明るい音
    playCheer();
  } else {
    // 低得点：シンプルな音
    playSimple();
  }
}

function playFanfare() {
  const notes = [262, 330, 392, 523]; // C, E, G, C
  notes.forEach((freq, i) => {
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    oscillator.type = 'triangle';
    oscillator.frequency.setValueAtTime(freq, audioContext.currentTime + i * 0.15);
    
    gainNode.gain.setValueAtTime(0.3, audioContext.currentTime + i * 0.15);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + i * 0.15 + 0.3);
    
    oscillator.start(audioContext.currentTime + i * 0.15);
    oscillator.stop(audioContext.currentTime + i * 0.15 + 0.3);
  });
}

function playCheer() {
  const oscillator = audioContext.createOscillator();
  const gainNode = audioContext.createGain();
  
  oscillator.connect(gainNode);
  gainNode.connect(audioContext.destination);
  
  oscillator.type = 'sine';
  oscillator.frequency.setValueAtTime(440, audioContext.currentTime);
  oscillator.frequency.exponentialRampToValueAtTime(880, audioContext.currentTime + 0.3);
  
  gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
  gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);
  
  oscillator.start(audioContext.currentTime);
  oscillator.stop(audioContext.currentTime + 0.3);
}

function playSimple() {
  const oscillator = audioContext.createOscillator();
  const gainNode = audioContext.createGain();
  
  oscillator.connect(gainNode);
  gainNode.connect(audioContext.destination);
  
  oscillator.type = 'sine';
  oscillator.frequency.setValueAtTime(330, audioContext.currentTime);
  
  gainNode.gain.setValueAtTime(0.2, audioContext.currentTime);
  gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.2);
  
  oscillator.start(audioContext.currentTime);
  oscillator.stop(audioContext.currentTime + 0.2);
}

// リーチ演出音（BAR以上がリーチになったとき）
function playSoundReach() {
  // AudioContextの状態を確認
  if (audioContext.state === 'suspended') {
    console.log('[AUDIO] AudioContext suspended, cannot play reach sound');
    return;
  }
  console.log('[AUDIO] Playing reach sound, AudioContext state:', audioContext.state);
  
  // ドラムロール風の緊張感のある音
  const duration = 0.6;
  
  // 低音のパルス
  for (let i = 0; i < 8; i++) {
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    oscillator.type = 'triangle';
    oscillator.frequency.setValueAtTime(80 + i * 10, audioContext.currentTime + i * 0.07);
    
    gainNode.gain.setValueAtTime(0.3, audioContext.currentTime + i * 0.07);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + i * 0.07 + 0.05);
    
    oscillator.start(audioContext.currentTime + i * 0.07);
    oscillator.stop(audioContext.currentTime + i * 0.07 + 0.05);
  }
  
  // 上昇するトーン
  const oscillator2 = audioContext.createOscillator();
  const gainNode2 = audioContext.createGain();
  
  oscillator2.connect(gainNode2);
  gainNode2.connect(audioContext.destination);
  
  oscillator2.type = 'sawtooth';
  oscillator2.frequency.setValueAtTime(200, audioContext.currentTime + 0.3);
  oscillator2.frequency.exponentialRampToValueAtTime(800, audioContext.currentTime + duration);
  
  gainNode2.gain.setValueAtTime(0.4, audioContext.currentTime + 0.3);
  gainNode2.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + duration);
  
  oscillator2.start(audioContext.currentTime + 0.3);
  oscillator2.stop(audioContext.currentTime + duration);
}

// GOD揃いの特別な効果音
function playSoundGodWin() {
  // 豪華なファンファーレ
  const notes = [
    {freq: 523, time: 0.0},    // C5
    {freq: 659, time: 0.15},   // E5
    {freq: 784, time: 0.3},    // G5
    {freq: 1047, time: 0.45},  // C6
    {freq: 1319, time: 0.6},   // E6
    {freq: 1047, time: 0.75},  // C6
    {freq: 1319, time: 0.9},   // E6
    {freq: 1568, time: 1.05}   // G6
  ];
  
  notes.forEach((note) => {
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    oscillator.type = 'triangle';
    oscillator.frequency.setValueAtTime(note.freq, audioContext.currentTime + note.time);
    
    gainNode.gain.setValueAtTime(0.4, audioContext.currentTime + note.time);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + note.time + 0.4);
    
    oscillator.start(audioContext.currentTime + note.time);
    oscillator.stop(audioContext.currentTime + note.time + 0.4);
  });
}

// ７揃いの特別な効果音
function playSoundSevenWin() {
  // 華やかな上昇音
  const notes = [
    {freq: 392, time: 0.0},    // G4
    {freq: 494, time: 0.12},   // B4
    {freq: 587, time: 0.24},   // D5
    {freq: 784, time: 0.36},   // G5
    {freq: 988, time: 0.48},   // B5
    {freq: 784, time: 0.6}     // G5
  ];
  
  notes.forEach((note) => {
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    oscillator.type = 'sine';
    oscillator.frequency.setValueAtTime(note.freq, audioContext.currentTime + note.time);
    
    gainNode.gain.setValueAtTime(0.35, audioContext.currentTime + note.time);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + note.time + 0.3);
    
    oscillator.start(audioContext.currentTime + note.time);
    oscillator.stop(audioContext.currentTime + note.time + 0.3);
  });
}

// BAR揃いの特別な効果音
function playSoundBarWin() {
  // 明るい上昇音
  const notes = [
    {freq: 330, time: 0.0},    // E4
    {freq: 415, time: 0.1},    // G#4
    {freq: 523, time: 0.2},    // C5
    {freq: 659, time: 0.3},    // E5
    {freq: 523, time: 0.4}     // C5
  ];
  
  notes.forEach((note) => {
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    oscillator.type = 'square';
    oscillator.frequency.setValueAtTime(note.freq, audioContext.currentTime + note.time);
    
    gainNode.gain.setValueAtTime(0.3, audioContext.currentTime + note.time);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + note.time + 0.25);
    
    oscillator.start(audioContext.currentTime + note.time);
    oscillator.stop(audioContext.currentTime + note.time + 0.25);
  });
}


async function fetchJSON(url,opt={}){
  const hasBody = opt && typeof opt.body !== "undefined";
  const headers = Object.assign({'Content-Type':'application/json'}, (opt.headers||{}));
  const res = await fetch(url, Object.assign({headers}, opt));
  if(!res.ok){ throw new Error(await res.text()); }
  return await res.json();
}

/* ===== 設定UI（配当入力→確率は自動計算プレビュー、保存時はサーバが再計算） ===== */
function rowTemplate(s={id:"",label:"",payout_3:0,color:"#888888",prob:0}){
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td><input class="sid" type="text" value="${s.id ?? ''}"></td>
    <td><input class="label" type="text" value="${s.label ?? ''}"></td>
    <td><input class="p3" type="number" step="0.01" min="0" value="${Number(s.payout_3||0)}"></td>
    <td><input class="prob" type="number" step="0.0001" value="${Number(s.prob||0).toFixed(4)}" disabled></td>
    <td style="display:flex;align-items:center;gap:.4rem">
      <input class="color" type="color" value="${s.color || '#888888'}">
      <span class="color-swatch" style="background:${s.color || '#888888'}"></span>
    </td>
    <td style="text-align:right"><button type="button" class="sub del">削除</button></td>`;
  return tr;
}

function readRows(){
  const arr = [];
  for(const tr of $$('#rows tr')){
    const id = tr.querySelector('.sid').value.trim();
    const label = tr.querySelector('.label').value.trim() || id;
    const payout_3 = parseFloat(tr.querySelector('.p3').value||"0");
    const color = tr.querySelector('.color').value;
    if(!id) continue;
    arr.push({id, label, payout_3: isFinite(payout_3)? payout_3:0, color});
  }
  return arr;
}

/* ===== 期待値ターゲットに一致する確率分布（指数傾斜） ===== */
function solveProbsForTarget(payouts, targetE1){
  if(!payouts.length) return [];
  const vmin = Math.min(...payouts), vmax = Math.max(...payouts);

  if(!(isFinite(targetE1)) || targetE1<=0){
    const inv = payouts.map(v => v>0 ? 1/v : 0);
    const S = inv.reduce((a,b)=>a+b,0) || 1;
    return inv.map(x => x/S);
  }
  if(targetE1 <= vmin + 1e-12){
    return payouts.map(v => v===vmin ? 1 : 0);
  }
  if(targetE1 >= vmax - 1e-12){
    return payouts.map(v => v===vmax ? 1 : 0);
  }

  const E = beta => {
    const w = payouts.map(v => Math.exp(beta * v));
    const Z = w.reduce((a,b)=>a+b,0);
    const p = w.map(x => x/Z);
    return p.reduce((s,pi,i)=> s + pi * payouts[i], 0);
  };

  let lo = -1, hi = 1;
  for(let i=0;i<60;i++){
    const elo = E(lo), ehi = E(hi);
    if(elo > targetE1){ lo *= 2; continue; }
    if(ehi < targetE1){ hi *= 2; continue; }
    break;
  }
  for(let i=0;i<80;i++){
    const mid = (lo+hi)/2;
    const em = E(mid);
    if(em < targetE1) lo = mid; else hi = mid;
  }
  const beta = (lo+hi)/2;
  const w = payouts.map(v => Math.exp(beta * v));
  const Z = w.reduce((a,b)=>a+b,0);
  return w.map(x => x/Z);
}

/* ===== 配当表レンダリング（図柄と配当のみ・配当降順） ===== */
function renderPayoutTableFromRows(){
  const rows  = readRows();
  const tbody = $('#payout-rows');
  if(!tbody) return;

  tbody.innerHTML = '';

  // 配当が大きい順に並べ替えて描画（配当0のシンボルは除外）
  const sorted = [...rows]
    .filter(r => (r.payout_3 || 0) > 0)  // 配当0のシンボルを除外
    .sort((a,b)=>(b.payout_3||0)-(a.payout_3||0));

  sorted.forEach((r)=>{
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="badge" style="background:${r.color || '#4f46e5'}">${r.label || r.id}</span></td>
      <td style="text-align:right">${Number(r.payout_3 || 0)}</td>
    `;
    tbody.appendChild(tr);
  });
}

/* ===== 配当表をwindow.__symbolsから直接描画 ===== */
function renderPayoutTableFromSymbols(){
  const tbody = $('#payout-rows');
  if(!tbody) return;
  if(!window.__symbols || !window.__symbols.length) return;

  tbody.innerHTML = '';

  // 配当が大きい順に並べ替えて描画（配当0のシンボルと不使用シンボルを除外）
  const sorted = [...window.__symbols]
    .filter(s => (s.payout_3 || 0) > 0 && s.is_disabled !== true)  // 配当0のシンボルと不使用シンボルを除外
    .sort((a,b)=>(b.payout_3||0)-(a.payout_3||0));

  sorted.forEach((r)=>{
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="badge" style="background:${r.color || '#4f46e5'}">${r.label || r.id}</span></td>
      <td style="text-align:right">${Number(r.payout_3 || 0)}</td>
    `;
    tbody.appendChild(tr);
  });
}

/* ===== プレビュー再計算（期待値>0は指数傾斜、0は反比例） ===== */
function previewRecalcProb(){
  const expected5 = parseFloat($('#expected-total-5')?.value||"0");
  const rows = readRows();
  const payouts = rows.map(r => Math.max(0, +r.payout_3));

  let probs1 = [];
  if(expected5 > 0){
    const targetE1 = expected5 / 5.0;
    probs1 = solveProbsForTarget(payouts, targetE1);
  }else{
    const inv = payouts.map(v => v>0 ? 1/v : 0);
    const S = inv.reduce((a,b)=>a+b,0) || 1;
    probs1 = inv.map(x => x/S);
  }

  const trs = $$('#rows tr');
  let sum = 0;
  probs1.forEach((p,i)=>{
    const pct = p*100;
    sum += pct;
    if(trs[i]) trs[i].querySelector('.prob').value = pct.toFixed(4);
  });
  $('#prob-total').textContent = sum.toFixed(4);
  $('#prob-warn').style.display = (Math.abs(sum-100) > 0.05) ? 'inline' : 'none';

  // 設定ダイアログが存在する場合のみ呼び出し
  if ($('#rows')) {
    renderPayoutTableFromRows();
  } else {
    renderPayoutTableFromSymbols();
  }
}

async function loadConfig(){
  try {
    const storeSlug = window.location.pathname.split('/')[4];
    const cfg = await fetchJSON(`/apps/survey/store/${storeSlug}/config`);
    console.log('[loadConfig] cfg.symbols:', cfg.symbols);
    window.__symbols = cfg.symbols;
    console.log('[loadConfig] window.__symbols set:', window.__symbols);
    const lemon = window.__symbols.find(s => s.id === 'lemon');
    console.log('[loadConfig] lemon symbol:', lemon);
    
    // 設定ダイアログが存在する場合のみ更新
    const rowsEl = $('#rows');
    if (rowsEl) {
      rowsEl.innerHTML = '';
      (cfg.symbols || []).forEach(s => rowsEl.appendChild(rowTemplate(s)));
    }
    
    if($('#expected-total-5')) $('#expected-total-5').value = cfg.expected_total_5 ?? 2500;
    bindRowEvents();
    buildAllReels(cfg.symbols);
    renderPayoutTableFromSymbols(); // 配当表を描画
    previewRecalcProb();
  } catch (e) {
    console.error('Failed to load config:', e);
    alert('設定の読み込みに失敗しました: ' + e.message);
    throw e;
  }
}

function bindRowEvents(){
  $$('#rows .del').forEach(btn=>btn.onclick=(e)=>{ e.target.closest('tr').remove(); previewRecalcProb(); });
  $$('#rows .color').forEach(inp=>inp.oninput=(e)=>{ e.target.closest('td').querySelector('.color-swatch').style.background = e.target.value; });
  $$('#rows .p3, #rows .sid, #rows .label').forEach(inp=> inp.oninput = previewRecalcProb);

  const exp = $('#expected-total-5');
  if(exp) exp.addEventListener('input', previewRecalcProb);
}

async function saveConfig(){
  const storeSlug = window.location.pathname.split('/')[4];
  const adminEl = $('#admin-token');
  const adminToken = adminEl ? (adminEl.value || '').trim() : '';

  const symbols = readRows();
  if(symbols.length === 0){ alert('行がありません'); return; }

  const body = {
    target_expected_total_5: parseFloat($('#expected-total-5')?.value||"0") || undefined,
    symbols,
    reels: 3,
    base_bet: 1
  };

  const headers = {'Content-Type':'application/json'};
  if(adminToken) headers['X-Admin-Token'] = adminToken;

  await fetchJSON(`/apps/survey/store/${storeSlug}/config`, { method:'POST', headers, body: JSON.stringify(body) });
  await loadConfig();
  alert('保存しました（確率を再計算して保存）');
}

/* ===== リール見た目生成 ===== */
const STRIP_REPEAT = 8;
const CELL_H = (() => {
  const v = getComputedStyle(document.documentElement).getPropertyValue('--cell-h') || '120px';
  const n = parseInt(String(v).replace('px','').trim(), 10);
  return Number.isFinite(n) ? n : 120;
})();

function buildStripHTML(symbols){
  const html = [];
  for(let r=0;r<STRIP_REPEAT;r++){
    for(const s of symbols){
      html.push(`<div class="cell" style="color:${s.color || '#fff'}">${s.label}</div>`);
    }
  }
  return html.join('');
}

function buildAllReels(symbols){
  $$('#reels .reel').forEach((reel)=>{
    const strip = reel.querySelector('.strip');
    strip.innerHTML = buildStripHTML(symbols);
    strip.style.transition = 'none';
    strip.style.transform = 'translateY(0)';
    strip.style.animation = 'none';
  });
}

/* ===== スピン演出（上→下に回る；CSSの@keyframes scroll 使用） ===== */
let spinning = false;

function startSpinVisual(){
  $$('#reels .reel').forEach((reel, i)=>{
    const strip = reel.querySelector('.strip');
    strip.style.transition = 'none';
    strip.style.transform = 'translateY(0)';
    const speed = 0.45 + i * 0.07;
    strip.style.animation = `scroll ${speed}s linear infinite`;
  });
}

function stopReelVisual(reelIndex, targetSymbolId){
  const reel = $(`#reels .reel[data-reel="${reelIndex}"]`);
  const strip = reel.querySelector('.strip');
  strip.style.animation = 'none';

  const order = (window.__symbols || []).map(s=>s.id);
  const oneLoopLen = order.length * STRIP_REPEAT;
  const baseIndex  = order.length * (STRIP_REPEAT - 2);
  const within     = Math.max(0, order.indexOf(targetSymbolId));
  const targetIndex = Math.min(oneLoopLen - 1, baseIndex + within);

  requestAnimationFrame(()=>{
    strip.style.transition = 'transform 620ms cubic-bezier(.18,.8,.2,1)';
    strip.style.transform  = `translateY(-${targetIndex * CELL_H}px)`;
  });
}

/* ===== 5回分のスピンを順番に再生 ===== */
async function animateFiveSpins(spins){
  $('#status').textContent = 'SPIN...';
  $('#round-indicator').textContent = '';

  let total = 0;
  for(let i=0;i<spins.length;i++){
    const one = spins[i];

    startSpinVisual();
    playSoundSpinStart(); // スピン開始音
    await new Promise(r=>setTimeout(r, 500));
    
    // 各リールを個別に停止
    stopReelVisual(0, one.reels[0].id);
    playSoundReelStop(); // リール停止音
    await new Promise(r=>setTimeout(r, 420));
    stopReelVisual(1, one.reels[1].id);
    playSoundReelStop(); // リール停止音
    
    // リーチ判定（リーチハズレまたは高価値シンボルの当たり）
    const highValueSymbols = ['bar', 'seven', 'god'];
    const isReach = one.is_reach === true || (one.matched === true && highValueSymbols.includes(one.reels[0].id));
    
    console.log(`[REACH DEBUG] Round ${i+1}: is_reach=${one.is_reach}, matched=${one.matched}, reels[0]=${one.reels[0].id}, reels[1]=${one.reels[1].id}, isReach=${isReach}`);
    
    if (isReach) {
      console.log(`[REACH DEBUG] Playing reach sound for ${one.reels[0].id}`);
      playSoundReach(); // リーチ演出音
      await new Promise(r=>setTimeout(r, 600)); // リーチ演出の時間
    } else {
      await new Promise(r=>setTimeout(r, 420));
    }
    stopReelVisual(2, one.reels[2].id);
    playSoundReelStop(); // リール停止音
    
    // リーチ時は最終リール停止後の待機時間を長くする
    if (isReach) {
      await new Promise(r=>setTimeout(r, 1500)); // リーチ時は1.5秒
    } else {
      await new Promise(r=>setTimeout(r, 700)); // 通常は0.7秒
    }

    total += one.payout;
    
    // 結果表示と特別な効果音
    if (one.matched) {
      $('#round-indicator').textContent = `Round ${i+1}/5：${one.symbol.label} 揃った！ (+${one.payout})`;
      
      // BAR以上が揃ったときの特別な効果音
      if (one.symbol.id === 'GOD') {
        playSoundGodWin();
      } else if (one.symbol.id === 'seven') {
        playSoundBarWin();
      } else if (one.symbol.id === 'bar') {
        playSoundSevenWin();
      }
    } else if (one.is_reach) {
      // リーチだけど揃わなかった
      const reachLabel = one.reach_symbol ? one.reach_symbol.label : one.reels[0].label;
      $('#round-indicator').textContent = `Round ${i+1}/5：${reachLabel} リーチ！ (+0)`;
    } else {
      $('#round-indicator').textContent = `Round ${i+1}/5：ハズレ (+0)`;
    }
  }
  return total;
}

/* ===== メイン操作 ===== */
// セット数管理
let currentSet = 0;
let maxSets = window.MAX_PLAY_SETS || 1;
let setScores = [];

// ボタン表示を更新
function updateSpinButton() {
  const btn = $('#btn-spin');
  if (!btn) return;
  
  if (currentSet >= maxSets) {
    btn.textContent = 'プレイ終了';
    btn.disabled = true;
    btn.style.opacity = '0.5';
    btn.style.cursor = 'not-allowed';
  } else {
    btn.textContent = `5回スピン (セット${currentSet + 1}/${maxSets})`;
    btn.disabled = false;
    btn.style.opacity = '1';
    btn.style.cursor = 'pointer';
  }
}

async function play(){
  if(spinning) return;
  
  // セット数制限チェック
  if (currentSet >= maxSets) {
    alert(`プレイ可能回数に達しました（${maxSets}セット）`);
    return;
  }
  
  spinning = true;
  
  // AudioContextを再開（ブラウザのAutoplay Policy対策）
  ensureAudioContext();

  let data;
  try{
    const storeSlug = window.location.pathname.split('/')[4];
    data = await fetchJSON(`/apps/survey/store/${storeSlug}/spin`, { method:'POST', body: JSON.stringify({}) });
  }catch(e){
    $('#status').textContent = 'エラー: ' + (e.message || e);
    spinning = false;
    return;
  }

  const total = await animateFiveSpins(data.spins);

  // セット番号を更新
  currentSet++;
  setScores.push(total);
  
  // ステータス表示を更新
  const totalScore = setScores.reduce((a, b) => a + b, 0);
  $('#status').textContent = `セット${currentSet}/${maxSets} 合計: ${total} (総計: ${totalScore})`;
  playSoundResult(total); // 結果発表音
  
  // 景品判定と表示
  if (data.prize) {
    const prizeMsg = document.querySelector('.survey-complete-message p');
    if (prizeMsg) {
      prizeMsg.innerHTML = `🎉 おめでとうございます！${data.prize.rank}が当たりました！！<br>景品: ${data.prize.name}`;
    }
  }
  const li = document.createElement('li');
  const ts = new Date(data.ts*1000).toLocaleString();
  
  // 各スピンの結果を表示
  const spinResults = data.spins.map(s => {
    if (s.matched) {
      return `<span class="badge" style="background:${s.symbol.color || '#4f46e5'}">${s.symbol.label}</span>`;
    } else {
      return `<span class="badge" style="background:#999">ハズレ</span>`;
    }
  }).join(' ');
  
  li.innerHTML = `[セット${currentSet}] ` + spinResults + ` <span class="muted">${ts}</span> / 合計: ${total}`;
  $('#history').insertBefore(li, $('#history').firstChild);

  // 設定ダイアログが存在する場合のみ呼び出し
  if ($('#rows')) {
    renderPayoutTableFromRows();
  } else {
    renderPayoutTableFromSymbols();
  }
  
  // ボタン表示を更新
  updateSpinButton();
  
  // 全セット完了時に結果ページにリダイレクト
  if (currentSet >= maxSets) {
    // 履歴を収集
    const historyItems = Array.from($('#history').children).reverse().map(li => li.textContent.trim());
    
    // 結果をセッションに保存するためにサーバーに送信
    try {
      const storeSlug = window.location.pathname.split('/')[4];
      await fetchJSON(`/apps/survey/store/${storeSlug}/slot/save_result`, {
        method: 'POST',
        body: JSON.stringify({
          total_score: totalScore,
          prize: data.prize || null,
          history: historyItems,
          set_scores: setScores
        })
      });
      
      // 結果ページにリダイレクト
      setTimeout(() => {
        window.location.href = `/apps/survey/store/${storeSlug}/slot/result`;
      }, 1500); // 1.5秒後にリダイレクト（結果を見せるため）
    } catch (e) {
      console.error('結果保存エラー:', e);
    }
  }
  
  spinning = false;
}

/* ===== 初期化 ===== */
document.addEventListener('DOMContentLoaded', ()=>{
  // 設定ダイアログ
  $('#btn-open')?.addEventListener('click', ()=>$('#dlg').showModal());
  $('#btn-cancel')?.addEventListener('click', ()=>$('#dlg').close());
  $('#add')?.addEventListener('click', ()=>{
    $('#rows').appendChild(rowTemplate());
    bindRowEvents();
    previewRecalcProb();
  });
  $('#btn-save')?.addEventListener('click', async (e)=>{
    e.preventDefault();
    await saveConfig();
    $('#dlg').close();
  });

  // n以上〜n'以下の確率計算ツール（存在する場合だけバインド）
  $('#btn-calc-prob')?.addEventListener('click', async ()=>{
    const minStr = $('#threshold-min')?.value ?? '';
    const maxStr = $('#threshold-max')?.value ?? '';
    const tmin = minStr.trim()==='' ? 0 : parseFloat(minStr);
    const tmax = maxStr.trim()==='' ? null : parseFloat(maxStr);

    const payload = { spins: 5, threshold_min: tmin };
    if(tmax !== null && Number.isFinite(tmax)) payload.threshold_max = tmax;

    try{
      const storeSlug = window.location.pathname.split('/')[4];
      const j = await fetchJSON(`/apps/survey/store/${storeSlug}/calc_prob`, { method:'POST', body: JSON.stringify(payload) });
      const el = $('#prob-result');
      if(!el) return;
      if('prob_range' in j && tmax !== null){
        el.textContent = `5回合計が ${tmin} 以上 ${tmax} 以下になる確率： ${(j.prob_range*100).toFixed(2)} %`;
      }else{
        el.textContent = `5回合計が ${tmin} 以上になる確率： ${(j.prob_ge*100).toFixed(2)} %`;
      }
    }catch(e){
      const el = $('#prob-result');
      if(el) el.textContent = `計算エラー: ${e.message || e}`;
    }
  });

  // プレイ
  $('#btn-spin')?.addEventListener('click', ()=>play());

  // アンケートリセット
  $('#btn-reset-survey')?.addEventListener('click', async ()=>{
    if(confirm('アンケートをリセットして最初からやり直しますか？')){
      try{
        const storeSlug = window.location.pathname.split('/')[4];
        await fetchJSON(`/apps/survey/store/${storeSlug}/reset_survey`, { method:'POST', body: JSON.stringify({}) });
        window.location.href = `/apps/survey/store/${storeSlug}/answer`;
      }catch(e){
        alert('リセットに失敗しました: ' + (e.message || e));
      }
    }
  });

  loadConfig();
  
  // ボタン表示を初期化
  updateSpinButton();
});
