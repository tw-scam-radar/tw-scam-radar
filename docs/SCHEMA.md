# 手法庫資料格式（v1）

手法庫是整個系統的核心：skill、網頁版、自動更新都讀這一份。
一類詐騙一筆資料，存在 `data/methods/<大類>.yaml`，每個檔案是一個 YAML 清單。

寫作原則：

- **受害者視角**：寫「你會看到、聽到什麼」和「哪裡不對勁」，不寫詐團的完整話術或操作步驟。
- **引用或棄權**：每一筆都要有 `sources`。查不到的欄位留空清單 `[]`，不要用推測補。
- **繁體中文、台灣用語、全形標點**（，。、「」：？！）。
- 不放任何個人資料：真名、帳號、電話、帳戶號碼、LINE ID 一律不寫（官方公布的詐騙網址除外，那放在官方名單，不放手法庫）。

## 欄位

```yaml
- id: fake-investment-group        # 英文小寫＋連字號，全庫唯一
  name: 假投資：投資群組、老師帶單   # 民眾會用的叫法
  aliases: [股票老師, 飆股群組]      # 165、新聞、網友的其他叫法
  category: 投資理財                 # 只能用下面「大類」之一
  summary: 一句話：對方假裝成誰、最後要你做什麼。
  status: active                     # active（還在流行）／declining（變少）／historical（已少見）
  first_seen: "2018"                 # 查得到最早報導的年份；查不到就留 ""
  channels: [臉書廣告, LINE 群組]    # 只能用下面「管道」詞表
  pretend_to_be: [投資老師, 助理]    # 對方假冒的身分
  stages:                            # 受害者依序會經歷什麼
    - stage: 接觸                    # 接觸／取信／製造情境／要求行動／收網後
      what_you_see: 在臉書看到名人推薦的免費飆股群組廣告。
  opener_examples:                   # 改寫過的典型開場，每句 40 字內，不是原文
    - 加入群組就送三支飆股，名額有限。
  red_flags:
    - id: guaranteed-return          # 英文小寫＋連字號
      text: 保證獲利、穩賺不賠        # 給民眾看的白話
      cues: ["保證獲利", "穩賺", "re:(零|無)風險"]   # 比對用關鍵詞；re: 開頭表示正規表示式
      weight: 3                      # 1＝可疑、2＝很可疑、3＝幾乎確定
  final_ask:                         # 對方最後要你做的事
    - 把錢匯到「專員」給的個人帳戶。
  verify:                            # 正確查證方式，優先給官方管道
    - 撥 165 反詐騙諮詢專線查詢。
  safe_lookalikes:                   # 容易誤判的正常情況，以及怎麼分辨
    - 證券商正式通知只會請你登入官方 App，不會給你個人帳戶匯款。
  if_already_happened:               # 已經被騙或已經給出去了，該怎麼做
    - 立刻打 165 或到派出所報案，並請銀行止付。
  prevalence:                        # 流行程度（必須附來源）
    note: 2026 年 6 月 165 財損排名第一。
    source_url: https://...
  sources:
    - title: 文章或頁面標題
      publisher: 刑事警察局
      date: "2026-06-30"             # YYYY-MM-DD；只有年月就寫 YYYY-MM
      url: https://...
      level: L1                      # L1＝官方／一手；L2＝主要媒體
      supports: [red_flags, final_ask]   # 這個來源支撐哪些欄位
  evidence: 🟢                       # 🟢 至少兩個獨立來源一致／🟡 單一來源／🔴 查不到可靠來源
  related: [fake-investment-app]     # 相關手法的 id
  updated: "2026-10-22"
```

## 大類（category）

投資理財、借貸金融、冒名恐嚇、網購交易、感情交友、求職打工、中獎優惠、帳號資安、其他

## 管道（channels）

電話、簡訊、LINE、LINE 群組、臉書、臉書廣告、IG、Threads、YouTube、TikTok、Telegram、交友軟體、電子郵件、網購平台、二手平台、求職網站、搜尋引擎廣告、網站彈窗、實體、其他

## 共通紅旗（data/red_flags_common.yaml）

跨手法都適用的紅旗（例如「要你操作 ATM」「要你提供簡訊驗證碼」），格式同 `red_flags`，另加：

```yaml
- id: atm-operation
  text: 要你到 ATM 操作「解除設定」或「認證」
  cues: ["ATM", "解除分期", "re:解除.{0,4}(設定|扣款)"]
  weight: 3
  why: ATM 沒有解除分期、取消扣款或身分認證的功能。
  sources: [...]
```

## 測試案例（tests/cases.yaml）

```yaml
- id: t-0001
  text: 訊息原文或改寫
  label: scam                 # scam／legit
  method_id: fake-investment-group   # 已知屬於哪一類；不確定就留 ""
  origin: quoted              # quoted＝官方或新聞引用的原文；synthetic＝自己寫的
  source: {title: , url: , date: }   # quoted 必填；synthetic 留空
  note: ""
```
