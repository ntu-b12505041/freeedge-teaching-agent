# Teaching Monster 加分作業自動產片 API

這個專案會接收競賽平台的 JSON 題目，自動生成英文教學影片、字幕與投影片 PDF，並回傳下載連結。

## 目前預設：免費 Edge TTS

系統預設使用 `TTS_PROVIDER=edge`，會走 Microsoft Edge Read Aloud 的 neural voice，不需要 OpenAI API key，也不會花 OpenAI API 費用。

如果你未來想改用付費 OpenAI TTS，才需要設定：

```powershell
$env:TTS_PROVIDER = "openai"
$env:OPENAI_API_KEY = "你的 key"
```

平常省錢測試請維持：

```powershell
$env:TTS_PROVIDER = "edge"
```

## 你需要先做的事

1. 到 Teaching Monster 註冊/登入並建立隊伍。
2. 在課程加分 Google Form 填隊伍資料：`https://forms.gle/trhPo1C61g2XWk9x7`。
3. 準備一個可公開連線的 API 網址。正式評測不能只跑在本機。
4. 正式參賽前確認影片下載連結至少 48 小時有效。

## 本機產生測試影片

```powershell
cd "C:\Users\yu891\OneDrive\文件\TEACHING monster"
$env:TTS_PROVIDER = "edge"
.\make_test_video.ps1
```

輸出會在：

```text
output\local-test\video.mp4
output\local-test\subtitles.vtt
output\local-test\slides.pdf
```

## 本機啟動 API

```powershell
.\run_local.ps1
```

服務會開在：

```text
http://127.0.0.1:8000
```

測試 API：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/generate `
  -ContentType "application/json" `
  -Body '{"request_id":"local-test","course_requirement":"Explain binary search to a high school student.","student_persona":"10th grader, knows basic arrays but not recursion."}'
```

回傳格式：

```json
{
  "video_url": "https://your-domain/static/local-test/video.mp4",
  "subtitle_url": "https://your-domain/static/local-test/subtitles.vtt",
  "supplementary_url": ["https://your-domain/static/local-test/slides.pdf"]
}
```

## 正式部署提醒

- `PUBLIC_BASE_URL` 必須設成外部可以下載檔案的 HTTPS 網址。
- 影片規格：MP4、1280x720、AAC audio，符合至少 720p 和 16kHz 的要求。
- 競賽要求全自動，所以正式題目不能人工改腳本、剪片或配音。
- 若使用 Edge TTS、OpenAI 或其他外部服務，文件中要揭露，因為規則要求外部模型/付費服務透明。

## 目前策略

- 教學設計：先分析學生程度，再生成 hook、學習目標、逐步講解、例子、常見誤解和 checkpoint。
- 影片形式：乾淨的投影片風格，畫面以概念圖、流程圖、對照圖和小例子為主。
- 聲音：預設免費 Edge neural voice `en-US-GuyNeural`；可用 `EDGE_TTS_VOICE` 換聲音。
- 引用：依領域自動附上 OpenStax、College Board AP 或 Princeton IntroCS 等教育來源。
