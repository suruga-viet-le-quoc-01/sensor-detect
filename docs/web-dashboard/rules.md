# Web Dashboard + Config (SPA) — Spec

App web thống nhất: **giám sát cận realtime mọi máy** + **cấu hình sensor tại chỗ qua Web Serial/BLE**.
Chạy trên Chrome/Edge desktop. Đây là spec — chưa phải code.

## Quyết định kiến trúc (ADR rút gọn)
- **Frontend**: SPA **Vue** (build nhẹ). 2 tab: Giám sát / Cấu hình.
- **Backend**: **FastAPI** (Python, dùng `oracledb`) — chỉ phục vụ tab Giám sát (đọc Oracle). Xem api-contract.md.
- **Tab Cấu hình**: **client-side thuần**, dùng Web Serial API + Web Bluetooth API chạm thẳng sensor; KHÔNG qua backend. Port protocol LD2410C sang JS — xem protocol-js.md.
- Giữ **Oracle** làm store; sensor vẫn cắm thẳng miniPC/tablet Windows (edge có dây).
- Quan hệ với docs khác: **Streamlit và GUI PyQt đều đã bỏ hẳn** — web app này là app **giám sát VÀ cấu hình duy nhất** (cấu hình qua Web Serial/BLE). Danh mục mọi tham số config được: `docs/sensor-config/configurable-items.md`. Logic nghiệp vụ (FTE, tỷ lệ có người, cảnh báo) tái dùng **business rules** trong `docs/dashboard/rules.md` + schema `docs/data-sync/schema.md`. Không lặp lại nội dung ở đây.

## Hai vùng, hai đường dữ liệu ĐỘC LẬP
```
VÙNG 1 GIÁM SÁT (mọi máy)          VÙNG 2 CẤU HÌNH (1 sensor)
Browser ──HTTP poll──► FastAPI     Browser ──Web Serial/BLE──► LD2410C tại chỗ
                         │          (JS chạm thẳng COM/BLE, không backend)
                         ▼
                      Oracle (machine_status + sessions)
```

## Tab Giám sát — cận realtime
- Nguồn realtime: bảng `machine_status` (xem `docs/data-sync/schema.md`) — mỗi `run_reader` upsert `present_now`/`last_seen`/`sensor_ok` mỗi vài giây.
- Frontend **poll** `GET /api/machines/status` mỗi 2–5s (cấu hình được) → cập nhật bảng, KHÔNG reload trang.
- FTE / tỷ lệ có người: lấy từ `sessions`, không realtime (poll thưa hoặc bấm refresh).
- Cảnh báo sensor: `sensor_ok=0` hoặc `last_seen` quá cũ → badge đỏ.
- KHÔNG hiển thị dữ liệu định danh cá nhân (privacy — chỉ machine_id + trạng thái + thời gian).

## Tab Cấu hình — Web Serial/BLE (parity đầy đủ với GUI PyQt cũ)
Tab này thay thế hoàn toàn GUI PyQt — mọi tính năng cấu hình đều nằm ở đây. 3 vùng:

### 1. Kết nối
- Chọn transport: **Serial** (`navigator.serial`) hoặc **BLE** (`navigator.bluetooth`).
- Serial: user chọn COM port; BLE: scan lọc tên `HLK-LD2410C*`, cảnh báo nếu UUID còn placeholder (xem ble-transport.md).
- Nút Connect/Disconnect + đèn trạng thái. Dùng chung module transport (protocol-js.md).

### 2. Energy realtime (Canvas)
- Bar chart theo gate 0..8: **energy chuyển động** + **energy tĩnh** (2 màu).
- Overlay **đường ngưỡng sensitivity** từng gate (kéo được) → thấy energy vượt ngưỡng ở đâu.
- Badge **target_state** (Trống / Chuyển động / Đứng yên / Cả hai) + **moving/static distance** (cm). Cập nhật ~10Hz.
- **Engineering mode tự bật khi Connect** (`0x0062`, volatile) để có energy; **tự tắt khi Disconnect** (`0x0063`).

### 3. Form cấu hình + hành động (đủ như app PyQt)
- Tham số: **range resolution** (0.75/0.2m, `0x00AA`), **max moving gate**, **max static gate**, **no-one duration** (3 cái sau chung lệnh `0x0060`).
- Sliders **sensitivity từng gate**: motion (gate 0–8), static (gate 2–8) — **gate 0,1 disable static** (không set được). Có nút set đồng loạt (gate word `0xFFFF`).
- Nút hành động: **Đọc lại** (`0x0061`) · **Ghi flash** (`0x0060` + `0x0064`) · **Auto-calib nền** (`0x000B`, poll `0x001B` — *tùy chọn*, chỉ lấy baseline) · **Factory reset** (`0x00A2`) · **Restart module** (`0x00A3`).
- **Luồng khuyến nghị = manual**: quan sát energy realtime → kéo đường ngưỡng (đặt sensitivity) → Ghi flash. Auto-calib không bắt buộc. Chi tiết: docs/sensor-config/rules.md.
- **Ô log**: hiển thị ACK từng lệnh (success/fail) — như log của GUI cũ.

### Hành vi (bê nguyên từ GUI PyQt)
- **Kéo slider** chỉ đổi đường ngưỡng hiển thị; chỉ khi bấm **Ghi flash** mới gửi `0x0064`.
- **Flow ghi**: Enable config (`0x00FF`) → gửi lệnh → verify ACK từng lệnh → End config (`0x00FE`) → bật lại engineering mode → **đọc lại (`0x0061`) so khớp** → hiện ✓/✗ trong log. ACK fail → log đỏ, KHÔNG đánh dấu "đã ghi".
- **Đọc lại** nạp giá trị hiện tại của sensor lên form làm điểm xuất phát.
- Đổi **range resolution** → nhắc user **Restart module** (`0x00A3`) mới có hiệu lực.
- **Auto-calib**: cảnh báo "đảm bảo KHÔNG có người trong vùng", đếm ngược theo thời lượng, poll `0x001B` tới khi xong rồi đọc lại sensitivity.

## Ràng buộc BẮT BUỘC (edge cases)
- **Trình duyệt**: chỉ Chrome/Edge desktop (Web BT thêm Android; KHÔNG iOS/Safari/Firefox). Tab Giám sát chạy mọi browser; tab Cấu hình disable + báo rõ nếu browser không hỗ trợ `navigator.serial`/`navigator.bluetooth`.
- **HTTPS hoặc localhost** mới dùng được Web Serial/BLE.
- **Serial độc quyền**: nếu `run_reader` đang giữ COM của máy → browser mở serial fail → hiện "Dừng reader trước khi cấu hình". Reader và tab Cấu hình KHÔNG dùng chung cổng cùng lúc.
- **Vị trí vật lý**: tab Cấu hình phải chạy trên browser của **máy đang cắm sensor** (hoặc kỹ thuật viên cắm sensor vào laptop mình). Tab Giám sát xem từ bất kỳ đâu trong mạng.
- **Ghi flash là hành động ảnh hưởng phần cứng**: luôn confirm + đọc lại; ACK fail → KHÔNG đánh dấu "đã ghi".

## Cấu trúc thư mục dự kiến
```
web/                — Frontend Vue SPA (tab Giám sát + Cấu hình)
  src/lib/ld2410c/  — Port protocol sang JS (build/parse frame) — xem protocol-js.md
src/web_api/        — Backend FastAPI đọc Oracle — xem api-contract.md
```

## Bảo mật
- Backend không nhận credential Oracle từ UI — lấy từ `.env` (dùng chung loader với reader).
- Tab Cấu hình ghi flash sensor: chỉ thao tác tại chỗ, có xác nhận.
- Truy cập app: đặt sau mạng nội bộ công ty; nếu mở rộng ra ngoài cần lớp auth (Cognito/SSO) — quyết định sau, xác nhận policy hạ tầng.
