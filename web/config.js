// 部署設定。aiEndpoint 留空＝不接 AI（只做規則比對）。
// publicAi 是 false 時，只有用「網址#key=通行碼」打開過的裝置能用 AI（通行碼要跟中繼程式的 OWNER_KEY 一樣）。
window.RADAR_CONFIG = {
  aiEndpoint: "",        // 例如 https://radar-ai.<你的子網域>.workers.dev
  turnstileSiteKey: "",  // Cloudflare Turnstile 的 site key（對外開放 AI 時用來防機器人）
  publicAi: false,
};
