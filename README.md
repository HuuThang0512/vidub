# ViDub 🎬

Công cụ chạy trên máy Windows: cho video vào, ra video có **phụ đề tiếng Việt** và **lồng tiếng Việt**.

- 🎧 Nhận giọng nói bằng **Whisper**, chạy offline
- 🌐 Dịch bằng **Google Gemini**, dùng API key miễn phí của chính bạn
- 🗣️ Đọc bằng **25 giọng VieNeu**, chạy offline, giọng tự nhiên; hoặc **Edge TTS** với hàng trăm giọng
- 🎨 Tùy chỉnh phụ đề: font, cỡ chữ, màu chữ, viền, hộp nền, vị trí, tự chia câu dài, làm mờ phụ đề gốc
- ⬆️ Có nút cập nhật bản mới ngay trong app

## Cài đặt (Windows 10/11)

1. Vào trang này, bấm nút xanh **Code → Download ZIP**.
2. Giải nén vào một thư mục cố định, ví dụ `D:\ViDub`. **Không** để trong Downloads hay Desktop.
3. Bấm đúp **`Cai_dat.bat`** rồi chờ khoảng 10–20 phút cho tới khi hiện chữ **CAI DAT XONG**. Máy cần có mạng, tool tự tải khoảng 2–3GB.
4. Trên Desktop sẽ có biểu tượng **ViDub**. Bấm đúp để mở app.

> Nếu Windows hiện cảnh báo *"Windows protected your PC"*: bấm **More info → Run anyway**.

## Lấy API key để dịch (miễn phí)

1. Vào https://aistudio.google.com/app/apikey và đăng nhập Google.
2. Bấm **Create API key**, rồi copy key.
3. Trong ViDub, dán key vào ô **Google API key**, bấm **Lưu key**.

Key được lưu trên máy bạn (file `config.json`), không gửi đi đâu khác ngoài Google.

## Cách dùng

1. Kéo thả video vào app. App tự nghe và chép lời.
2. Bấm **Dịch tất cả**, rồi sửa lại các câu chưa ưng trong bảng.
3. Chọn giọng đọc và kiểu phụ đề. Bấm **📸 Khung hình thật** để xem trước.
4. Bấm **🎬 Xuất video**, rồi tải file MP4 hoặc SRT.

Trong lúc dùng app, **giữ cửa sổ đen "ViDub" mở**.

## Cập nhật

Khi có bản mới, góc trên app sẽ hiện nút **⬆ Cập nhật**. Bấm vào đó là xong.
Hoặc bấm đúp `Cap_nhat.bat`. Dự án và key của bạn vẫn được giữ nguyên.

## Gặp lỗi?

- Cài bị lỗi giữa chừng: bấm đúp `Cai_dat.bat` lần nữa, các bước đã xong sẽ tự bỏ qua.
- Gửi ảnh chụp màn hình cửa sổ đen cho người gửi tool.
