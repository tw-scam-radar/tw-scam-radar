"""用測試集評分規則比對：抓到幾成詐騙、把幾成正常訊息誤判成詐騙。

用法：python tools/eval.py [--show-misses]
「判成詐騙」＝等級為「高風險」或「可疑」。
"""
import argparse
import sys
from collections import Counter

from check import Engine
from common import TESTS, load_yaml, normalize

# 新聞只引用了半句的「片段」不像真的會被貼來檢查的訊息，分開計分
FRAGMENT_LEN = 15


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show-misses", action="store_true")
    ap.add_argument("--tests", default=str(TESTS), help="測試檔，預設 tests/cases.yaml；獨立考卷用 private/tests/holdout.yaml")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    eng = Engine()
    cases = load_yaml(a.tests)
    stats = Counter()
    misses, false_alarms, wrong_type = [], [], []
    for t in cases:
        r = eng.analyze(t["text"])
        flagged = r["level"] in ("高風險", "可疑")
        origin = "fragment" if len(normalize(t["text"])) < FRAGMENT_LEN else t.get("origin", "?")
        key = f"{t['label']}_{origin}"
        stats[key] += 1
        if t["label"] == "scam":
            stats[f"{key}_hit"] += flagged
            if not flagged:
                misses.append((t, r))
            top3 = [m["id"] for m in r["methods"]]
            if t.get("method_id"):
                stats["typed"] += 1
                stats["typed_top3"] += t["method_id"] in top3
                if flagged and t["method_id"] not in top3:
                    wrong_type.append((t, top3))
        else:
            stats[f"{key}_fp"] += flagged
            if flagged:
                false_alarms.append((t, r))

    def pct(a, b):
        return f"{a}/{b}（{a / b:.0%}）" if b else "0/0"

    print(f"測試案例 {len(cases)} 則")
    for origin in ("quoted", "synthetic", "fragment"):
        print(f"詐騙・{origin}：抓到 {pct(stats[f'scam_{origin}_hit'], stats[f'scam_{origin}'])}")
        print(f"正常・{origin}：誤判 {pct(stats[f'legit_{origin}_fp'], stats[f'legit_{origin}'])}")
    print(f"有標手法的詐騙，正確手法在前三名：{pct(stats['typed_top3'], stats['typed'])}")

    if a.show_misses:
        print("\n── 漏抓 ──")
        for t, r in misses:
            print(f"{t['id']}［{t.get('method_id', '')}］分數 {r['score']}：{t['text'][:60]}")
        print("\n── 誤判 ──")
        for t, r in false_alarms:
            top = r["methods"][0]["id"] if r["methods"] else "-"
            print(f"{t['id']} 分數 {r['score']}（{top}）：{t['text'][:60]}")
        print("\n── 抓到但手法認錯 ──")
        for t, top3 in wrong_type:
            print(f"{t['id']} 應為 {t['method_id']}，前三名 {top3}")


if __name__ == "__main__":
    main()
