# LD2410C — Danh mục CẤU HÌNH ĐƯỢC (đầy đủ)

Nguồn: docs/references/ld2410c-protocol.md (protocol V1.07). Đây là catalog tất cả tham số có thể set
qua UART — dùng làm cơ sở cho script `configure`, `tune` và GUI cấu hình.

Cột **Lưu**: `flash` = giữ khi tắt nguồn · `volatile` = mất khi tắt nguồn.
Cột **Hiệu lực**: `ngay` · `restart` = phải khởi động lại module.

## A. Tầm phát hiện & gate
| Mục | Command | Giá trị | Lưu | Hiệu lực | Ghi chú |
|---|---|---|---|---|---|
| Độ phân giải khoảng cách | `0x00AA` | 0.75m (`0x0000`) / 0.2m (`0x0001`) | flash | restart | Quyết định gate N = N × resolution. 8 gate: 0.75m→6m, 0.2m→1.6m |
| Max moving gate | `0x0060` (word `0x0000`) | 1–8 hoặc 2–8 ⚠️ | flash | ngay | Gate xa nhất còn tính chuyển động. **Tài liệu Hi-Link mâu thuẫn về giá trị nhỏ nhất** (§1.2.2 nói 1, §2.2.3 nói 2) — xem docs/references/ld2410c-protocol.md §3. KHÔNG validate cứng phía client; dựa vào ACK sensor trả về |
| Max static gate | `0x0060` (word `0x0001`) | 1–8 hoặc 2–8 ⚠️ | flash | ngay | Tương tự — gate xa nhất còn tính đứng yên |

**Ví dụ tính khoảng cách** (§1.2.2): farthest gate=2, resolution=0.75m → chỉ phát hiện trong **1.5m** (= 2 × 0.75).

## B. Độ nhạy (ngưỡng năng lượng)
| Mục | Command | Giá trị | Lưu | Hiệu lực | Ghi chú |
|---|---|---|---|---|---|
| Motion sensitivity từng gate | `0x0064` (word gate + `0x0001`) | gate 0–8, value 0–100 | flash | ngay | Càng thấp càng nhạy |
| Static sensitivity từng gate | `0x0064` (word gate + `0x0002`) | gate 2–8, value 0–100 | flash | ngay | **Gate 0,1 KHÔNG đặt được static** |
| Sensitivity đồng loạt mọi gate | `0x0064` (gate word `0xFFFF`) | value 0–100 | flash | ngay | Áp 1 giá trị cho tất cả gate |
| Tự hiệu chỉnh nền (auto sensitivity) | `0x000B` | duration giây | flash | ngay | Đo background noise (yêu cầu KHÔNG có người), tự set sensitivity |

### Kỹ thuật khoanh vùng bằng sensitivity = 100
Energy mục tiêu nằm trong 0–100 → đặt sensitivity **= 100** cho 1 gate = **vô hiệu hoá** gate đó (không energy nào vượt ngưỡng). Kết hợp: gate cần bắt → sensitivity thấp (nhạy); gate còn lại → sensitivity=100 (tắt) → chỉ phát hiện đúng 1 dải khoảng cách mà không cần đổi max gate tổng thể.
- Ví dụ (§1.2.2): gate 3 & 4 sensitivity=20, các gate khác=100 → chỉ phát hiện người trong **2.25–3.75m**. Áp dụng tốt để loại người đi ngang ngoài vùng đứng máy CNC.

## C. Thời gian
| Mục | Command | Giá trị | Lưu | Hiệu lực | Ghi chú |
|---|---|---|---|---|---|
| No-one / unmanned duration | `0x0060` (word `0x0002`) | 0–65535 giây | flash | ngay | Giữ trạng thái "có người" thêm N giây sau khi mất mục tiêu |

## D. Hành vi chân OUT (cảm biến ánh sáng)
| Mục | Command | Giá trị | Lưu | Hiệu lực | Ghi chú |
|---|---|---|---|---|---|
| Aux light control — chế độ | `0x00AD` byte 1 | `0x00` tắt / `0x01` kích khi sáng < ngưỡng / `0x02` kích khi sáng > ngưỡng | flash | ngay | OUT bị ảnh hưởng thêm bởi cảm biến ánh sáng |
| Aux light control — ngưỡng sáng | `0x00AD` byte 2 | 0–255 (mặc định 0x80) | flash | ngay | |
| Mức mặc định chân OUT | `0x00AD` byte 3 | `0x00` low mặc định / `0x01` high mặc định | flash | ngay | Chỉ ảnh hưởng chân OUT vật lý, KHÔNG ảnh hưởng data UART |

> Với project này ta đọc target_state qua UART, KHÔNG dùng chân OUT → nhóm D thường để mặc định (tắt).

## E. Truyền thông
| Mục | Command | Giá trị | Lưu | Hiệu lực | Ghi chú |
|---|---|---|---|---|---|
| Baud rate | `0x00A1` | index 9600–460800 (mặc định `0x0007`=256000) | flash | restart | Đổi xong phải restart + đổi baud phía PC |
| Bluetooth on/off | `0x00A4` | `0x0100` on / `0x0000` off | flash | restart | Cần **bật** nếu dùng BLE transport để config từ xa (xem docs/sensor-config/ble-transport.md); nên **tắt** khi vận hành prod (bảo mật/privacy) |
| Get Bluetooth access (xác thực BLE) | `0x00A8` | 6B password | — | ngay | Gửi qua kênh BLE để lấy quyền cấu hình qua BLE. Xem docs/sensor-config/ble-transport.md |
| Đổi mật khẩu Bluetooth | `0x00A9` | 6 byte | flash | restart | Mặc định "HiLink" |

> **Kết nối cấu hình qua BLE (không dây, trong tầm ~10–30m)**: xem docs/sensor-config/ble-transport.md — khung code đã dựng (`src/sensor/transport/ble_transport.py`), UUID GATT thật cần dò bằng `python -m src.workflows.ble_discover` (ngay trên laptop, không cần điện thoại) trước khi dùng.

## F. Chế độ / bảo trì
| Mục | Command | Giá trị | Lưu | Hiệu lực | Ghi chú |
|---|---|---|---|---|---|
| Engineering mode | `0x0062` bật / `0x0063` tắt | none | volatile | ngay | Thêm energy từng gate vào data output — chỉ dùng khi tune |
| Factory reset | `0x00A2` | none | flash | restart | Về mặc định xuất xưởng (xem ref §7) |
| Restart module | `0x00A3` | none | — | ngay | Tự restart sau ACK |

## Chỉ đọc (không config, nhưng liên quan)
Read parameters `0x0061` · Read firmware `0x00A0` · Get MAC `0x00A5` · Query range resolution `0x00AB` ·
Query aux control `0x00AE` · Query noise-detection status `0x001B`.

## Ưu tiên cho project presence-tracking
1. **Range resolution** → chọn theo khoảng cách người–sensor tại máy.
2. **Max moving/static gate** → giới hạn đúng vùng máy, loại người ở lối đi xa.
3. **Sensitivity từng gate** (manual, luồng khuyến nghị — xem docs/sensor-config/rules.md) → giữ trạng thái ổn định, tránh nhấp nháy. Auto-calib `0x000B` chỉ là tùy chọn lấy baseline.
4. **No-one duration** → phối hợp với DEBOUNCE_S ở tầng phần mềm (xem docs/realtime-reader).
5. Tắt **Bluetooth**, để **Aux light** mặc định.
