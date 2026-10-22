"""把 work/blind/ 底下的盲測考卷（YAML）轉成 JSON，給 worker/test/eval_api.mjs 用。"""
import json

from common import ROOT, load_yaml


def main():
    for p in (ROOT / "work" / "blind").glob("*.yaml"):
        rows = [{"id": r["id"], "text": r["text"]} for r in load_yaml(p)]
        p.with_suffix(".json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        print(f"{p.name} → {p.with_suffix('.json').name}（{len(rows)} 則）")


if __name__ == "__main__":
    main()
