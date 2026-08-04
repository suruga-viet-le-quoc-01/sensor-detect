# Port protocol LD2410C sang JS (tab Cấu hình — Web Serial/BLE)

Module `web/src/lib/ld2410c/`. Cùng byte-protocol với Python — nguồn sự thật:
`docs/references/ld2410c-protocol.md`. KHÔNG định nghĩa lại giá trị command ở đây; chỉ mô tả cách port.

## Cấu trúc module đề xuất
- `frames.js` — build/parse frame thuần (không I/O), giống vai trò `src/protocol/` bên Python.
- `serial.js` — transport Web Serial (`navigator.serial`).
- `ble.js` — transport Web Bluetooth (`navigator.bluetooth`).
- `config.js` — flow cấu hình cấp cao (enable → gửi → verify → end → readback).

## frames.js — hàm cần có
- `buildCommand(word: number, value: Uint8Array): Uint8Array`
  → `FD FC FB FA | len(2B LE) | word(2B LE) + value | 04 03 02 01`.
- `parseAck(bytes): {word, status, payload}` — status `00 00` = OK. ACK word = word | 0x0100.
- `parseDataFrame(bytes): {type, targetState, ...energies}` — header `F4 F3 F2 F1`, `data[2]` = target_state.
- `presence(state): boolean` — `state ∈ {1,2,3}` → true.
- Little-endian mọi trường đa byte (khớp Python). Có unit test đối chiếu đúng các ví dụ byte trong ref doc §3/§5/§8.4.

## config.js — mapping ĐẦY ĐỦ (parity với GUI PyQt cũ)
| Tham số/hành động UI | Command | Ghi chú |
|---|---|---|
| Max moving gate + max static gate + **no-one duration** | `0x0060` | 3 tham số chung 1 lệnh, value 4B mỗi cái, xem ref §3. Hiệu lực ngay |
| Sensitivity từng gate | `0x0064` gate word + motion/static | ref §5. Gate 0,1 KHÔNG set được static |
| Sensitivity đồng loạt | `0x0064` gate word `0xFFFF` | 1 giá trị mọi gate |
| RANGE_RESOLUTION | `0x00AA` (`0x0000`=0.75m/`0x0001`=0.2m) | **hiệu lực sau restart** → gọi `0x00A3` |
| Engineering mode | `0x0062` bật / `0x0063` tắt | tự bật khi connect, tắt khi disconnect |
| Read parameters | `0x0061` | đọc lại xác nhận sau khi ghi |
| **Auto-calib nền** | `0x000B` (thời lượng) + poll `0x001B` | yêu cầu KHÔNG có người; poll tới status=2 (xong) rồi đọc lại |
| **Factory reset** | `0x00A2` | về mặc định xuất xưởng; nhắc restart |
| **Restart module** | `0x00A3` | tự restart sau ACK |

- Flow ghi (chi tiết ở `docs/web-dashboard/rules.md` tab Cấu hình): Enable `0x00FF` → lệnh → verify ACK từng lệnh → End `0x00FE` → bật lại engineering mode → `0x0061` đọc lại so khớp → hiện ✓/✗. Đổi resolution → nhắc user restart module.

## serial.js — Web Serial
- `navigator.serial.requestPort()` (user chọn COM) → `port.open({ baudRate: 256000 })`.
- Ghi: `port.writable.getWriter().write(frame)`. Đọc: `port.readable.getReader()` gom byte, resync theo header.
- Đóng writer/reader + `port.close()` khi rời tab.

## ble.js — Web Bluetooth
- `navigator.bluetooth.requestDevice({ filters:[{ namePrefix: 'HLK-LD2410C' }], optionalServices:[SERVICE_UUID] })`.
- UUID lấy theo `docs/sensor-config/ble-transport.md` (write char = ghi lệnh, notify char = nhận data/ACK). Nếu chưa dò được UUID thật → disable phần BLE, chỉ cho Serial.
- Ghi: `writeChar.writeValue(frame)`. Nhận: `startNotifications()` + event `characteristicvaluechanged`.

## Ràng buộc (nhắc lại — quan trọng)
- Chỉ Chrome/Edge desktop (BLE thêm Android). HTTPS/localhost. Feature-detect `navigator.serial`/`navigator.bluetooth`, thiếu thì báo rõ.
- Serial độc quyền: reader đang giữ COM → mở fail → hướng dẫn dừng reader.
- Message hiển thị cho người vận hành: **tiếng Nhật** (theo `docs/coding-standards.md`); comment code: tiếng Anh.
