// 台灣詐騙雷達：AI 判讀中繼程式（Cloudflare Worker）
// 網頁版規則判不出來時，把訊息轉給 Claude 判讀。
// - 全站每日上限（DAILY_LIMIT）＋每個來源每日上限（PER_CLIENT_LIMIT），用 KV 計數（KV 有延遲，極短時間內可能超出幾次）
// - 有設定 TURNSTILE_SECRET 時，先驗證人機驗證（防機器人灌額度）
// - 不保存、不記錄訊息內容；來源只存雜湊後的代碼，而且每天換鹽
import Anthropic from "@anthropic-ai/sdk";
import { PROMPT_VERSION, SYSTEM_PROMPT } from "./prompt.js";

const MAX_CHARS = 3000;
const VERDICTS = ["高風險", "可疑", "看起來正常"];
const OUTPUT_SCHEMA = {
  type: "object",
  properties: {
    verdict: { type: "string", enum: VERDICTS },
    method_id: { type: "string" },
    reasons: { type: "array", items: { type: "string" } },
    advice: { type: "array", items: { type: "string" } },
  },
  required: ["verdict", "method_id", "reasons", "advice"],
  additionalProperties: false,
};

// 台北時間的日期，每天 00:00 重新計數
const taipeiDate = (now = Date.now()) => new Date(now + 8 * 3600 * 1000).toISOString().slice(0, 10);

async function hashClient(ip, date, salt) {
  const data = new TextEncoder().encode(`${salt}|${date}|${ip}`);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)].slice(0, 8).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function corsHeaders(origin, env) {
  const allowed = (env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean);
  if (!origin || !allowed.includes(origin)) return null;
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "content-type",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

const json = (body, status, headers) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8", ...headers } });

async function verifyTurnstile(token, ip, env, fetchImpl) {
  if (!env.TURNSTILE_SECRET) return true; // 沒設定就不驗（只建議在測試時這樣）
  if (!token) return false;
  const form = new FormData();
  form.append("secret", env.TURNSTILE_SECRET);
  form.append("response", token);
  if (ip) form.append("remoteip", ip);
  const res = await fetchImpl("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form });
  const data = await res.json();
  return data.success === true;
}

// 呼叫 Claude。回傳 { ok, result } 或 { ok:false, reason }
export async function callModel(text, env, fetchImpl) {
  const client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, ...(fetchImpl ? { fetch: fetchImpl } : {}) });
  const response = await client.messages.create({
    model: env.MODEL || "claude-sonnet-5-5",
    max_tokens: 2048,
    system: [{ type: "text", text: SYSTEM_PROMPT, cache_control: { type: "ephemeral" } }],
    messages: [{ role: "user", content: `<message>\n${text}\n</message>` }],
    output_config: { effort: "low", format: { type: "json_schema", schema: OUTPUT_SCHEMA } },
  });
  if (response.stop_reason === "refusal") return { ok: false, reason: "refusal" };
  const block = response.content.find((b) => b.type === "text");
  if (!block) return { ok: false, reason: "empty" };
  const result = JSON.parse(block.text);
  if (!VERDICTS.includes(result.verdict)) return { ok: false, reason: "bad_output" };
  return { ok: true, result };
}

// deps 讓測試可以換掉真正的 AI 呼叫與外部請求
export async function handle(request, env, deps = {}) {
  const callModelImpl = deps.callModel || callModel;
  const fetchImpl = deps.fetch || fetch;
  const now = deps.now ? deps.now() : Date.now();
  const origin = request.headers.get("Origin");
  const cors = corsHeaders(origin, env);
  const url = new URL(request.url);

  if (request.method === "OPTIONS") return cors ? new Response(null, { status: 204, headers: cors }) : new Response(null, { status: 403 });
  if (url.pathname === "/health") return json({ ok: true, prompt: PROMPT_VERSION }, 200, cors || {});
  if (url.pathname !== "/check" || request.method !== "POST") return json({ message: "找不到這個位置" }, 404, cors || {});
  if (!cors) return json({ message: "不允許的來源" }, 403, {});

  let body;
  try { body = await request.json(); } catch { return json({ message: "格式錯誤" }, 400, cors); }
  const text = typeof body.text === "string" ? body.text.trim() : "";
  if (!text) return json({ message: "沒有收到訊息內容" }, 400, cors);
  if ([...text].length > MAX_CHARS) return json({ message: `訊息太長，請只貼 ${MAX_CHARS} 字以內` }, 400, cors);

  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  if (!(await verifyTurnstile(body.turnstileToken, ip, env, fetchImpl))) {
    return json({ message: "人機驗證沒有通過，請重新整理頁面再試" }, 403, cors);
  }

  const date = taipeiDate(now);
  const dailyLimit = Number(env.DAILY_LIMIT || 300);
  const perClient = Number(env.PER_CLIENT_LIMIT || 5);
  const clientKey = `c:${date}:${await hashClient(ip, date, env.HASH_SALT || "")}`;
  const globalKey = `d:${date}`;
  const [g, c] = await Promise.all([env.RADAR_KV.get(globalKey), env.RADAR_KV.get(clientKey)]);
  const used = Number(g || 0), mine = Number(c || 0);
  if (used >= dailyLimit) return json({ message: "今天的 AI 判讀名額已經用完" }, 429, cors);
  if (mine >= perClient) return json({ message: `你今天已經用了 ${perClient} 次 AI 判讀` }, 429, cors);

  let out;
  try {
    out = await callModelImpl(text, env);
  } catch (e) {
    console.log("model_error", e?.status || e?.name || "unknown"); // 只記錯誤類型，不記訊息內容
    return json({ message: "AI 暫時無法使用" }, 502, cors);
  }
  if (!out.ok) return json({ message: "AI 這次判斷不出來" }, 502, cors);

  // 成功才扣額度（兩天後自動刪除）
  await Promise.all([
    env.RADAR_KV.put(globalKey, String(used + 1), { expirationTtl: 172800 }),
    env.RADAR_KV.put(clientKey, String(mine + 1), { expirationTtl: 172800 }),
  ]);
  const r = out.result;
  return json({
    verdict: r.verdict,
    method_id: r.method_id,
    reasons: (r.reasons || []).slice(0, 3),
    advice: (r.advice || []).slice(0, 3),
    remaining: Math.max(0, perClient - mine - 1),
  }, 200, cors);
}

export default {
  fetch: (request, env) => handle(request, env),
};
