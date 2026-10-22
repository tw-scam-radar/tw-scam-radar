"""下載 165 官方涉詐網站名單，整理成精簡名單（data/official/bad_domains.tsv、bad_urls.tsv）。

原始 CSV 放 data/official/raw/（不放進版本紀錄）；精簡名單放進版本紀錄，網頁版與 skill 都讀它。
來源標示寫在 data/official/SOURCES.md（政府資料開放授權條款要求顯名）。
用法：python tools/update_official.py
"""
import sys
import urllib.request
from datetime import date

from check import OFFICIAL_DIR, parse_official_csvs

SOURCES = [
    {
        "file": "165_stop_resolve.csv",
        "name": "165反詐騙諮詢專線_遭停止解析涉詐網站",
        "page": "https://data.gov.tw/dataset/176455",
        "url": "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/29E8E643-88ED-4952-B21E-BD42A3B7108C/resource/5B8ED236-9DDB-496E-B6C8-5C4B823747C7/download",
    },
    {
        "file": "165_fake_investment.csv",
        "name": "165反詐騙諮詢專線_假投資(博弈)網站",
        "page": "https://data.gov.tw/dataset/160055",
        "url": "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/033197D4-70F4-45EB-9FB8-6D83532B999A/resource/A00B1802-6A4A-42B4-B842-B66A2D937DAE/download",
    },
]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    raw = OFFICIAL_DIR / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for s in SOURCES:
        req = urllib.request.Request(s["url"], headers={"User-Agent": "tw-scam-radar-updater"})
        with urllib.request.urlopen(req, timeout=120) as r:
            (raw / s["file"]).write_bytes(r.read())
        print(f"下載 {s['name']}")
    domains, urls = parse_official_csvs(raw)
    today = date.today().isoformat()
    header = f"# 165 官方涉詐名單精簡版，{today} 由 tools/update_official.py 產生。格式：網域<TAB>來源名單\n"
    (OFFICIAL_DIR / "bad_domains.tsv").write_text(
        header + "".join(f"{d}\t{l}\n" for d, l in sorted(domains.items())), encoding="utf-8")
    (OFFICIAL_DIR / "bad_urls.tsv").write_text(
        header + "".join(f"{u}\t{l}\n" for u, l in sorted(urls.items())), encoding="utf-8")
    lines = ["# 官方名單來源", "",
             f"最後更新：{today}；網域 {len(domains):,} 筆、大平台上的單一網址 {len(urls)} 筆。", ""]
    for s in SOURCES:
        lines += [f"- 內政部警政署 {date.today().year} {s['name']}（{s['page']}）"]
    lines += ["", "此開放資料依政府資料開放授權條款 (Open Government Data License) 進行公眾釋出，"
              "使用者於遵守本條款各項規定之前提下，得利用之。",
              "政府資料開放授權條款：https://data.gov.tw/license"]
    (OFFICIAL_DIR / "SOURCES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"網域 {len(domains):,} 筆、單一網址 {len(urls)} 筆")


if __name__ == "__main__":
    main()
