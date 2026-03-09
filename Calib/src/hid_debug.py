import argparse
import threading
import time

from config import USB_VID, USB_PID, COM_PORT

try:
    import pywinusb.hid as hid_win
except Exception:
    hid_win = None

try:
    import serial
except Exception:
    serial = None


def format_hex(data):
    return " ".join(f"{b:02X}" for b in data)


def parse_axes(report):
    if report is None:
        return None, None
    report_len = len(report)

    def u16(i):
        return report[i] | (report[i + 1] << 8)

    def pick_offset():
        if report_len < 12:
            return None
        candidates = []
        if report_len >= 13 and report[0] <= 0x10:
            candidates.append(1)
        if report_len >= 14 and report[0] == 0 and report[1] <= 0x10:
            candidates.append(2)
        for off in (0, 1, 2):
            if off not in candidates:
                candidates.append(off)
        best = None
        best_score = -1
        for off in candidates:
            if report_len < off + 12:
                continue
            axes = [u16(off + 4), u16(off + 6), u16(off + 8), u16(off + 10)]
            score = sum(0 <= v <= 1023 for v in axes)
            if score > best_score:
                best_score = score
                best = off
            if score == 4:
                break
        return best

    offset = pick_offset()
    if offset is None:
        return None, None
    if report_len < offset + 12:
        return None, None
    offset += 4

    x = u16(offset)
    y = u16(offset + 2)
    rudder = u16(offset + 4)
    brake = u16(offset + 6)
    max_val = max(x, y, rudder, brake)
    if max_val > 1023:
        x = int(round(x * 1023 / 65535))
        y = int(round(y * 1023 / 65535))
        rudder = int(round(rudder * 1023 / 65535))
        brake = int(round(brake * 1023 / 65535))
    return offset - 4, {"x": x, "y": y, "rudder": rudder, "brake": brake}


class HIDDump:
    def __init__(self, vid, pid):
        self.vid = vid
        self.pid = pid
        self.dev = None
        self.last_report = None

    def open(self):
        if hid_win is None:
            print("[HID] pywinusb not available")
            return False
        devices = hid_win.HidDeviceFilter(vendor_id=self.vid, product_id=self.pid).get_devices()
        if not devices:
            print("[HID] device not found")
            return False
        self.dev = devices[0]
        self.dev.open()
        self.dev.set_raw_data_handler(self._handle_report)
        return True

    def close(self):
        if self.dev:
            self.dev.set_raw_data_handler(None)
            self.dev.close()
            self.dev = None

    def _handle_report(self, data):
        self.last_report = bytes(data)

    def read_report(self):
        if self.last_report is None:
            return None
        r = self.last_report
        self.last_report = None
        return r


def serial_read_loop(ser):
    while True:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        if line:
            print(f"[SER] {line}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vid", type=lambda v: int(v, 0), default=USB_VID)
    parser.add_argument("--pid", type=lambda v: int(v, 0), default=USB_PID)
    parser.add_argument("--serial", action="store_true", help="also dump serial RAW")
    parser.add_argument("--port", default=COM_PORT)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--send", action="append", help="send a serial command (repeatable)")
    parser.add_argument("--send-interval", type=float, default=0.2)
    args = parser.parse_args()

    ser = None
    if args.serial or args.send:
        if serial is None:
            print("[SER] pyserial not available")
            return
        if not args.port:
            print("[SER] no COM port specified")
            return
        try:
            ser = serial.Serial(args.port, args.baud, timeout=0.2)
            print(f"[SER] connected {args.port}")
        except Exception as exc:
            print(f"[SER] open failed: {exc}")
            return
        if args.serial:
            t = threading.Thread(target=serial_read_loop, args=(ser,), daemon=True)
            t.start()
        if args.send:
            for cmd in args.send:
                payload = cmd.rstrip("\n") + "\n"
                try:
                    print(f"[SER->] {payload.rstrip()}")
                    ser.write(payload.encode("utf-8"))
                    ser.flush()
                except Exception as exc:
                    print(f"[SER] write failed: {exc}")
                    break
                time.sleep(max(0.0, args.send_interval))

    hid = HIDDump(args.vid, args.pid)
    if not hid.open():
        return
    print("[HID] listening...")
    try:
        while True:
            report = hid.read_report()
            if report:
                offset, axes = parse_axes(report)
                hex_str = format_hex(report)
                if axes is None:
                    print(f"[HID] len={len(report)} off=? data={hex_str}")
                else:
                    print(f"[HID] len={len(report)} off={offset} data={hex_str} axes={axes}")
            time.sleep(0.01)
    finally:
        hid.close()
        if ser:
            try:
                ser.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
