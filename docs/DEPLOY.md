# 部署步驟（網頁版＋AI 中繼程式）

全部用專案專用 email 註冊，名稱用 `tw-scam-radar` 之類的中性名字。註冊帳號、付款、同意條款都要維護者本人操作。

注意：Cloudflare 會用註冊 email 自動產生 workers.dev 子網域，這個子網域會出現在公開的 AI 網址裡。部署前先到 Workers & Pages → Account details → Subdomain 改成中性名字。

目前的正式版：網頁放 GitHub Pages（`https://tw-scam-radar.github.io/tw-scam-radar/`，由發布流程推 `web/` 到公開專案的 `gh-pages` 分支），AI 中繼放 Cloudflare Workers（`https://radar-ai.tw-scam-radar.workers.dev`）。下面第 4 節的 Cloudflare Pages 是另一種放法。

## 1. 帳號（維護者本人）

| 服務 | 用途 | 費用 |
|---|---|---|
| Cloudflare | 放網頁（Pages）、放 AI 中繼程式（Workers）、人機驗證（Turnstile）、計數（KV） | 免費方案即可 |
| Anthropic Console（platform.claude.com） | AI 判讀的 API 金鑰 | 用多少付多少，先儲值少量 |

Anthropic Console 裡可以設定用量上限（建議設，金額照每日上限換算）。

## 2. 人機驗證（Turnstile）

Cloudflare 後台 → Turnstile → 新增網站，網域填網頁版網址。會拿到：
- **site key**：填進 `web/config.js` 的 `turnstileSiteKey`
- **secret key**：之後用 `wrangler secret put TURNSTILE_SECRET` 設定

## 3. AI 中繼程式（Worker）

```bash
cd worker
npm install
npx wrangler login                      # 會開瀏覽器，用專案帳號登入
npx wrangler kv namespace create RADAR_KV   # 把印出來的 id 填進 wrangler.toml
npx wrangler secret put ANTHROPIC_API_KEY
npx wrangler secret put TURNSTILE_SECRET
npx wrangler secret put HASH_SALT       # 隨便一串長亂碼，用來把來源 IP 變成代碼
```

在 `wrangler.toml` 填 `ALLOWED_ORIGINS`（網頁版網址），每日上限改 `DAILY_LIMIT`、`PER_CLIENT_LIMIT`。然後：

```bash
npm test                 # 本機測試（不花錢）
npx wrangler deploy      # 部署，會印出網址，例如 https://radar-ai.<子網域>.workers.dev
```

## 4. 網頁版（Pages）

把 Worker 網址填進 `web/config.js` 的 `aiEndpoint`，先跑 `python tools/build.py` 更新資料，再部署：

```bash
npx wrangler pages deploy web --project-name tw-scam-radar
```

## 5. 上線前用正式寫法量一次分數（會花錢；345 題用 Haiku 5.5 約不到 1 美元，Sonnet 5.5 大約貴 20 倍）

```bash
python tools/blind_to_json.py            # 把盲測考卷轉成 JSON
cd worker
ANTHROPIC_API_KEY=... node test/eval_api.mjs ../work/blind/cofacts_blind.json ../work/api_haiku_cofacts.json
ANTHROPIC_API_KEY=... node test/eval_api.mjs ../work/blind/holdout_blind.json ../work/api_haiku_holdout.json
cd .. && python work/score_models.py
```

## 本機測試（不用任何帳號）

```bash
python -m http.server 8766 --directory web
node worker/test/local_server.mjs        # 假 AI，固定回答
```

打開 `http://localhost:8766/?ai=http://localhost:8787`。
