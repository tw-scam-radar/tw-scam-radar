"""共用：讀手法庫、正規化文字。

判讀只需要 Python 標準函式庫：沒有安裝 PyYAML 時，改讀打包好的 web/data/radar.json。
（維護手法庫、跑檢查與測試才需要 PyYAML。）
"""
import json
import re
import unicodedata
from pathlib import Path

try:
    import yaml
except ImportError:  # 一般使用者的電腦不一定有
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
METHODS_DIR = ROOT / "data" / "methods"
COMMON_FLAGS = ROOT / "data" / "red_flags_common.yaml"
BUNDLE = ROOT / "web" / "data" / "radar.json"
TESTS = ROOT / "tests" / "cases.yaml"

CATEGORIES = ["投資理財", "借貸金融", "冒名恐嚇", "網購交易", "感情交友",
              "求職打工", "中獎優惠", "帳號資安", "其他"]
CHANNELS = ["電話", "簡訊", "LINE", "LINE 群組", "臉書", "臉書廣告", "IG", "Threads",
            "YouTube", "TikTok", "Telegram", "交友軟體", "電子郵件", "網購平台", "二手平台",
            "求職網站", "搜尋引擎廣告", "網站彈窗", "實體", "其他"]
STAGES = ["接觸", "取信", "製造情境", "要求行動", "收網後"]
EVIDENCE = ["🟢", "🟡", "🔴"]


def load_yaml(path):
    if yaml is None:
        raise RuntimeError("這個功能需要 PyYAML：pip install pyyaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def _bundle():
    return json.loads(BUNDLE.read_text(encoding="utf-8"))


def load_methods():
    if yaml is None:
        return [dict(m, _file="radar.json") for m in _bundle()["methods"]]
    methods = []
    for p in sorted(METHODS_DIR.glob("*.yaml")):
        for m in load_yaml(p):
            m["_file"] = p.name
            methods.append(m)
    return methods


def load_common_flags():
    if yaml is None:
        return _bundle()["common_flags"]
    return load_yaml(COMMON_FLAGS) if COMMON_FLAGS.exists() else []


def normalize(text):
    """全形轉半形、英文轉小寫、臺→台、拿掉空白，讓關鍵詞比對不受寫法影響。"""
    t = unicodedata.normalize("NFKC", text or "")
    t = t.lower().replace("臺", "台")
    return re.sub(r"\s+", "", t)


# 關鍵詞前面幾個字內出現這些詞，代表是在「提醒不會這樣做」，不算命中。
# 例：「本行不會要求您匯款至個人帳戶」
NEGATION_RX = re.compile(r"(不會|不需|不用|不必|無須|毋須|請勿|切勿|勿|不要|不得|不可|不能|絕不|從不|"
                         r"並未|並沒有|沒有|未曾|禁止|謹防|小心|慎防|提防|避免|防範|"
                         r"不收|不含|不接受|不提供|不經手)")
NEGATION_WINDOW = 20
CLAUSE_BREAK = re.compile(r"[,.!?;:、。\n]")


def _negated(s, start):
    """只看同一個子句（往前到最近的標點為止，最多 20 字）裡有沒有否定詞。"""
    before = s[max(0, start - NEGATION_WINDOW):start]
    before = CLAUSE_BREAK.split(before)[-1]
    return NEGATION_RX.search(before) is not None


def compile_cue(cue):
    """re: 開頭是正規表示式，其他是一般關鍵詞。回傳 (說明, 比對函式)。

    比對函式只在「至少有一處出現、而且前面沒有否定詞」時回傳 True。
    """
    if cue.startswith("re:"):
        # 樣式只做全形轉半形，不拿掉空白（正規表示式裡的符號要保留）
        pattern = unicodedata.normalize("NFKC", cue[3:]).replace("臺", "台")
        rx = re.compile(pattern, re.IGNORECASE)
        return cue, lambda s, rx=rx: any(not _negated(s, m.start()) for m in rx.finditer(s))
    key = normalize(cue)

    def match(s, key=key):
        i = s.find(key)
        while i != -1:
            if not _negated(s, i):
                return True
            i = s.find(key, i + 1)
        return False
    return cue, match
