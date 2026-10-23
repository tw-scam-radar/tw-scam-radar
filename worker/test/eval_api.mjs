// 用「正式的寫法」（跟中繼程式同一個 callModel、同一份系統提示）跑盲測考卷。會真的呼叫 Claude API、花錢。
// 需要環境變數 ANTHROPIC_API_KEY。用法：node test/eval_api.mjs <盲測.json> <輸出.json>
// 盲測檔格式：[{ "id": "...", "text": "..." }]
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { callModel } from "../src/index.js";

const [inPath, outPath] = process.argv.slice(2);
if (!process.env.ANTHROPIC_API_KEY) { console.error("缺少 ANTHROPIC_API_KEY"); process.exit(1); }
const items = JSON.parse(readFileSync(inPath, "utf8"));
const done = existsSync(outPath) ? JSON.parse(readFileSync(outPath, "utf8")) : [];
const seen = new Set(done.map((d) => d.id));
const env = { ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY, MODEL: process.env.MODEL || "claude-sonnet-5-5" };

for (const it of items) {
  if (seen.has(it.id)) continue; // 中斷後可以接著跑
  try {
    const r = await callModel(it.text, env);
    done.push(r.ok ? { id: it.id, verdict: r.result.verdict, method: r.result.method_id } : { id: it.id, verdict: "錯誤", method: r.reason });
  } catch (e) {
    done.push({ id: it.id, verdict: "錯誤", method: String(e?.status || e?.name) });
  }
  writeFileSync(outPath, JSON.stringify(done, null, 1));
  process.stdout.write(`\r${done.length}/${items.length}`);
}
console.log(`\n完成，寫入 ${outPath}`);
