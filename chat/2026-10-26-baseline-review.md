# Codex Task 001 — Step 0 基線審查紀錄

日期：2026-10-26

> 對話保存範圍：本檔是本工作階段可見對話的忠實摘要，不是逐字稿。未保存任何實際媒體 URL、Cookies、token、授權標頭或帶簽章串流 URL。

## 使用者原意摘要

- 完整閱讀 `AGENTS.md`、`arch-v0.1.md`、`steps-v0.1.md`、`video-get.py`，執行 Step 0，建立既有行為基線。
- 以閱讀、分析與驗證為主，不修改程式或既有架構文件。
- 查明 HLS Master/Media Playlist、yt-dlp 格式探索與最佳畫質選擇，以及五秒靜默停止的限制。
- 只更新 `chat/`，遮蔽敏感資料；完成後 commit 並 push 目前分支。

## 範圍與決策

- 已啟用環境內的 Ponytail full，採用「不新增自製 HLS parser、不新增測試框架、不拆模組」的最小工程原則。
- 已完整閱讀四個指定檔案，並搜尋 `kind`、`yt_command`、`main` 的所有專案內呼叫點。它們都只在單檔 `video-get.py` 內使用；本輪沒有 caller、fixture、config 或 export 需要變更。
- 本輪未修改 `video-get.py`、`arch-v0.1.md`、`steps-v0.1.md`，也未使用真實或敏感媒體 URL。

## A. 現有架構評價

合理部分：

- `video-get.py:51-59` 先確認 yt-dlp 存在；非 `--spy` 時先讓 yt-dlp 處理網頁。成功立即結束，失敗才啟動瀏覽器，符合「yt-dlp 是下載引擎、瀏覽器只是探索輔助」的定位。
- `video-get.py:61-65,69-110` 對 Playwright 缺失、瀏覽器啟動／操作失敗有明確非零回傳；頁面導覽失敗則保留監聽機會。
- `video-get.py:78-89` 監聽 HTTP responses，以 URL path 或 Content-Type 辨識 HLS、DASH、直接影片並依完整 URL 去重。
- `video-get.py:112-131` 沒有候選時回傳 1；有候選時按 HLS、DASH、VIDEO 排序並要求使用者選擇；`q` 安全取消且不下載；所選 URL、Referer、輸出目錄、選用的瀏覽器 Cookies 參數交給 yt-dlp。
- `video-get.py:30-39` 沒有自行下載、合併或排序串流；yt-dlp 仍負責實際下載，符合架構目標。

確定限制：

- 目前「識別 HLS」只表示 URL/Content-Type 像 HLS；程式不讀 response body，因此無法識別 Master Playlist 與 Media Playlist。
- 候選在下載前沒有用 yt-dlp `-F` 或其他方式驗證可解析、可存取及有哪些格式。實際驗證只發生在使用者選完後的下載命令。
- 若選到 Master Playlist，現有命令沒有指定 `-f`，yt-dlp 預設會選其認為最佳的可用格式；這是合理且最簡單的行為。若只選到單畫質 Media Playlist，yt-dlp 只能看到該播放清單公開的內容，不能可靠推導未提供的其他 rendition。
- Playwright 是全新 context（`video-get.py:75`）；瀏覽器工作階段的 Cookie/授權狀態沒有傳給 yt-dlp。`--cookies-browser` 讀取的是指定之日常瀏覽器 Cookie，不是這個 Playwright context。程式只額外傳 Referer，故需要其他短效 header、Origin 或 context Cookie 的候選可能偵測到但下載失敗。

## 畫質研究結論

1. **現有程式不能區分 HLS Master 與 Media Playlist。** `kind()` 只檢查 `.m3u8` 或 MPEGURL Content-Type（`video-get.py:18-27`）。依 HLS 規範，Master 的關鍵是內容中的 `#EXT-X-STREAM-INF` 等 Master tags；Media Playlist 則列出 Media Segments。只看 URL 名稱或觀察到的解析度字串不充分。
2. **yt-dlp 已有格式探索與選擇能力。** 官方文件定義 `-F/--list-formats` 列出可用格式；未傳格式選項時，預設嘗試下載最佳可用品質，通常等價於 `bestvideo*+bestaudio/best`，必要時由 FFmpeg 合併。格式資訊是否完整仍取決於來源 manifest/網站提供的 metadata。
3. **取得 Master Playlist 時，最簡單方案是直接交給 yt-dlp。** 可先用同一組必要 headers/Cookies 執行 `yt-dlp -F <master>` 供確認；真正下載不必新增 `-f best`，沿用 yt-dlp 預設即可。官方也明確指出 `-f best` 只選預先合併格式，往往不是最佳選項。
4. **只取得單一 Media Playlist 時，沒有通用且可靠的方法尋找其他畫質。** 可繼續監聽、讓使用者在播放器切換畫質，或尋找實際被頁面取得的 Master/API 資料；不得依 `240p`/`480p` 等字串猜 URL。伺服器若提供多組編碼，規範建議提供列出 variants 的 Master，但這不是可由 client 保證或倒推出來的資訊。
5. **五秒靜默不是「探索完成」。** `video-get.py:97-105` 在第一個候選後，只要候選 URL 數五秒不變便退出；它可能早於 ABR 升檔、使用者切換畫質、廣告結束、延遲載入或另一段影片開始。相反地，分段 URL 未被列為候選（`.ts` 不在 matcher），所以持續播放分段也不會重設計時。這個停止條件只能表示「五秒沒有新增可辨識 URL」，不能表示已找到最高畫質。
6. **有比自製 HLS parser 更小的方案。** 先把觀察到的 manifest 交給 yt-dlp `-F`/預設格式選擇；下一輪若必須判別 manifest 性質，只需取得少量 playlist 文字並檢查標準 tag，或直接以 yt-dlp 的格式列舉結果作為使用者證據，不需要實作完整 parser、下載器或 bitrate sorter。

參考資料：

- yt-dlp 官方 README（Format Selection、`-F`、預設最佳格式）：https://github.com/yt-dlp/yt-dlp/blob/master/README.md
- yt-dlp 官方程式碼對常見 `-f best` 誤用的警告：https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/__init__.py
- IETF RFC 8216（Master/Media Playlist 與 `EXT-X-STREAM-INF`）：https://datatracker.ietf.org/doc/html/rfc8216

## B. 問題清單

### P0

- 無已確認 P0。基礎語法、CLI 建立與直接成功分支可執行；沒有證據顯示核心程式完全失效。

### P1

1. **沒有辨識或驗證 playlist 性質與可用格式**
   - 位置：`video-get.py:18-27,78-85,115-131`
   - 條件：瀏覽器觀察到任何 `.m3u8`，尤其同時觀察到 Master、Media 或多個 rendition 時。
   - 影響：全部只標成 HLS；預設第一個 HLS 只是字典插入順序，可能是低畫質 Media Playlist。使用者在下載前看不到 yt-dlp 實際可解析的格式，也不能據此確認最高可用畫質。

2. **第一個候選後五秒靜默即提前停止**
   - 位置：`video-get.py:94-105`
   - 條件：第一個媒體候選出現後，較高 rendition、Master 或另一個主要來源晚於五秒才請求。
   - 影響：遺漏後續候選；尤其 ABR 初始低畫質時會系統性降低找到較佳來源的機會。五秒靜默不可作為最高畫質證據。

3. **瀏覽器授權狀態傳遞不完整**
   - 位置：`video-get.py:75,84,130`
   - 條件：manifest 需要 Playwright context Cookie、Origin、Authorization 或其他 request headers，而非只有 Referer；或登入發生在新開的 Playwright context。
   - 影響：候選可被瀏覽器播放／偵測，交給 yt-dlp 卻可能收到 401/403。這不應以猜 URL 或保存敏感 header 解決。

### P2

1. **response callback 吞掉所有例外**
   - 位置：`video-get.py:78-87`
   - 條件：Playwright header API、URL parsing 或候選紀錄發生非預期錯誤。
   - 影響：使用者只會看到漏候選，無法分辨網站無媒體與偵測器出錯。

2. **下載失敗只透傳 return code，缺少程式層級摘要**
   - 位置：`video-get.py:128-131`
   - 條件：所選候選不可存取、格式解析失敗或 yt-dlp/FFmpeg 失敗。
   - 影響：yt-dlp 通常已有 stderr，因此不是核心失效；但程式本身不區分「偵測成功」與「下載成功」。

3. **`--timeout` 未驗證正值**
   - 位置：`video-get.py:48,99`
   - 條件：使用者傳 0 或負數。
   - 影響：仍強制監聽約一秒，與「maximum listening time」語意不一致；影響較小。

## C. 最小修改方案（下一輪候選，不在本輪實作）

優先只改 `video-get.py`：

1. 對每個候選 manifest，在使用者決定前以現有 `yt-dlp` 做格式列舉／驗證，沿用相同 Referer、輸出無關參數與必要 Cookies；Master 能列出多格式時直接保留 manifest，下載仍用 yt-dlp 預設格式選擇。不要加入 `-f best`，也不要自行排序或合併。
2. 明確標示「yt-dlp 列出的可用格式」與「單一播放清單／未證實其他畫質」；若 `-F` 失敗就保留錯誤狀態，不把被 Network 看見等同可下載。
3. 移除「有候選後五秒自動 break」，最小替代是持續到既有 `--timeout`，讓使用者有時間播放或切畫質。若實測等待體驗不可接受，再加入單一、明確的手動結束方式；先不建立策略類別或多組 timeout。
4. 授權 header 問題先用真實案例確認最小必要集合；不要把全部 headers 印出或寫入 repo，也不要先做通用 session 匯出系統。

## D. 驗證結果

| 項目 | 結果 | 證據／限制 |
|---|---|---|
| `python -m py_compile video-get.py` | PASS | Python 3.11.6，exit 0。產生的 `__pycache__` 已清除。 |
| `python video-get.py --help` | PASS | exit 0；必要 positional URL 與既有 options 正常顯示。 |
| yt-dlp 可執行 | PASS | `yt-dlp --version` 回報 `2026.10.21`。 |
| Playwright Python import | PASS | import 成功；這不代表任何瀏覽器 channel 已安裝。 |
| `kind()` / `yt_command()` 最小 assertions | PASS | HLS、DASH、直接影片、忽略 `.ts`、完整參數順序皆通過。 |
| yt-dlp 原生下載成功 | PASS（模擬） | mock `subprocess.run` 回傳 0；`main()` 回傳 0，且只呼叫一次下載命令。不是網路端對端下載。 |
| yt-dlp 原生下載失敗後 fallback | NOT TESTED | 靜態確認 `returncode != 0` 會進入 Playwright；未用真實站點或瀏覽器驗證。 |
| `--spy` | NOT TESTED | 靜態確認會跳過第一個 `subprocess.run`；未啟動實機 browser channel。 |
| 沒有偵測到媒體 | NOT TESTED | 靜態確認回傳 1；未做瀏覽器端對端測試。 |
| 多個媒體來源 | NOT TESTED | 靜態確認依 HLS/DASH/VIDEO 排序並提示選擇；未做端對端測試。 |
| 使用者取消 | NOT TESTED | 靜態確認輸入 `q` 回傳 0，且不執行最後下載。 |
| yt-dlp 候選下載失敗 | NOT TESTED | 靜態確認直接回傳子程序非零碼；沒有真實失敗案例。 |
| Master/Media 判別 | FAIL | 現有程式完全不讀 playlist 內容，兩者一律標為 HLS。 |
| 下載前格式／可下載性驗證 | FAIL | 選擇前未執行 `-F` 或等效驗證。 |
| 瀏覽器端對端 | BLOCKED | 本輪沒有合法、可重現且不含敏感資訊的測試網站／授權案例；未確認 Edge/Chrome/Chromium binary。 |

首次執行命令時受 managed sandbox 阻擋 `python.exe`/`yt-dlp.exe`；取得受控核准後，相同命令才成功。這是環境限制，不是程式 FAIL。

## E. 下一輪建議

下一個最值得做的任務：**Step 1 — 用 yt-dlp 驗證 manifest 並呈現格式能力，不自製 HLS parser。**

最小驗收標準：

1. 使用一個合法、非敏感、可重現的 HLS Master 測試來源，候選在下載前可由 yt-dlp 列出至少兩個不同格式／解析度。
2. 選擇該 Master 後，不指定 `-f best`，由 yt-dlp 預設選擇最佳可用組合；實際命令與回傳碼可驗證，且不洩漏敏感 URL/header。
3. 使用一個 Media Playlist，介面明確說明只能確認該來源，不宣稱它是網站最高畫質，也不生成猜測 URL。
4. `--spy`、無候選、多候選、取消、下載失敗的既有回傳行為不退化；至少用一個小型可執行檢查覆蓋新增分支，不新增測試框架。
5. 原生 yt-dlp 成功仍不啟動 Playwright。

## 工作階段代理回覆摘要

- 代理先說明會完整讀取規範、盤點流程、做最小執行驗證與官方能力查核。
- 發現 PowerShell 初次以錯誤編碼顯示中文後，改用 UTF-8 重讀，未以亂碼作判斷。
- 啟用 Ponytail 後將範圍限制在基線、證據與工作紀錄；不新增 parser、抽象層或測試框架。
- 執行命令首次受沙箱限制，依規則申請受控執行；成功後明確區分命令 PASS、模擬 PASS、靜態分析與端對端未測。
- 最終決策是本輪不修程式；最優先的後續改動是重用 yt-dlp 格式探索，並處理五秒過早停止，而不是自行推測高畫質 URL。

---

# Codex Task 001 — Step 1 執行紀錄

> 對話保存範圍：以下是同日後續工作階段可見對話與決策摘要，不是逐字稿。公開測試來源不含 Cookie、token、授權資訊或簽章參數。

## 使用者原意與範圍

- 使用者要求執行 `steps-v0.1.md` 的 Step 1。
- 延續 Ponytail full；只修改 `video-get.py` 與本紀錄，不新增依賴、模組、完整 HLS parser 或測試框架。
- Step 2 的五秒停止條件刻意保留，避免本輪混入另一項控制流程變更。

## 實作決策

1. `kind()` 可接收已取得的 response body，但只辨識 HLS 標準標記：
   - `#EXT-X-STREAM-INF`／`#EXT-X-I-FRAME-STREAM-INF` → `HLS master`
   - `#EXTINF:`／`#EXT-X-TARGETDURATION:` → `HLS media`
   - body 不可得或無法判斷 → 保留 `HLS`
2. Playwright 只對已依 URL／Content-Type 判為 HLS 的 response 讀 body。body 讀取失敗時仍保留候選，不讓 manifest 分類影響既有探索能力。
3. 使用者選定候選後，先以相同 Referer／Cookies 參數執行 `yt-dlp --list-formats`。格式驗證失敗時不嘗試下載，並透傳 yt-dlp return code。
4. 驗證成功後仍不傳 `-f`，由 yt-dlp 預設格式選擇與 FFmpeg 合併；沒有自行排序 bitrate 或解析 rendition URL。
5. 若判定為 `HLS media`，下載前明示可能存在其他畫質，但不能安全推導。

## 驗證結果

| 項目 | 結果 | 證據／限制 |
|---|---|---|
| `python -m py_compile video-get.py` | PASS | exit 0 |
| `python video-get.py --help` | PASS | exit 0，CLI 未新增選項 |
| Master／Media／未知 HLS assertions | PASS | 標準 tag 的最小 bytes fixtures 均得到預期分類 |
| `yt_command(..., list_formats=True)` | PASS | 參數包含 `--no-playlist --list-formats`，並保留 Referer／Cookies |
| 公開 Master 實際分類 | PASS | 讀取 Apple 公開 HLS 範例的 6,289-byte manifest，判為 `HLS master` |
| 公開 Master `yt-dlp -F` | PASS | 實際列出 audio-only 與 270p、360p、432p、540p、720p、1080p 多組格式；未下載媒體 |
| yt-dlp 預設選擇模擬 | PASS | `--simulate` 選到 `8366+aud2-English`、1920x1080；這只證明該公開 Master 當下提供的格式與預設選擇 |
| Playwright 端對端 | NOT TESTED | 未啟動瀏覽器、播放頁面或驗證 response callback 的實站事件時序 |
| 單一 Media Playlist 實站 | NOT TESTED | 分類與提示以最小 fixture 驗證；未主張能找到未公開的其他畫質 |

公開測試來源：`https://devstreaming-cdn.apple.com/videos/streaming/examples/img_bipbop_adv_example_ts/master.m3u8`。此 URL 無 query、簽章或授權資訊。

## 本輪可見代理回覆摘要

- 代理說明先重讀規範、確認 caller 與風險，再將修改限制在 manifest 分類與 yt-dlp 格式驗證。
- 初版實作後發現 response body 若讀取失敗會連候選一起遺失，因此立即改為退回一般 `HLS`，保留既有行為。
- 公開 Master 驗證顯示 yt-dlp 能從單一 Master 列出最高至 1080p 的多組格式，且不需要依瀏覽器已觀察到的 rendition 猜測 URL。

## 未解事項

- Step 2 的五秒靜默停止仍可能漏掉較晚出現的 Master 或 rendition。
- Playwright context 的授權狀態仍未完整傳給 yt-dlp；本輪沒有真實授權案例，未擴張成 header/session 匯出功能。
- `response.body()` 在各網站、長時間直播及不同 Playwright browser channel 的實際行為仍需 Step 3 端對端驗證。
