"""找出太普通的關鍵詞：在正常訊息裡也會命中的 cue。

用法：python tools/audit_cues.py
"""
import sys
from collections import defaultdict

from common import TESTS, compile_cue, load_common_flags, load_methods, load_yaml, normalize


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cases = [(t, normalize(t["text"])) for t in load_yaml(TESTS)]
    owners = [(m["id"], f) for m in load_methods() for f in m.get("red_flags") or []]
    owners += [("共通", f) for f in load_common_flags()]
    rows = []
    for owner, f in owners:
        for c in f.get("cues") or []:
            _, fn = compile_cue(str(c))
            legit = [t["id"] for t, s in cases if t["label"] == "legit" and fn(s)]
            scam = sum(1 for t, s in cases if t["label"] == "scam" and fn(s))
            if legit:
                rows.append((len(legit), scam, owner, f.get("id"), f.get("weight"), c, legit))
    rows.sort(key=lambda r: (-r[0], r[1]))
    print("正常命中\t詐騙命中\t手法\t紅旗\t權重\tcue\t命中的正常訊息")
    for r in rows:
        print("\t".join(str(x) for x in r[:6]) + "\t" + ",".join(r[6]))


if __name__ == "__main__":
    main()
