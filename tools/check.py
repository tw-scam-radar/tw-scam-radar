"""規則比對：貼一段訊息，找出像哪一種詐騙、命中哪些紅旗。

這是網頁版（不呼叫 AI）的判斷邏輯原型，也是測試集的評分器。
用法：
  python tools/check.py "訊息內容"
  python tools/check.py --file 訊息.txt
  python tools/check.py --json "訊息內容"
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

from common import ROOT, compile_cue, load_common_flags, load_methods, normalize

OFFICIAL_DIR = ROOT / "data" / "official"
# 路徑只吃可見的 ASCII 字元：比對的是拿掉空白的文字，不能把網址後面的中文吃進去
URL_RX = re.compile(r"(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?:[/:?#][\x21-\x7e]*)?", re.IGNORECASE)

# 分數門檻（用 tools/eval.py 調）
HIGH, SUSPICIOUS, NOTICE = 6, 3, 2

# 大家共用的平台：官方名單收的是上面的單一頁面，不能整個網域判黑
SHARED_HOSTS = ("google.com", "goo.gl", "forms.gle", "line.me", "lin.ee", "facebook.com", "fb.com",
                "instagram.com", "youtube.com", "youtu.be", "t.me", "bit.ly", "reurl.cc", "linktr.ee",
                "apple.com", "github.com", "dropbox.com", "notion.site", "canva.site")


# 可信網站：政府、主要新聞、查核單位。網址如果是這些網站，就不算「訊息裡有可疑連結」。
TRUSTED_HOSTS = ("gov.tw", "udn.com", "chinatimes.com", "ettoday.net", "setn.com", "tvbs.com.tw",
                 "ltn.com.tw", "cna.com.tw", "pts.org.tw", "storm.mg", "ctwant.com", "ebc.net.tw",
                 "newtalk.tw", "mirrormedia.mg", "tw.news.yahoo.com", "mygopen.com", "tfc-taiwan.org.tw",
                 "cofacts.tw", "youtube.com", "youtu.be")
TRUSTED_PREFIXES = ("liff.line.me/1454987169-",)  # LINE TODAY 的文章連結

# 新聞或轉傳的防詐提醒：描述詐騙，但本身不是詐騙訊息
NEWS_RX = re.compile(r"(記者|報導|新聞網|line today|來源[:：]|中央社|聯合報|自由時報|ettoday|三立|tvbs|"
                     r"ctwant|東森|新頭殼|鏡週刊|風傳媒|yahoo)", re.IGNORECASE)
WARN_RX = re.compile(r"(提醒大家|請大家|大家注意|大家小心|千萬別|千萬不要|小心詐騙|詐騙手法|詐騙集團|詐團|"
                     r"被騙了|受害者|請勿點|不要點|別點|轉發|轉傳|分享給)")
WARN_MIN_LEN = 120


def _strip_scheme(url):
    return re.sub(r"^(https?://)?(www\.)?", "", url)


def _is_trusted(url):
    host = url.split("/")[0]
    return any(host == h or host.endswith("." + h) for h in TRUSTED_HOSTS) or url.startswith(TRUSTED_PREFIXES)


def _mask_trusted_urls(text):
    """把可信網站的網址換成「[可信網址]」，讓連結類紅旗不會因為它們命中。"""
    def repl(m):
        return "[可信網址]" if _is_trusted(_strip_scheme(m.group(0))) else m.group(0)
    return URL_RX.sub(repl, text)


def _genre(raw):
    if NEWS_RX.search(raw):
        return "新聞或文章"
    if len(raw) >= WARN_MIN_LEN and WARN_RX.search(raw):
        return "防詐提醒或轉傳文"
    return None


def _is_shared(host):
    return any(host == h or host.endswith("." + h) for h in SHARED_HOSTS)


def _compile_flags(flags):
    out = []
    for f in flags or []:
        matchers = [compile_cue(str(c)) for c in f.get("cues") or []]
        out.append((f, matchers))
    return out


def parse_official_csvs(directory):
    """讀官方名單 CSV（找名稱含「網域」「網址」或 url 的欄位），回傳 (網域→名單, 網址→名單)。

    名單裡有些是大平台上的單一頁面（例如 Google Play 上某個 App）。這種不能整個網域
    一起判黑，只比對到網址路徑，放在第二個字典。
    """
    domains, urls = {}, {}
    for p in sorted(Path(directory).glob("*.csv")):
        with open(p, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                for k, v in row.items():
                    if not (k and v and re.search(r"網域|網址|url", k, re.IGNORECASE)):
                        continue
                    url = _strip_scheme(normalize(v))
                    host = url.split("/")[0]
                    if _is_shared(host):
                        if "/" in url:
                            urls[url.rstrip(".")] = p.stem
                    elif URL_RX.fullmatch(host):
                        domains[host] = p.stem
    return domains, urls


def _read_tsv(path):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, _, lst = line.partition("\t")
            out[key] = lst or "165"
    return out


class Engine:
    def __init__(self):
        self.methods = [(m, _compile_flags(m.get("red_flags"))) for m in load_methods()]
        self.common = _compile_flags(load_common_flags())
        self.bad_domains = self._load_official_domains()

    def _load_official_domains(self):
        """優先讀 tools/update_official.py 整理好的精簡名單；沒有的話才讀原始 CSV。"""
        compact = OFFICIAL_DIR / "bad_domains.tsv"
        if compact.exists():
            urls = OFFICIAL_DIR / "bad_urls.tsv"
            self.bad_urls = _read_tsv(urls) if urls.exists() else {}
            return _read_tsv(compact)
        domains, self.bad_urls = parse_official_csvs(OFFICIAL_DIR / "raw") if (OFFICIAL_DIR / "raw").exists() else ({}, {})
        return domains

    @staticmethod
    def _hits(compiled, text):
        hits = []
        for f, matchers in compiled:
            matched = [label for label, fn in matchers if fn(text)]
            if matched:
                hits.append({"id": f.get("id"), "text": f.get("text"), "weight": f.get("weight", 1),
                             "why": f.get("why", ""), "matched": matched})
        return hits

    def analyze(self, raw):
        text = normalize(raw)
        cue_text = _mask_trusted_urls(text)
        common_hits = self._hits(self.common, cue_text)
        common_score = sum(h["weight"] for h in common_hits)

        ranked = []
        for m, compiled in self.methods:
            hits = self._hits(compiled, cue_text)
            if hits:
                ranked.append({"id": m["id"], "name": m.get("name"), "score": sum(h["weight"] for h in hits),
                               "hits": hits, "final_ask": m.get("final_ask", []), "verify": m.get("verify", [])})
        ranked.sort(key=lambda r: -r["score"])

        domains = [d.removeprefix("www.") for d in URL_RX.findall(text)]
        listed = [{"domain": d, "list": self.bad_domains[d]} for d in domains if d in self.bad_domains]
        for m in URL_RX.finditer(text):
            url = _strip_scheme(m.group(0))
            for bad, lst in self.bad_urls.items():
                if url.startswith(bad):
                    listed.append({"domain": bad, "list": lst})

        score = (ranked[0]["score"] if ranked else 0) + common_score
        genre = _genre(raw)
        if listed or score >= HIGH:
            level = "高風險"
        elif score >= SUSPICIOUS:
            level = "可疑"
        elif score >= NOTICE:
            level = "留意"
        else:
            level = "沒有發現已知紅旗"
        # 新聞與防詐提醒：最多到「留意」（命中官方名單除外），並說明原因
        if genre and not listed and level in ("高風險", "可疑"):
            level = "留意"
        return {"level": level, "score": score, "genre": genre, "official_list_hits": listed,
                "common_flags": common_hits, "methods": ranked[:3], "domains": domains}


def render(r):
    lines = [f"判斷：{r['level']}（分數 {r['score']}）"]
    if r.get("genre") == "新聞或文章":
        lines.append("這則看起來是轉傳的新聞或文章，不像是對方直接傳給你的訊息。")
    elif r.get("genre"):
        lines.append("這則看起來是防詐提醒或轉傳文：它在描述詐騙手法，本身不一定是詐騙。")
    if r["official_list_hits"]:
        for h in r["official_list_hits"]:
            lines.append(f"  ⚠ 網址 {h['domain']} 在官方涉詐名單（{h['list']}）")
    if r["methods"]:
        top = r["methods"][0]
        lines.append(f"最像：{top['name']}")
        for h in top["hits"]:
            lines.append(f"  - {h['text']}（命中：{'、'.join(h['matched'])}）")
        others = [m["name"] for m in r["methods"][1:]]
        if others:
            lines.append("也有點像：" + "、".join(others))
    if r["common_flags"]:
        lines.append("共通紅旗：")
        for h in r["common_flags"]:
            lines.append(f"  - {h['text']}" + (f"：{h['why']}" if h["why"] else ""))
    if r["methods"]:
        if r["methods"][0]["final_ask"]:
            lines.append("對方最後通常會要你：" + "；".join(r["methods"][0]["final_ask"][:3]))
        if r["methods"][0]["verify"]:
            lines.append("怎麼查證：" + "；".join(r["methods"][0]["verify"][:3]))
    if r["level"] == "沒有發現已知紅旗":
        lines.append("沒有命中已知紅旗不代表安全。只要對方要你匯款、給驗證碼或下載 App，先打 165 問。")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?")
    ap.add_argument("--file")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    raw = Path(a.file).read_text(encoding="utf-8") if a.file else (a.text or sys.stdin.read())
    r = Engine().analyze(raw)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=2) if a.json else render(r))


if __name__ == "__main__":
    main()
