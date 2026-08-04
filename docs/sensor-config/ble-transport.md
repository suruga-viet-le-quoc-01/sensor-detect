# BLE Transport (kết nối không dây tới sensor) — SCAFFOLD

Module: `src/sensor/transport/` (`base.py`, `serial_transport.py`, `ble_transport.py`)
Trạng thái: **khung code đã dựng, UUID BLE thật CHƯA được xác nhận** — không dùng prod cho tới khi điền UUID thật.

## Vì sao có tài liệu này
Kỹ thuật viên muốn ngồi cách sensor ~3–4m (trong tầm BLE, không cần dây USB) để cấu hình/hiệu chỉnh.
LD2410C có Bluetooth on-board (lệnh `0x00A4` bật/tắt, `0x00A5` lấy MAC, `0x00A8`/`0x00A9` xác thực BLE
— xem docs/references/ld2410c-protocol.md). Nhưng file protocol PDF Hi-Link **chỉ tài liệu hoá UART**,
KHÔNG có GATT profile (service/characteristic UUID) của kênh BLE.

## Bằng chứng cùng 1 protocol byte-level được tái dùng qua BLE
Lệnh `0x00A8` (Get Bluetooth access) dùng đúng frame format `FD FC FB FA ... 04 03 02 01` giống hệt
lệnh UART khác, và PDF ghi chú: *"This response only responds to bluetooth, not the serial port"*
(§2.2.14) — tức lệnh này được gửi/nhận qua kênh BLE bằng **cùng byte protocol**. Đây là cơ sở để giả
định: command/ACK frame giống hệt UART, chỉ khác đường truyền vật lý (transport). Giả định này **chưa
được verify với chính module thật** — cần kiểm chứng ở bước dò UUID bên dưới.

## Kiến trúc
```
src/sensor/transport/
  base.py             — SensorTransport (ABC): connect/disconnect/send/read
  serial_transport.py — SerialTransport (pyserial) — đã dùng được ngay
  ble_transport.py     — BleTransport (bleak) — SCAFFOLD, chặn dùng khi UUID còn placeholder
  __init__.py          — create_transport() đọc TRANSPORT trong .env, chọn Serial hoặc BLE
```
Lớp `src/protocol/` (frame builder/parser, sẽ viết ở bước sau) dùng chung cho cả 2 transport — không
cần biết đang chạy qua Serial hay BLE.

## Vì sao BleTransport raise lỗi ngay bây giờ
`BleTransport.__init__` chặn cứng nếu `BLE_SERVICE_UUID` / `BLE_WRITE_CHAR_UUID` / `BLE_NOTIFY_CHAR_UUID`
còn rỗng hoặc là placeholder `00000000-0000-0000-0000-000000000000` — ném `BleConfigError` kèm hướng
dẫn. Mục đích: không để ai vô tình chạy "prod" với UUID giả rồi tưởng lỗi kết nối là do sensor/BLE
adapter, trong khi thực ra là do chưa dò UUID thật.

## Cách dò UUID thật (làm 1 lần khi setup)

### Phương án A — ngay trên laptop bằng script có sẵn (khuyến nghị, không cần điện thoại)
Project đã có `src/workflows/ble_discover.py`, dùng chung thư viện `bleak` với `BleTransport` —
laptop chỉ cần Bluetooth adapter (built-in hoặc USB dongle).

1. Bật Bluetooth trên sensor: gửi lệnh `0x00A4` value `0x0100` qua UART (dùng `configure` CLI hoặc
   GUI cấu hình — sensor phải đang cắm dây ít nhất 1 lần đầu để bật BLE).
2. Quét thiết bị xung quanh:
   ```
   python -m src.workflows.ble_discover
   ```
   In ra danh sách `address` + tên quảng bá (tìm tên dạng `HLK-LD2410C_xxxx`, hoặc đối chiếu MAC lấy
   từ lệnh `0x00A5` Get MAC address).
3. Liệt kê service/characteristic của thiết bị đã chọn:
   ```
   python -m src.workflows.ble_discover --address AA:BB:CC:DD:EE:FF
   ```
   In ra từng `Service <uuid>` kèm `Characteristic <uuid> [properties]`. Tìm service không phải
   chuẩn Bluetooth SIG (custom UUID, thường không phải `0000xxxx-0000-1000-8000-00805f9b34fb`) →
   đây là `BLE_SERVICE_UUID`. Trong service đó:
   - Characteristic có `write` trong properties → `BLE_WRITE_CHAR_UUID` (tương đương UART_Rx).
   - Characteristic có `notify` trong properties → `BLE_NOTIFY_CHAR_UUID` (tương đương UART_Tx).
4. Verify giả định protocol ngay trong 1 lệnh — script tự gửi Enable config và so khớp ACK:
   ```
   python -m src.workflows.ble_discover --address AA:BB:CC:DD:EE:FF \
     --verify-write-uuid <write-uuid> --verify-notify-uuid <notify-uuid>
   ```
   Kết quả in `"KHỚP ACK mong đợi — UUID + giả định protocol qua BLE ĐÚNG"` → dùng được ngay.
   Không nhận được gì → sai UUID, hoặc sensor cần xác thực trước (thử gửi `0x00A8` Get Bluetooth
   access với password mặc định "HiLink" — chưa có trong script, gửi thủ công qua `client.write_gatt_char`
   nếu cần).
5. Điền 3 UUID + address vào `.env` (`BLE_SERVICE_UUID`, `BLE_WRITE_CHAR_UUID`, `BLE_NOTIFY_CHAR_UUID`,
   `BLE_DEVICE_ADDRESS`).

### Phương án B — dùng điện thoại (nRF Connect for Mobile)
Nếu muốn xem trực quan hơn (đặc biệt khi cần bấm "Enable notifications" thủ công để quan sát), dùng
app **nRF Connect for Mobile** (Nordic Semiconductor, miễn phí, Android/iOS): Scan → Connect → xem
Services/Characteristics → ghi lại UUID theo đúng quy tắc ở Phương án A bước 3. Windows cũng có công
cụ GUI tương đương (**Bluetooth LE Explorer**, Microsoft Store) nếu không muốn chạy script.

## Edge cases / Skip logic
- UUID còn placeholder/rỗng → `BleConfigError` ngay khi khởi tạo, KHÔNG cố kết nối rồi mới lỗi mù mờ.
- Sensor ngoài tầm BLE hoặc chưa bật Bluetooth (`0x00A4`) → `connect()` timeout theo
  `BLE_SCAN_TIMEOUT_S` → báo lỗi rõ "không tìm thấy thiết bị, kiểm tra đã bật Bluetooth trên sensor
  qua UART chưa".
- Sensor yêu cầu password BLE (`0x00A8`) trước khi cho ghi lệnh cấu hình → nếu gặp ACK fail khi gửi
  lệnh cấu hình qua BLE dù connect thành công, thử gửi `0x00A8` với `BLE_PASSWORD` trước.
- BLE và Serial transport KHÔNG chạy đồng thời trên cùng sensor để tránh xung đột trạng thái cấu hình
  (giống nguyên tắc "reader và tab Cấu hình web không dùng chung COM" ở docs/web-dashboard/rules.md).

## Ràng buộc
- BLE chỉ dùng cho **cấu hình/hiệu chỉnh** (config-sensor, tune, GUI) — KHÔNG dùng làm transport cho
  `run_reader` prod (đọc liên tục 24/7 qua BLE kém ổn định hơn UART có dây; UART vẫn là đường chính
  cho vận hành thực tế).
- Không hard-code UUID/address trong code — luôn đọc từ `.env`.

## Việc còn lại (chưa làm, cần phần cứng thật)
- Xác nhận UUID thật bằng `python -m src.workflows.ble_discover` (§"Cách dò UUID thật" ở trên).
- Sau khi có UUID thật, chạy `pytest tests/test_transport.py -q` (đã pass với mock/placeholder) rồi
  test thật với sensor + laptop có BLE adapter.
