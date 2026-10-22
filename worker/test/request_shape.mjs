// 檢查送給 Claude API 的請求長什麼樣子（攔截網路請求，不會真的送出、不花錢）
import assert from "node:assert/strict";
import { callModel } from "../src/index.js";

let captured;
const fakeFetch = async (url, init) => {
  captured = { url: String(url), headers: init.headers, body: JSON.parse(init.body) };
  return new Response(JSON.stringify({
    id: "msg_test", type: "message", role: "assistant", model: "claude-haiku-5-5", stop_reason: "end_turn",
    content: [{ type: "text", text: JSON.stringify({ verdict: "可疑", method_id: "none", reasons: ["「測試」"], advice: ["打 165"] }) }],
    usage: { input_tokens: 10, output_tokens: 10 },
  }), { status: 200, headers: { "content-type": "application/json", "request-id": "req_test" } });
};

const out = await callModel("請到ATM解除設定", { ANTHROPIC_API_KEY: "test-key", MODEL: "claude-haiku-5-5" }, fakeFetch);
const b = captured.body;
assert.ok(captured.url.endsWith("/v1/messages"));
assert.equal(b.model, "claude-haiku-5-5");
assert.equal(b.system[0].cache_control.type, "ephemeral");
assert.equal(b.output_config.effort, "low");
assert.equal(b.output_config.format.type, "json_schema");
assert.ok(b.messages[0].content.startsWith("<message>"));
assert.equal(out.ok, true);
assert.equal(out.result.verdict, "可疑");
console.log("請求格式正確：", JSON.stringify({ model: b.model, max_tokens: b.max_tokens, output_config: { effort: b.output_config.effort, format: b.output_config.format.type }, system_chars: b.system[0].text.length }));
