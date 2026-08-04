# Sensor Config Rules

Module: `src/sensor/` + `src/protocol/` · Entry: `src/workflows/configure.py`, `src/workflows/tune.py`
Protocol chi tiết: docs/references/ld2410c-protocol.md
**Danh mục ĐẦY ĐỦ các mục config được: docs/sensor-config/configurable-items.md**

> ## ⚠️ Nguồn sự thật cấu hình cảm biến = WEB (tab 設定)
> Cấu hình cảm biến (gate/sensitivity/resolution/no-one-duration) nằm trong **FLASH của cảm biến**,
> giữ khi tắt nguồn. Có 2 đường ghi cùng flash đó:
> - **Web (tab 設定, Web Serial)** — khuyến nghị làm nguồn chính: trực quan, có 読み込み直し (đọc lại từ flash).
> - **CLI `configure.py`** (đọc `.env`) — tuỳ chọn/legacy, dùng khi không có trình duyệt.
>
> Lần ghi cuối thắng. **KHÔNG chạy `configure.py` sau khi đã tune trên web** — nó đọc `.env` (có thể là
> giá trị cũ) rồi ghi đè flash, xoá mất cấu hình web. `run_reader` **chỉ đọc** stream, không ghi flash và
> không đọc các biến gate/sensitivity trong `.env` (những biến đó chỉ `configure.py` dùng).
> Muốn xem cấu hình hiện tại: bấm 読み込み直し trên web (đọc từ flash) — `.env` KHÔNG phản ánh cấu hình web.

## Các thành phần chính
- **Enable/End config**: mọi lệnh cấu hình phải nằm giữa Enable (0x00FF, val 0x0001) và End (0x00FE).
- ⚠️ **Xác nhận trên hardware thật (LD2410C)**: **Restart module (`0x00A3`) phải gửi TRƯỚC End config, KHÔNG được gửi sau.** Gửi Restart sau khi End config đã ACK thành công → sensor **từ chối** (ACK status fail), vì End config đã đưa sensor "resume working mode" (thoát config mode), và Restart bị coi là lệnh cấu hình cần config mode. Restart tự khiến module reboot nên **không cần gửi End config nữa** khi có restart trong chuỗi lệnh — xem `src/workflows/configure.py`.
- **Max gate + unmanned duration** (0x0060): moving gate word 0x0000, static gate word 0x0001, no-one duration word 0x0002; mỗi value 4 byte LE. Gate 1–8 hoặc 2–8 (⚠️ tài liệu Hi-Link mâu thuẫn, xem bên dưới), duration 0–65535s.
- **Sensitivity** (0x0064): distance gate word 0x0000 (0xFFFF = tất cả gate), motion word 0x0001, static word 0x0002; value 4 byte, thang 0–100.
- **Engineering mode** (0x0062 bật / 0x0063 tắt): thêm energy từng gate vào data output — dùng cho tune.
- **Read parameters** (0x0061): đọc lại cấu hình để verify.

## Hiệu chỉnh sensitivity — MANUAL là luồng KHUYẾN NGHỊ; auto-calib chỉ TÙY CHỌN
- **Khái niệm**: `energy` = năng lượng sensor **ĐO** từng gate (chỉ đọc, qua engineering mode). `sensitivity` = **ngưỡng** ta ĐẶT (`0x0064`). Luật: `energy > sensitivity` → gate báo có mục tiêu. → Ta chỉnh **sensitivity**, không "set energy".
- **Luồng khuyến nghị (manual)**: bật engineering mode (`0x0062`) → quan sát energy từng gate lúc **phòng trống** (nhiễu nền) và lúc **có người** ở vị trí máy → đặt sensitivity vào **khoảng giữa** (cao hơn nhiễu, thấp hơn energy người) → ghi flash (`0x0064`) → đọc lại (`0x0061`) xác nhận. Đây là cách chính, chính xác nhất cho môi trường cụ thể (máy CNC, người đứng yên).
- **Auto-calib nền (`0x000B`) là TÙY CHỌN**, KHÔNG bắt buộc: sensor tự đo nhiễu nền (yêu cầu phòng trống suốt quá trình) rồi tự đặt sensitivity mọi gate. Ưu: nhanh, có baseline. Nhược: ghi đè sensitivity tay, cần phòng trống tuyệt đối, ngưỡng chỉ "vừa trên nền" nên với người đứng yên lâu vẫn thường phải tinh chỉnh tay lại. Coi nó là **điểm xuất phát**, không thay thế manual.
- Dùng mặc định xuất xưởng (không đụng sensitivity, chỉ set max gate + resolution) cũng hợp lệ nếu môi trường dễ.

## Quy tắc nghiệp vụ
- Luôn verify ACK từng lệnh: status 2 byte `00 00` = success, khác = fail → raise.
  - Ví dụ: gửi 0x0060 → ACK `FD FC FB FA 04 00 60 01 00 00 04 03 02 01` (status 00 00 = OK).
- Sau khi ghi cấu hình → gọi Read parameters (0x0061), so sánh với giá trị mong muốn, in bảng đối chiếu.
  - Ví dụ: đặt max gate 8/8, unmanned 5s → read về phải ra moving=8, static=8, duration=5.
- Sensitivity mặc định thấp ở gate xa (gate 6–8 = 15). Với máy CNC người đứng gần, tăng static sensitivity gate gần giúp giữ trạng thái "stationary" ổn định.
- **Khoanh vùng phát hiện**: đặt sensitivity=100 cho gate ngoài vùng máy (vô hiệu hoá gate đó), sensitivity thấp cho gate trong vùng → lọc người đi ngang mà không cần đổi max gate. Xem ví dụ trong docs/sensor-config/configurable-items.md mục B.
- Config max gate / sensitivity / baud lưu **flash** (giữ khi tắt nguồn). Engineering mode KHÔNG lưu.
- **KHÔNG validate cứng giá trị max gate = 1 ở phía client** (rằng hợp lệ hay không). Cứ gửi lệnh xuống, đọc ACK: `00 00` = sensor chấp nhận, khác 0 = từ chối → báo lỗi rõ ràng ("sensor từ chối giá trị gate=1, thử gate≥2"). Lý do: chính tài liệu Hi-Link mâu thuẫn (§1.2.2 nói min=1, §2.2.3 nói min=2) nên không có cơ sở chắc chắn để tự chặn.

## Edge cases / Skip logic
- Không có ACK trong timeout (vd 1s) → coi như fail, retry tối đa N lần rồi báo lỗi cổng COM.
- Sai baud → không đọc được ACK: thử lại ở 256000 (mặc định) trước khi báo lỗi.
- Xen frame data output (F4 F3 F2 F1) giữa lúc chờ ACC → bỏ qua, chỉ nhận frame header FD FC FB FA.

## Ràng buộc
- Gate 0/1 KHÔNG đặt được static sensitivity (chỉ motion) — theo bảng mặc định.
- Không hard-code COM port: nhận qua `--port` hoặc `.env` COM_PORT.

## Chế độ chạy
- configure: ghi cấu hình vào flash, verify, thoát.
- tune: bật engineering mode, in energy từng gate liên tục để người vận hành quan sát và chỉnh ngưỡng (KHÔNG ghi flash trừ khi xác nhận).
