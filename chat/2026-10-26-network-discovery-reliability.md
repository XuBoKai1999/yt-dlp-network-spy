# Codex Task 002 — Network Discovery Reliability & Quality Selection

日期：2026-10-26

> 本檔是本工作階段可見對話、決策與結果的忠實摘要，不是逐字稿。測試中的秘密字串僅存在於記憶體 mock，未寫入本檔；未保存 Cookie、授權標頭、token、session path 或帶簽章 URL。

## 使用者原意摘要

- 以最新 `main` 與既有 Step 0／Step 1 為基礎，不重新實作 manifest 探索。
- 修正第一個候選後五秒靜默便停止的問題，提供不阻塞 Playwright 的合理手動結束方式。
- 同時有 HLS Master 與 Media 時，預設優先 Master，但不宣稱 HLS 一定優於 DASH。
- 一般 Console 不顯示可能含秘密的串流 URL，完整 URL 只保留於記憶體並交給 yt-dlp。
- 使用最小 assertions／mock 與可行的 Playwright 實測，保存紀錄後 commit、push。

## 範圍與 Ponytail 決策

- 已重讀 `AGENTS.md`、`arch-v0.1.md`、`steps-v0.1.md`、`video-get.py` 與前次 chat 紀錄，並確認 `main` 起點為 `1a86d5e`。
- 所有相關 caller 都在單檔 `video-get.py`；沒有 fixture、config、export 或依賴需要變更。
- 沒有增加 CLI 選項、執行緒、async 重構、事件系統、類別、模組或測試框架。
- 手動結束採 Playwright 已有狀態：提示使用者完成播放／切換畫質後關閉頁面或瀏覽器。主迴圈繼續以 `wait_for_timeout(1000)` pump events；偵測關閉便保留候選並離開，否則既有 `--timeout` 提供硬上限。

## A. 修改摘要

### Task A：監聽可靠性

- 刪除 `quiet_ticks`、`previous_count` 與五秒靜默 `break`。
- 監聽持續到頁面／瀏覽器被關閉或 `--timeout` 到期；沒有候選時仍走既有 return code 1。
- `wait_for_timeout` 因使用者關閉視窗而拋錯時視為正常結束；其他例外仍交給既有 browser error path。
- 沒有背景程序；離開迴圈時瀏覽器若仍連線便主動關閉。

### Task B：Master 優先

- 候選排序改為明確的小型 mapping：`HLS master` → 其他 HLS → DASH → VIDEO。
- 相同優先級保留 Python stable sort 的發現順序。
- 顯示仍要求使用者選擇；此優先級不代表 HLS 品質一定優於 DASH。

### Task C：敏感 URL

- 即時發現與候選清單都只顯示編號、媒體類型、hostname，不顯示 path、query 或 fragment。
- 完整 URL 仍只作為 `candidates` dictionary key 留在記憶體，供所選來源交給 yt-dlp。
- 導覽及瀏覽器例外只顯示 exception class，不再輸出可能包含原 URL 的完整 exception 字串。
- yt-dlp 命令加入原生 `--quiet --progress`：隱藏 extraction URL 與一般診斷前綴，保留 `-F` 格式表、下載進度與 error return code。公開 Master 實測確認 `-F` 不再印來源 URL。

## B. 測試矩陣

| 情境 | 結果 | 類型與證據 |
|---|---|---|
| `python -m py_compile video-get.py` | PASS | 實際命令，exit 0 |
| `python video-get.py --help` | PASS | 實際命令，exit 0 |
| yt-dlp 原生解析成功 | PASS | Mock：只呼叫一次 `subprocess.run`，return 0；Playwright import／launch 未進入 |
| `--spy` | PASS | Mock 與真實 Edge：直接進入 browser discovery |
| 只有 HLS Media | PASS | Mock：辨識為 `HLS media`，格式驗證後顯示無法安全推導更高畫質，下載非零碼 7 原樣回傳 |
| Master + Media | PASS | Mock：Media 先出現，Master 後出現；清單仍以 Master 為選項 1 |
| 延遲出現高畫質／Master | PASS | Mock：Media 在第 1 秒、Master 在第 7 秒出現，兩者均保留；舊五秒條件會漏掉後者 |
| 使用者關閉視窗 | PASS | Mock：page closed 後離開迴圈並保留候選；沒有背景工作 |
| 真實手動關閉視窗 | NOT TESTED | 真實 Edge 測試由 5 秒 timeout 結束，沒有人工操作 GUI 關閉 |
| 沒有候選 | PASS | Mock：正常結束 discovery 並 return 1 |
| 使用者取消 | PASS | Mock 與真實 Edge：輸入 `q`，未呼叫格式驗證或下載 |
| 格式驗證失敗 | PASS | Mock：顯示明確錯誤，只呼叫一次 yt-dlp，return code 4 原樣回傳 |
| 下載失敗 | PASS | Mock：格式驗證成功後下載回傳 7，`main()` 原樣回傳 7 |
| 敏感候選 URL | PASS | Mock 使用含秘密 path/query 的兩個 URL；capture stdout/stderr 不含秘密 path、query 或測試秘密值 |
| HLS helper／yt-dlp 命令 | PASS | Assertions：Master、Media 與 `--quiet --progress --list-formats` 命令組裝符合預期 |
| 真實 yt-dlp `-F` quiet 模式 | PASS | Apple 公開 Master；格式表保留且輸出不含來源 URL，未下載媒體 |
| 真實 Playwright response detection | PASS | Edge 從本機 `data:` 頁面 fetch Apple 公開 Master；`response.body()` 完成且顯示 `HLS master` hostname，未阻塞候選處理 |
| 直接導覽 manifest 的 fallback | PASS | Edge 導覽被瀏覽器中止、body 不可讀時仍保留為一般 `HLS` 候選 |
| 完整 Playwright → yt-dlp 實際下載 | NOT TESTED | 為避免僅為驗收下載數百 MB 公開樣本，真實流程在候選選擇處取消；不宣稱完整下載 E2E 通過 |

## C. 尚存限制

- 關閉視窗的手動終止已由 mock 驗證控制流，但尚未人工操作真實 GUI 驗證各 browser channel 的 close event 時序。
- `response.body()` 可能因下載式 navigation、長時間 live response 或網站行為失敗；程式會保留一般 `HLS` 候選，但無法分類 Master／Media。
- hostname 能安全區分不同網域；同網域多個候選只能依編號和媒體類型區分。這是刻意的安全取捨，沒有建立 path 脫敏器。
- `--quiet` 可抑制正常 yt-dlp extraction URL；外部工具在罕見錯誤訊息中是否回顯 URL 不由本程式完全控制。程式自身不再輸出候選 URL。
- Playwright context 與 yt-dlp 的完整 Cookie／header 同步仍不在本輪範圍。
- 單一 Media Playlist 仍無法證明網站沒有其他畫質，也不會猜造 URL。

## D. 最小化審查

- 刪除了兩個計時狀態與整段五秒提前停止分支；最終 `video-get.py` diff 為 17 行新增、17 行刪除。
- 排序只使用一個 local dictionary，未新增評分函式或候選類別。
- hostname 直接重用標準函式庫既有 `urlsplit`，沒有 URL 脫敏依賴。
- 手動結束重用 Playwright `page.is_closed()`、`browser.is_connected()` 與既有 timeout，沒有 Console input thread。
- yt-dlp 日誌安全重用其 `--quiet --progress`，沒有包裝或過濾 subprocess output。
- 未發現可再刪除而不犧牲關閉視窗錯誤處理、候選保留或敏感輸出防護的邏輯。

## 本輪可見代理回覆摘要

- 代理先說明會採關閉瀏覽器的 Playwright 原生狀態作為手動結束候選，並完整重讀指定檔案。
- 代理確認修改只需觸及監聽迴圈、排序鍵與兩個 URL 顯示點；實作後以記憶體 mock 驗證超過五秒才出現的 Master。
- 敏感輸出審查發現 yt-dlp 自身預設會印來源 URL，因此加入並實測 `--quiet --progress`，同時保留格式表與進度。
- 真實 Edge 測試區分兩種結果：直接導覽 manifest 時 body 不可讀但候選仍保留；由頁面 fetch 時 body 可讀並成功分類 Master。

## 未新增／未處理

- 未新增 GUI、package、模組、HLS parser、依賴、測試檔、Cookie/header 同步框架、網站 extractor 或 DRM 功能。
- 未修改 `arch-v0.1.md`、`steps-v0.1.md` 或 `.gitignore`。
