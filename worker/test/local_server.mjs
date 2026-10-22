// 本機測試用：把中繼程式包成 http://localhost:8787，AI 換成固定回答的假模型（不花錢、不連網）。
// 網頁用 http://localhost:8766/?ai=http://localhost:8787 打開即可接上。
import http from "node:http";
import { handle } from "../src/index.js";

const kv = new Map();
const env = {
  ALLOWED_ORIGINS: "http://localhost:8766",
  DAILY_LIMIT: "300", PER_CLIENT_LIMIT: "5", HASH_SALT: "local",
  RADAR_KV: { get: async (k) => kv.get(k) ?? null, put: async (k, v) => kv.set(k, v) },
};
const fakeModel = async (text) => ({
  ok: true,
  result: /借|匯|轉帳|急/.test(text)
    ? { verdict: "可疑", method_id: "guess-who", reasons: ["（假 AI 測試回覆）訊息裡有「借」錢的要求"], advice: ["先打電話給本人確認", "撥 165 反詐騙諮詢專線"] }
    : { verdict: "看起來正常", method_id: "none", reasons: ["（假 AI 測試回覆）沒有看到要你付錢或給資料的要求"], advice: ["還是不放心就打 165"] },
});

http.createServer(async (req, res) => {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const request = new Request(`http://localhost:8787${req.url}`, {
    method: req.method,
    headers: { ...req.headers, "CF-Connecting-IP": req.socket.remoteAddress || "local" },
    body: ["GET", "HEAD", "OPTIONS"].includes(req.method) ? undefined : Buffer.concat(chunks),
  });
  const response = await handle(request, env, { callModel: fakeModel });
  res.writeHead(response.status, Object.fromEntries(response.headers));
  res.end(Buffer.from(await response.arrayBuffer()));
}).listen(8787, () => console.log("假 AI 中繼伺服器：http://localhost:8787"));
