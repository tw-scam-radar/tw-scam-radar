import { Engine } from "./radar.js";

const $ = (id) => document.getElementById(id);
const cfg = { ...(window.RADAR_CONFIG || {}) };
// 本機開發：http://localhost:8766/?ai=http://localhost:8787 可以接上本機的中繼程式
// 加 &ts=1x00000000000000000000AA 換成 Cloudflare 的測試用 site key（正式的 key 只認正式網域）
if (location.hostname === "localhost") {
  const q = new URLSearchParams(location.search);
  const ai = q.get("ai"), ts = q.get("ts");
  if (ai && /^http:\/\/localhost:\d+$/.test(ai)) cfg.aiEndpoint = ai;
  if (ts && /^[\w-]+$/.test(ts)) cfg.turnstileSiteKey = ts;
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const list = (items) => `<ul>${items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;

const LEVELS = {
  "高風險": { cls: "lv-high", title: "很可能是詐騙", say: "先不要回覆、不要點連結、不要匯款。" },
  "可疑": { cls: "lv-sus", title: "有詐騙跡象，先別照做", say: "照著做之前，先打 165 或自己查官方電話問清楚。" },
  "留意": { cls: "lv-notice", title: "有一點可疑，自動比對判不準", say: "可以請 AI 再看一次，或直接打 165 問。" },
  "沒有發現已知紅旗": { cls: "lv-ok", title: "沒有看到已知的詐騙跡象", say: "這不代表一定安全。只要對方要你匯款、給驗證碼、下載 App 或交出提款卡，先打 165。" },
};

let engine;

async function load() {
  try {
    const [radar, domains, urls] = await Promise.all([
      fetch("data/radar.json").then((r) => r.json()),
      fetch("data/bad_domains.txt").then((r) => r.text()),
      fetch("data/bad_urls.txt").then((r) => r.text()),
    ]);
    engine = new Engine(radar, domains, urls);
    $("check").disabled = false;
    $("status").textContent = "";
    $("meta").textContent = `資料版本 ${radar.version}｜詐騙手法 ${radar.counts.methods} 類｜165 涉詐網址 ${radar.counts.bad_domains.toLocaleString()} 筆`;
  } catch (e) {
    $("status").textContent = "資料載入失敗，請重新整理頁面。";
  }
}

function renderRule(text) {
  const r = engine.analyze(text);
  const lv = LEVELS[r.level];
  const top = r.methods[0];
  let html = `<div class="card ${lv.cls}"><p class="verdict">${lv.title}</p><p>${lv.say}</p>`;
  if (r.genre === "新聞或文章") html += `<p class="note">這則看起來是轉傳的新聞或文章，不像是對方直接傳給你的訊息。</p>`;
  else if (r.genre) html += `<p class="note">這則看起來是防詐提醒或轉傳文：它在描述詐騙手法，本身不一定是詐騙。</p>`;
  if (r.official_list_hits.length) {
    html += `<h3>網址在 165 官方涉詐名單上</h3>${list(r.official_list_hits.map((h) => h.domain))}`;
  }
  if (top) {
    html += `<h3>最像：${esc(top.name)}</h3><ul>`;
    for (const h of top.hits) html += `<li>${esc(h.text)}<div class="hit">訊息裡的「${esc(h.found.join("」「"))}」</div></li>`;
    html += `</ul>`;
    if (top.final_ask.length) html += `<h3>對方接下來通常會要你</h3>${list(top.final_ask.slice(0, 3))}`;
    if (top.verify.length) html += `<h3>怎麼查證</h3>${list(top.verify.slice(0, 3))}`;
    if (top.if_already_happened.length) html += `<h3>如果已經照做了</h3>${list(top.if_already_happened.slice(0, 3))}`;
  }
  if (r.common_flags.length) {
    html += `<h3>其他可疑跡象</h3><ul>${r.common_flags.map((h) => `<li>${esc(h.text)}${h.why ? `<div class="hit">${esc(h.why)}</div>` : ""}</li>`).join("")}</ul>`;
  }
  html += `<a class="call" href="tel:165">撥打 165 反詐騙諮詢專線</a></div>`;
  $("result").innerHTML = html;
  $("result").hidden = false;
  renderAiOffer(r);
}

function renderAiOffer(r) {
  const clean = r.level === "沒有發現已知紅旗" && !r.genre;
  const unsure = r.genre || r.level === "留意" || clean;
  const box = $("ai");
  // 規則看到一點紅旗但判不準 → 主要按鈕；完全沒紅旗或已判出紅旗 → 次要按鈕（省下每日名額）
  const label = clean ? "還是不放心？請 AI 判讀" : unsure ? "自動比對判不出來，請 AI 判讀" : "我覺得不是詐騙，請 AI 再看一次";
  const primary = unsure && !clean;
  if (!cfg.aiEndpoint) {
    box.innerHTML = unsure
      ? `<div class="card"><p><b>還是不放心？</b>AI 判讀還在測試，暫時沒有開放；不確定的話請直接打 165。</p></div>`
      : "";
    box.hidden = !unsure;
    return;
  }
  box.innerHTML = `<div class="card"><p class="note">按下後，這則訊息會送到 AI 服務判讀（我們不保存訊息內容）。每天名額有限。送出前請先把姓名、電話、帳號刪掉，或改成○○。</p>
    <div id="tsBox"></div>
    <button id="askAi" class="${primary ? "primary" : "ghost"}">${label}</button><div id="aiOut"></div></div>`;
  box.hidden = false;
  $("askAi").onclick = askAi;
  renderTurnstile();
}

// Cloudflare Turnstile 人機驗證（有設定 site key 才顯示）
// 容器 id 不能叫 turnstile：有 id 的元素會變成同名的 window 屬性，蓋掉 window.turnstile
let tsLoading = null;
function renderTurnstile() {
  if (!cfg.turnstileSiteKey) return;
  const btn = $("askAi");
  btn.disabled = true; // 拿到驗證 token 才能送
  window.turnstileToken = "";
  const draw = () => {
    window.tsWidget = window.turnstile.render("#tsBox", {
      sitekey: cfg.turnstileSiteKey, language: "zh-tw",
      callback: (token) => { window.turnstileToken = token; btn.disabled = false; },
      "expired-callback": () => { window.turnstileToken = ""; btn.disabled = true; },
    });
  };
  if (typeof window.turnstile?.render === "function") return draw();
  if (!tsLoading) {
    tsLoading = new Promise((ok) => {
      const s = document.createElement("script");
      s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
      s.onload = ok;
      document.head.appendChild(s);
    });
  }
  tsLoading.then(draw);
}

async function askAi() {
  const btn = $("askAi");
  btn.disabled = true;
  $("aiOut").innerHTML = `<p class="note">AI 判讀中……</p>`;
  try {
    const res = await fetch(cfg.aiEndpoint.replace(/\/$/, "") + "/check", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ text: $("msg").value, turnstileToken: window.turnstileToken || "" }),
    });
    let data = null;
    try { data = await res.json(); } catch { /* 回應不是 JSON */ }
    if (!res.ok || !data) {
      const msg = data && data.message ? data.message.replace(/[。.！!]+$/, "") : "AI 判讀暫時連不上";
      throw Object.assign(new Error(msg), { fromServer: true });
    }
    const lv = { "高風險": LEVELS["高風險"], "可疑": LEVELS["可疑"], "看起來正常": LEVELS["沒有發現已知紅旗"] }[data.verdict] || LEVELS["留意"];
    $("aiOut").innerHTML = `<div class="card ${lv.cls}"><p class="verdict">AI：${esc(data.verdict)}</p>
      ${data.reasons?.length ? `<h3>理由</h3>${list(data.reasons)}` : ""}
      ${data.advice?.length ? `<h3>建議</h3>${list(data.advice)}` : ""}
      <p class="note">AI 也會判錯；有疑問請打 165。${data.remaining != null ? `今天還剩 ${data.remaining} 次。` : ""}</p></div>`;
  } catch (e) {
    const msg = e.fromServer ? e.message : "AI 判讀暫時連不上"; // 連不上網路時瀏覽器給的是英文，不顯示給使用者
    $("aiOut").innerHTML = `<p class="note">${esc(msg)}。請直接打 165 問。</p>`;
    // 驗證 token 只能用一次：換一個新的，拿到後按鈕會自己恢復
    if (cfg.turnstileSiteKey && window.turnstile?.reset) { window.turnstileToken = ""; window.turnstile.reset(window.tsWidget); }
    else btn.disabled = false;
  }
}

$("check").onclick = () => { if ($("msg").value.trim()) renderRule($("msg").value); };
$("clear").onclick = () => { $("msg").value = ""; $("result").hidden = true; $("ai").hidden = true; };
load();
