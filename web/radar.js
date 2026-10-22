// 台灣詐騙雷達：規則比對引擎（瀏覽器與 Node 共用）
// 跟 tools/check.py 是同一套邏輯；改這裡要同步改那裡，並跑 tools/parity.py 確認結果一致。

export const HIGH = 6, SUSPICIOUS = 3, NOTICE = 2;

const URL_RX = /(?:https?:\/\/)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?:[\/:?#][\x21-\x7e]*)?/gi;
const NEGATION_RX = /(不會|不需|不用|不必|無須|毋須|請勿|切勿|勿|不要|不得|不可|不能|絕不|從不|並未|並沒有|沒有|未曾|禁止|謹防|小心|慎防|提防|避免|防範|不收|不含|不接受|不提供|不經手)/;
const NEGATION_WINDOW = 20;
const CLAUSE_BREAK = /[,.!?;:、。\n]/;

const SHARED_HOSTS = ["google.com", "goo.gl", "forms.gle", "line.me", "lin.ee", "facebook.com", "fb.com",
  "instagram.com", "youtube.com", "youtu.be", "t.me", "bit.ly", "reurl.cc", "linktr.ee",
  "apple.com", "github.com", "dropbox.com", "notion.site", "canva.site"];
const TRUSTED_HOSTS = ["gov.tw", "udn.com", "chinatimes.com", "ettoday.net", "setn.com", "tvbs.com.tw",
  "ltn.com.tw", "cna.com.tw", "pts.org.tw", "storm.mg", "ctwant.com", "ebc.net.tw",
  "newtalk.tw", "mirrormedia.mg", "tw.news.yahoo.com", "mygopen.com", "tfc-taiwan.org.tw",
  "cofacts.tw", "youtube.com", "youtu.be"];
const TRUSTED_PREFIXES = ["liff.line.me/1454987169-"];

const NEWS_RX = /(記者|報導|新聞網|line today|來源[:：]|中央社|聯合報|自由時報|ettoday|三立|tvbs|ctwant|東森|新頭殼|鏡週刊|風傳媒|yahoo)/i;
const WARN_RX = /(提醒大家|請大家|大家注意|大家小心|千萬別|千萬不要|小心詐騙|詐騙手法|詐騙集團|詐團|被騙了|受害者|請勿點|不要點|別點|轉發|轉傳|分享給)/;
const WARN_MIN_LEN = 120;

export function normalize(text) {
  return (text || "").normalize("NFKC").toLowerCase().replaceAll("臺", "台").replace(/\s+/g, "");
}

function negated(s, start) {
  let before = s.slice(Math.max(0, start - NEGATION_WINDOW), start);
  const parts = before.split(CLAUSE_BREAK);
  before = parts[parts.length - 1];
  return NEGATION_RX.test(before);
}

// 回傳比對函式：命中時回傳訊息裡被命中的那段文字（給使用者看），沒命中回傳 null
export function compileCue(cue) {
  cue = String(cue);
  if (cue.startsWith("re:")) {
    const rx = new RegExp(cue.slice(3).normalize("NFKC").replaceAll("臺", "台"), "gi");
    return (s) => {
      for (const m of s.matchAll(rx)) if (!negated(s, m.index)) return m[0];
      return null;
    };
  }
  const key = normalize(cue);
  return (s) => {
    let i = s.indexOf(key);
    while (i !== -1) {
      if (!negated(s, i)) return key;
      i = s.indexOf(key, i + 1);
    }
    return null;
  };
}

const stripScheme = (url) => url.replace(/^(https?:\/\/)?(www\.)?/, "");
const hostOf = (url) => url.split("/")[0];
const isShared = (host) => SHARED_HOSTS.some((h) => host === h || host.endsWith("." + h));
const isTrusted = (url) => {
  const host = hostOf(url);
  return TRUSTED_HOSTS.some((h) => host === h || host.endsWith("." + h)) || TRUSTED_PREFIXES.some((p) => url.startsWith(p));
};
const maskTrusted = (text) => text.replace(URL_RX, (m) => (isTrusted(stripScheme(m)) ? "[可信網址]" : m));

function genre(raw) {
  if (NEWS_RX.test(raw)) return "新聞或文章";
  if ([...raw].length >= WARN_MIN_LEN && WARN_RX.test(raw)) return "防詐提醒或轉傳文";
  return null;
}

function compileFlags(flags) {
  return (flags || []).map((f) => ({ f, matchers: (f.cues || []).map((c) => [String(c), compileCue(c)]) }));
}

function hitsOf(compiled, text) {
  const hits = [];
  for (const { f, matchers } of compiled) {
    const matched = [], found = [];
    for (const [label, fn] of matchers) {
      const snippet = fn(text);
      if (snippet !== null) { matched.push(label); if (!found.includes(snippet)) found.push(snippet); }
    }
    if (matched.length) hits.push({ id: f.id, text: f.text, weight: f.weight ?? 1, why: f.why || "", matched, found });
  }
  return hits;
}

export class Engine {
  // radar：dist/radar.json 的內容；badDomains、badUrls：dist/ 底下的 txt（一行一個）
  constructor(radar, badDomains = "", badUrls = "") {
    this.version = radar.version;
    this.methods = radar.methods.map((m) => ({ m, compiled: compileFlags(m.red_flags) }));
    this.common = compileFlags(radar.common_flags);
    this.badDomains = new Set(badDomains.split("\n").map((s) => s.trim()).filter(Boolean));
    this.badUrls = badUrls.split("\n").map((s) => s.trim()).filter(Boolean);
  }

  analyze(raw) {
    const text = normalize(raw);
    const cueText = maskTrusted(text);
    const commonHits = hitsOf(this.common, cueText);
    const commonScore = commonHits.reduce((a, h) => a + h.weight, 0);

    const ranked = [];
    for (const { m, compiled } of this.methods) {
      const hits = hitsOf(compiled, cueText);
      if (hits.length) ranked.push({ id: m.id, name: m.name, score: hits.reduce((a, h) => a + h.weight, 0), hits,
        final_ask: m.final_ask || [], verify: m.verify || [], if_already_happened: m.if_already_happened || [] });
    }
    ranked.sort((a, b) => b.score - a.score);

    const domains = [...text.matchAll(URL_RX)].map((m) => m[1].replace(/^www\./, ""));
    const listed = domains.filter((d) => this.badDomains.has(d)).map((d) => ({ domain: d, list: "165" }));
    for (const m of text.matchAll(URL_RX)) {
      const url = stripScheme(m[0]);
      for (const bad of this.badUrls) if (url.startsWith(bad)) listed.push({ domain: bad, list: "165" });
    }

    const score = (ranked[0] ? ranked[0].score : 0) + commonScore;
    const g = genre(raw);
    let level;
    if (listed.length || score >= HIGH) level = "高風險";
    else if (score >= SUSPICIOUS) level = "可疑";
    else if (score >= NOTICE) level = "留意";
    else level = "沒有發現已知紅旗";
    if (g && !listed.length && (level === "高風險" || level === "可疑")) level = "留意";
    return { level, score, genre: g, official_list_hits: listed, common_flags: commonHits, methods: ranked.slice(0, 3), domains };
  }
}
