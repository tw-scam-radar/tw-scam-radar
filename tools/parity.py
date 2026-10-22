"""確認網頁版引擎（web/radar.js）跟 Python 版（tools/check.py）判斷完全一致。

用法：python tools/parity.py [測試檔 ...]
預設比對 tests/cases.yaml 與 private/tests/holdout.yaml（不公開的獨立考卷，沒有就只比對前者）；需要 Node。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from check import Engine
from common import ROOT, TESTS, load_yaml

NODE_SCRIPT = r"""
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const [radarPath, domainsPath, urlsPath, inPath, enginePath] = process.argv.slice(2);
const { Engine } = await import(pathToFileURL(enginePath).href);
const eng = new Engine(JSON.parse(readFileSync(radarPath, "utf8")), readFileSync(domainsPath, "utf8"), readFileSync(urlsPath, "utf8"));
const cases = JSON.parse(readFileSync(inPath, "utf8"));
const out = cases.map((c) => { const r = eng.analyze(c.text); return { id: c.id, level: r.level, score: r.score, top: r.methods[0]?.id ?? null }; });
process.stdout.write(JSON.stringify(out));
"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    holdout = ROOT / "private" / "tests" / "holdout.yaml"
    files = sys.argv[1:] or [str(TESTS)] + ([str(holdout)] if holdout.exists() else [])
    cases = [c for f in files for c in load_yaml(f)]
    eng = Engine()
    py = {c["id"]: eng.analyze(c["text"]) for c in cases}
    dist = ROOT / "dist"
    with tempfile.TemporaryDirectory() as td:
        inp, js = Path(td) / "in.json", Path(td) / "run.mjs"
        inp.write_text(json.dumps([{"id": c["id"], "text": c["text"]} for c in cases], ensure_ascii=False), encoding="utf-8")
        js.write_text(NODE_SCRIPT, encoding="utf-8")
        out = subprocess.run(["node", str(js), str(dist / "radar.json"), str(dist / "bad_domains.txt"),
                              str(dist / "bad_urls.txt"), str(inp), str(ROOT / "web" / "radar.js")],
                             capture_output=True, text=True, encoding="utf-8")
    if out.returncode:
        print(out.stderr)
        sys.exit(1)
    diff = 0
    for r in json.loads(out.stdout):
        p = py[r["id"]]
        ptop = p["methods"][0]["id"] if p["methods"] else None
        if (p["level"], p["score"], ptop) != (r["level"], r["score"], r["top"]):
            diff += 1
            print(f"不一致 {r['id']}：Python {p['level']}/{p['score']}/{ptop}　JS {r['level']}/{r['score']}/{r['top']}")
    print(f"比對 {len(cases)} 則，不一致 {diff} 則")
    sys.exit(1 if diff else 0)


if __name__ == "__main__":
    main()
