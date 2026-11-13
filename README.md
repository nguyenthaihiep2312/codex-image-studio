# Codex Image Studio

Tạo ảnh bằng công cụ `image_generation` của Codex, gọi thẳng máy chủ Codex bằng tài khoản ChatGPT bạn đã đăng nhập trong Codex. Repo gồm hai cách dùng:

- **Web studio** chạy trên máy: giao diện chat giống Codex, đính kèm nhiều ảnh, chỉnh sửa nối tiếp, xem hạn mức còn lại.
- **Script dòng lệnh** `codex-image-gen.py` để tạo ảnh nhanh từ Terminal.

Ảnh được lưu vào `<thư mục dự án>/images/renders/`. Mọi yêu cầu gửi với `store: false`, nên không tạo cuộc trò chuyện nào trên ChatGPT hay Codex.

## Yêu cầu

- Python 3.8 trở lên. Chỉ dùng thư viện chuẩn, không cần `pip install`.
- Codex đã đăng nhập bằng tài khoản ChatGPT (`codex login`). Thông tin đăng nhập được đọc từ `~/.codex/auth.json`, hoặc `$CODEX_HOME/auth.json` nếu bạn đặt biến `CODEX_HOME`.

## Web studio

```bash
cd ~/du-an-cua-ban
python3 /đường/dẫn/codex-image-studio/server.py
```

Trình duyệt tự mở `http://127.0.0.1:8765`. Ảnh được lưu vào `images/renders/` của thư mục bạn đang đứng.

| Tuỳ chọn | Ý nghĩa |
|---|---|
| `-p, --project DIR` | Thư mục dự án để lưu ảnh (mặc định: thư mục hiện tại) |
| `--port N` | Cổng chạy server (mặc định: 8765) |
| `--no-browser` | Không tự mở trình duyệt |

Tính năng:

- Danh sách đoạn chat ở thanh bên, lưu trong trình duyệt.
- Đính kèm nhiều ảnh bằng nút **+**, kéo thả hoặc dán (Cmd+V). Ảnh lớn được thu nhỏ còn tối đa 2048px trước khi gửi.
- Chọn model (mặc định `gpt-5.6-sol`, danh sách lấy từ Codex), kích thước và chất lượng.
- Xem trước ảnh mờ trong lúc tạo, có nút dừng giữa chừng.
- Chỉnh sửa nối tiếp: ảnh vừa tạo được tự gửi kèm lượt sau, nên chỉ cần gõ kiểu "đổi nền thành màu xanh".
- Phóng to ảnh, tải về, copy đường dẫn file.
- Khung hạn mức: tên gói, phần trăm còn lại của cửa sổ 5 giờ và 7 ngày, giờ làm mới. Tự cập nhật sau mỗi lần tạo ảnh và mỗi phút.

## Script dòng lệnh

```bash
./codex-image-gen.py "một chiếc xe đạp đỏ trên bãi biển lúc hoàng hôn"
./codex-image-gen.py -p ~/du-an -i mau1.png -i mau2.jpg "ghép hai ảnh này thành một poster"
```

| Tuỳ chọn | Ý nghĩa |
|---|---|
| `-m, --model` | Model (mặc định: `gpt-5.6-sol`) |
| `-p, --project` | Thư mục dự án (mặc định: thư mục hiện tại) |
| `-i, --image` | Ảnh mẫu, lặp lại để đính kèm nhiều ảnh |
| `-n, --name` | Gợi ý tên file (mặc định: lấy từ prompt) |
| `--size` | `1024x1024`, `1536x1024`, `1024x1536` hoặc `auto` |
| `--quality` | `low`, `medium`, `high` hoặc `auto` |
| `--format` | `png` (mặc định), `jpeg` hoặc `webp` |
| `--timeout` | Số giây chờ tối đa (mặc định: 300) |

Script in ra đường dẫn của từng ảnh đã lưu. Tên file có dạng `YYYYMMDD-HHMMSS-<tóm-tắt-prompt>.png`.

## Cấu trúc

| File | Vai trò |
|---|---|
| `codex_client.py` | Gọi máy chủ Codex, đọc luồng kết quả, lấy hạn mức, lưu ảnh. Web và CLI dùng chung. |
| `server.py` | Server web cục bộ: trang giao diện, `/api/generate`, `/api/usage`, `/api/config`, phục vụ ảnh trong `/renders/`. |
| `static/index.html` | Giao diện web (HTML, CSS, JS trong một file). |
| `codex-image-gen.py` | Script dòng lệnh. |

## Lưu ý

- **API không chính thức.** Repo gọi các endpoint nội bộ mà Codex dùng (`chatgpt.com/backend-api/codex/responses` và `/wham/usage`). OpenAI có thể thay đổi chúng bất cứ lúc nào mà không báo trước.
- **Tính vào hạn mức ChatGPT.** Mỗi ảnh được trừ vào hạn mức của gói ChatGPT, giống như khi tạo ảnh trong Codex.
- **Chỉ chạy trên máy của bạn.** Server chỉ nghe ở `127.0.0.1` vì nó dùng token đăng nhập của bạn. Đừng mở cho máy khác truy cập.
- **Kích thước có thể bị bỏ qua.** Máy chủ đôi khi trả về 1536×1024 dù bạn chọn kích thước khác. Muốn khung ảnh cụ thể thì ghi tỉ lệ ngay trong prompt.
- **Lỗi 401.** Phiên đăng nhập đã hết hạn. Mở `codex` một lần để Codex tự làm mới rồi thử lại. Repo không tự làm mới token, để tránh làm Codex bị đăng xuất.
- **Không có bản sao trên mạng.** Ảnh chỉ nằm trong `images/renders/`. Xoá file là mất.
