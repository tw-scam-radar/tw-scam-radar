"""檢查手法庫與測試案例：格式、來源、個資、交叉引用。

用法：python tools/validate.py
有錯誤時結束碼為 1；警告不影響結束碼。
"""
import re
import sys

from common import (CATEGORIES, CHANNELS, EVIDENCE, ROOT, STAGES, TESTS, compile_cue,
                    load_common_flags, load_methods, load_yaml)

errors, warnings = [], []

# 個資與本機痕跡：公開前一定要是零
PRIVACY = [
    ("手機號碼", re.compile(r"(?<!\d)09\d{2}-?\d{3}-?\d{3}(?!\d)")),
    ("市話", re.compile(r"(?<!\d)0[2-8]-?\d{7,8}(?!\d)")),
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("長串數字（可能是帳號）", re.compile(r"(?<!\d)\d{10,16}(?!\d)")),
    ("本機路徑", re.compile(r"([A-Za-z]:\\\\?Users\\\\?|/[a-z]/Users/)", re.IGNORECASE)),
]
# 維護者自己的名字、帳號等只寫在 private/privacy_patterns.txt（不公開），一行一個
_private = ROOT / "private" / "privacy_patterns.txt"
if _private.exists():
    for line in _private.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            PRIVACY.append(("維護者個資", re.compile(re.escape(line.strip()), re.IGNORECASE)))
# 官方查證管道允許出現的號碼
ALLOWED_NUMBERS = {"165", "110", "1955", "113"}


def scan_privacy(where, text):
    for label, rx in PRIVACY:
        for m in rx.finditer(text):
            if m.group(0) in ALLOWED_NUMBERS:
                continue
            errors.append(f"{where}：疑似{label}「{m.group(0)}」")


def scan_repo_files():
    """所有會被公開的檔案（git 沒忽略的）都掃一遍維護者個資與本機路徑。"""
    import subprocess
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout
    checks = [(label, rx) for label, rx in PRIVACY if label in ("本機路徑", "維護者個資")]
    for rel in out.splitlines():
        p = ROOT / rel
        if p.suffix.lower() not in (".py", ".md", ".yaml", ".yml", ".json", ".html", ".js", ".css", ".txt", ".csv"):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for label, rx in checks:
            for m in rx.finditer(text):
                errors.append(f"公開檔案 {rel}：{label}「{m.group(0)}」")


def walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("url", "source_url"):
                continue
            yield from walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v)


def check_flags(where, flags, need_why=False):
    seen = set()
    for f in flags or []:
        fid = f.get("id", "")
        w = f"{where} 紅旗 {fid or '(無 id)'}"
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fid):
            errors.append(f"{w}：id 格式錯誤")
        if fid in seen:
            errors.append(f"{w}：id 重複")
        seen.add(fid)
        if not f.get("text"):
            errors.append(f"{w}：缺 text")
        cues = f.get("cues") or []
        if not cues:
            warnings.append(f"{w}：沒有 cues，規則比對抓不到")
        for c in cues:
            try:
                compile_cue(str(c))
            except Exception as e:  # 正規表示式寫錯
                errors.append(f"{w}：cue「{c}」無法編譯（{e}）")
        if f.get("weight") not in (1, 2, 3):
            errors.append(f"{w}：weight 要是 1、2、3")
        if need_why and not f.get("why"):
            warnings.append(f"{w}：缺 why")


def check_sources(where, sources):
    if not sources:
        errors.append(f"{where}：沒有 sources")
        return
    for s in sources:
        if not str(s.get("url", "")).startswith("http"):
            errors.append(f"{where}：來源缺網址（{s.get('title', '')}）")
        if s.get("level") not in ("L1", "L2"):
            errors.append(f"{where}：來源 level 要是 L1 或 L2（{s.get('title', '')}）")
        if not re.fullmatch(r"\d{4}(-\d{2}){0,2}", str(s.get("date", ""))):
            warnings.append(f"{where}：來源日期格式不對（{s.get('date')}）")


def main():
    methods = load_methods()
    ids = [m.get("id") for m in methods]
    idset = set(ids)
    for i in idset:
        if ids.count(i) > 1:
            errors.append(f"手法 id 重複：{i}")

    for m in methods:
        where = f"{m['_file']}:{m.get('id')}"
        for key in ("id", "name", "category", "summary", "channels", "red_flags",
                    "final_ask", "verify", "sources", "evidence"):
            if not m.get(key):
                errors.append(f"{where}：缺 {key}")
        if m.get("category") not in CATEGORIES:
            errors.append(f"{where}：category「{m.get('category')}」不在清單")
        for c in m.get("channels") or []:
            if c not in CHANNELS:
                warnings.append(f"{where}：管道「{c}」不在詞表")
        for st in m.get("stages") or []:
            if st.get("stage") not in STAGES:
                warnings.append(f"{where}：階段「{st.get('stage')}」不在詞表")
        for o in m.get("opener_examples") or []:
            if len(o) > 40:
                warnings.append(f"{where}：開場超過 40 字：{o[:20]}…")
        if m.get("evidence") not in EVIDENCE:
            errors.append(f"{where}：evidence 要是 🟢🟡🔴")
        for r in m.get("related") or []:
            if r not in idset:
                warnings.append(f"{where}：related 指到不存在的 {r}")
        check_flags(where, m.get("red_flags"))
        check_sources(where, m.get("sources"))
        for s in walk_strings({k: v for k, v in m.items() if k != "_file"}):
            scan_privacy(where, s)

    for f in load_common_flags():
        check_flags("共通紅旗", [f], need_why=True)
        check_sources(f"共通紅旗 {f.get('id')}", f.get("sources"))
        for s in walk_strings(f):
            scan_privacy(f"共通紅旗 {f.get('id')}", s)

    if TESTS.exists():
        tids = set()
        for t in load_yaml(TESTS):
            where = f"測試 {t.get('id')}"
            if t.get("id") in tids:
                errors.append(f"{where}：id 重複")
            tids.add(t.get("id"))
            if t.get("label") not in ("scam", "legit"):
                errors.append(f"{where}：label 要是 scam 或 legit")
            if t.get("origin") not in ("quoted", "synthetic"):
                errors.append(f"{where}：origin 要是 quoted 或 synthetic")
            if t.get("origin") == "quoted" and not str((t.get("source") or {}).get("url", "")).startswith("http"):
                errors.append(f"{where}：quoted 一定要附來源網址")
            if t.get("method_id") and t["method_id"] not in idset:
                warnings.append(f"{where}：method_id「{t['method_id']}」不存在")
            scan_privacy(where, t.get("text", ""))

    scan_repo_files()

    print(f"手法 {len(methods)} 筆，共通紅旗 {len(load_common_flags())} 條")
    for w in warnings:
        print("警告：" + w)
    for e in errors:
        print("錯誤：" + e)
    print(f"結果：{len(errors)} 個錯誤、{len(warnings)} 個警告")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
