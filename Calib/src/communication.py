import time
import math

from config import USB_PID, USB_VID, COM_PORT

try:
    import serial
    from serial.tools import list_ports
except Exception:
    serial = None
    list_ports = None

try:
    import pywinusb.hid as hid_win
except Exception:
    hid_win = None

class ArduinoComm:
    def __init__(
        self,
        port=COM_PORT,
        baudrate=115200,
        timeout=1.0,
        usb_vid=USB_VID,
        usb_pid=USB_PID,
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.usb_vid = usb_vid
        self.usb_pid = usb_pid
        self.ser = None
        self.log_prefix_tx = "[SERIAL TX]"
        self.log_prefix_rx = "[SERIAL RX]"

    def _log_tx(self, payload):
        print(f"{self.log_prefix_tx} {payload}")

    def _log_rx(self, payload):
        print(f"{self.log_prefix_rx} {payload}")

    def auto_connect(self):
        if serial is None or list_ports is None:
            print("[Comm] pyserial not available")
            return False
        port = self.port or self._find_port()
        if not port:
            print("[Comm] No Arduino port found")
            return False
        try:
            self.ser = serial.Serial(port, self.baudrate, timeout=self.timeout)
            time.sleep(1.0)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            print(f"[Comm] Connected to {port}")
            return True
        except Exception as exc:
            print(f"[Comm] Failed to open {port}: {exc}")
            return False

    def _find_port(self):
        if self.usb_vid is not None or self.usb_pid is not None:
            for info in list_ports.comports():
                if self.usb_vid is not None and info.vid != self.usb_vid:
                    continue
                if self.usb_pid is not None and info.pid != self.usb_pid:
                    continue
                return info.device
            return None
        for info in list_ports.comports():
            desc = (info.description or "").lower()
            hwid = (info.hwid or "").lower()
            if "arduino" in desc or "leonardo" in desc:
                return info.device
            if "2341" in hwid or "2a03" in hwid:
                return info.device
        ports = list(list_ports.comports())
        return ports[0].device if ports else None

    def _read_line(self):
        if not self.ser:
            return None
        try:
            raw = self.ser.readline().decode("utf-8", errors="ignore").strip()
            if raw:
                self._log_rx(raw)
                return raw
            return None
        except Exception:
            return None

    def _parse_raw_line(self, line):
        if not line:
            return None
        if line.startswith("<RAW{") and line.endswith("}>"):
            payload = line[5:-2]
        elif line.startswith("RAW,"):
            payload = line[4:]
        else:
            return None
        parts = [p.strip() for p in payload.split(",") if p.strip() != ""]
        if len(parts) != 4:
            return None
        try:
            values = [int(p) for p in parts]
        except ValueError:
            return None
        if any(v < 0 or v > 1023 for v in values):
            return None
        return values

    def _request_raw(self):
        if not self.ser:
            return None
        payload = "*GETRAW\n"
        try:
            self._log_tx(payload.rstrip("\n"))
            self.ser.write(payload.encode("utf-8"))
            self.ser.flush()
        except Exception:
            return None
        line = self._read_line()
        return self._parse_raw_line(line)

    def _send_and_wait(self, cmd, retries=2):
        if not self.ser:
            return False
        payload = cmd.rstrip("\n") + "\n"
        for _ in range(retries + 1):
            try:
                self._log_tx(payload.rstrip("\n"))
                self.ser.write(payload.encode("utf-8"))
                self.ser.flush()
            except Exception:
                return False
            resp = self._read_line()
            if resp == "<OK>":
                return True
            if resp == "<ERR>":
                continue
        return False

    def _drain_lines(self, duration_s=0.8):
        if not self.ser:
            return
        deadline = time.time() + max(0.0, duration_s)
        while time.time() < deadline:
            line = self._read_line()
            if line is None:
                # No data within timeout, keep waiting until deadline.
                continue

    def _begin_calibration(self):
        return self._send_and_wait("<BEGIN_CALIBRATION>")

    def _end_calibration(self):
        return self._send_and_wait("<END_CALIBRATION>")

    def _send_lut_payload(self, axis_idx, lut_list):
        payload = ",".join(str(int(v)) for v in lut_list)
        return self._send_and_wait(f"*SETLUT{{{axis_idx},{payload}}}")

    def _save(self):
        return self._send_and_wait("*SAVE")

    def save_all(self):
        return self._send_and_wait("*SAVE_ALL")

    def enable_hid(self):
        return self._send_and_wait("*HID_ON")

    def send_brake_endpoints(self, min_val, max_val):
        min_val = int(min_val)
        max_val = int(max_val)
        if min_val < 0 or min_val > 1023 or max_val < 0 or max_val > 1023:
            print("[Comm] Brake endpoints must be 0..1023")
            return False
        if min_val > max_val:
            min_val, max_val = max_val, min_val
        return self._send_and_wait(f"*SETBRK{{{min_val},{max_val}}}")

    def send_lut_batch(self, lut_map, brake_endpoints=None):
        if not self.ser:
            return False
        started = False
        success = False
        try:
            if not self._begin_calibration():
                return False
            started = True
            for axis_idx, lut in lut_map.items():
                if not self._send_lut_payload(axis_idx, lut):
                    return False
            if brake_endpoints is not None:
                bmin, bmax = brake_endpoints
                if not self._send_and_wait(f"*SETBRK{{{int(bmin)},{int(bmax)}}}"):
                    return False
            if not self._save():
                return False
            # Drain any dump lines sent after save.
            self._drain_lines(0.8)
            success = True
        finally:
            if started and not self._end_calibration():
                success = False
        return success

    def send_lut(self, axis_idx, lut_list):
        if not self.ser:
            return False
        if axis_idx not in (0, 1, 2, 3):
            print("[Comm] Axis index must be 0..3")
            return False
        if len(lut_list) != 33:
            print("[Comm] LUT length must be 33")
            return False
        started = False
        success = False
        try:
            if not self._begin_calibration():
                return False
            started = True
            if not self._send_lut_payload(axis_idx, lut_list):
                return False
            if not self._save():
                if not self._send_lut_payload(axis_idx, lut_list):
                    return False
                if not self._save():
                    return False
            success = True
        finally:
            if started and not self._end_calibration():
                success = False
        return success

    def get_raw(self):
        values = self._request_raw()
        if values is not None:
            return values
        line = self._read_line()
        return self._parse_raw_line(line)

    def close(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None


class DummyComm:
    def __init__(self):
        self.ser = object()
        self._t0 = time.time()

    def auto_connect(self):
        self.ser = object()
        return True

    def enable_hid(self):
        return True

    def _wave(self, phase, base=512, amp=400):
        return int(round(base + amp * math.sin(phase)))

    def get_raw(self):
        t = time.time() - self._t0
        x = self._wave(t * 0.9)
        y = self._wave(t * 0.7 + 1.2)
        rud = self._wave(t * 1.1 + 2.1)
        brk = int(round(512 + 511 * (math.sin(t * 0.6 - 0.3) * 0.5 + 0.5)))
        return [max(0, min(1023, v)) for v in (x, y, rud, brk)]

    def send_lut_batch(self, lut_map, brake_endpoints=None):
        return True

    def send_lut(self, axis_idx, lut_list):
        return True

    def send_brake_endpoints(self, min_val, max_val):
        return True

    def close(self):
        self.ser = None



class HIDReader:
    def __init__(self, usb_vid=USB_VID, usb_pid=USB_PID):
        self.usb_vid = usb_vid
        self.usb_pid = usb_pid
        self.dev = None
        self._last_report = None

    def open(self):
        if hid_win is None:
            print("[HID] pywinusb not available")
            return False
        devices = hid_win.HidDeviceFilter(
            vendor_id=self.usb_vid,
            product_id=self.usb_pid,
        ).get_devices()
        if not devices:
            print("[HID] device not found")
            return False
        try:
            self.dev = devices[0]
            self.dev.open()
            self.dev.set_raw_data_handler(self._handle_report)
            return True
        except Exception as exc:
            print(f"[HID] open failed: {exc}")
            self.dev = None
            return False

    def close(self):
        if self.dev:
            try:
                self.dev.set_raw_data_handler(None)
                self.dev.close()
            except Exception:
                pass
            self.dev = None

    def _handle_report(self, data):
        # data is a list of ints from pywinusb
        self._last_report = bytes(data)

    def _read_report(self):
        if self._last_report is None:
            return None
        report = self._last_report
        self._last_report = None
        return report

    def read_axes(self):
        report = self._read_report()
        if report is None:
            return None
        report_len = len(report)

        def u16(i):
            return report[i] | (report[i + 1] << 8)

        # Heuristically choose the report offset to handle report IDs/prefix bytes.
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
            return None
        if report_len < offset + 4 + 8:
            return None
        offset += 4  # buttons

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
        return {"x": x, "y": y, "rudder": rudder, "brake": brake}


class DummyHID:
    def __init__(self):
        self._t0 = time.time()

    def open(self):
        return True

    def close(self):
        return None

    def _wave(self, phase, base=512, amp=400):
        return int(round(base + amp * math.sin(phase)))

    def read_axes(self):
        t = time.time() - self._t0
        x = self._wave(t * 0.9)
        y = self._wave(t * 0.7 + 1.2)
        rud = self._wave(t * 1.1 + 2.1)
        brk = int(round(512 + 511 * (math.sin(t * 0.6 - 0.3) * 0.5 + 0.5)))
        return {
            "x": max(0, min(1023, x)),
            "y": max(0, min(1023, y)),
            "rudder": max(0, min(1023, rud)),
            "brake": max(0, min(1023, brk)),
        }

