import asyncio
import flet as ft
import ui_views
from calibration import AxisCalibrator
from communication import ArduinoComm, HIDReader, DummyComm, DummyHID


class AppState:
    def __init__(self):
        self.comm = ArduinoComm()
        self.hid = HIDReader()
        self.is_dummy = False
        self.hid_state = {"x": 512, "y": 512, "rudder": 512, "brake": 0}
        self.calibrators = {
            "AILERON": AxisCalibrator("AILERON"),
            "ELEVATOR": AxisCalibrator("ELEVATOR"),
            "RUDDER": AxisCalibrator("RUDDER"),
            "BRAKE": AxisCalibrator("BRAKE", is_brake=True),
        }
        self.current_step_idx = 0
        self.is_monitoring = False
        self.monitor_refs = None
        self.temp_raw_data = {k: {} for k in self.calibrators.keys()}
        self.processing = False
        self.pending_luts = {}
        self.pending_brake = None
        self.connect_task = None


state = AppState()


async def main(page: ft.Page):
    page.title = "Glider Calibrator (Fixed)"
    page.theme_mode = ft.ThemeMode.DARK
    page.window.resizable = True
    page.window.min_width = ui_views.MIN_WINDOW_WIDTH
    page.window.min_height = ui_views.MIN_WINDOW_HEIGHT

    # Page alignment
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    def close_comm():
        try:
            state.comm.close()
        except Exception:
            pass
        try:
            state.hid.close()
        except Exception:
            pass

    def set_dummy_mode(enabled: bool):
        enabled = bool(enabled)
        if state.is_dummy == enabled:
            return
        close_comm()
        state.is_dummy = enabled
        if state.connect_task:
            try:
                state.connect_task.cancel()
            except Exception:
                pass
            state.connect_task = None
        if state.is_dummy:
            state.comm = DummyComm()
            state.hid = DummyHID()
        else:
            state.comm = ArduinoComm()
            state.hid = HIDReader()

    async def enter_monitor():
        if not state.comm.enable_hid():
            page.dialog = ft.AlertDialog(title=ft.Text("HID error"))
            page.dialog.open = True
            page.update()
            return False
        if not state.hid.open():
            page.dialog = ft.AlertDialog(title=ft.Text("HID open failed"))
            page.dialog.open = True
            page.update()
            return False
        state.is_monitoring = True
        state.monitor_refs = await ui_views.show_monitor_view(page, reset_process, exit_app)
        asyncio.create_task(monitor_loop())
        return True

    async def start_monitor(e):
        if state.comm.ser is None:
            if not state.comm.auto_connect():
                await ui_views.show_start_view(
                    page,
                    start_process,
                    start_monitor,
                    False,
                    state.is_dummy,
                    on_toggle_dummy,
                )
                page.dialog = ft.AlertDialog(title=ft.Text("Connection error"))
                page.dialog.open = True
                page.update()
                return
        await enter_monitor()
    async def auto_connect_loop():
        while True:
            if state.is_dummy:
                return
            if state.comm.ser is not None:
                return
            connected = state.comm.auto_connect()
            await ui_views.show_start_view(
                page,
                start_process,
                start_monitor,
                connected,
                state.is_dummy,
                on_toggle_dummy,
            )
            if connected:
                return
            await asyncio.sleep(1.0)

    async def start_process(e):
        if state.comm.ser is None:
            if not state.comm.auto_connect():
                await ui_views.show_start_view(
                    page,
                    start_process,
                    start_monitor,
                    False,
                    state.is_dummy,
                    on_toggle_dummy,
                )
                page.dialog = ft.AlertDialog(title=ft.Text("接続エラー"))
                page.dialog.open = True
                page.update()
                return
        state.current_step_idx = 0
        state.is_monitoring = False
        state.processing = False
        await ui_views.show_calib_wizard(page, state.current_step_idx, next_step)

    async def back_to_start(e=None):
        state.is_monitoring = False
        state.processing = False
        await ui_views.show_start_view(
            page,
            start_process,
            start_monitor,
            state.comm.ser is not None,
            state.is_dummy,
            on_toggle_dummy,
        )
        if state.comm.ser is None and not state.is_dummy:
            state.connect_task = asyncio.create_task(auto_connect_loop())

    async def next_step(e=None):
        # Guard against re-entry
        if state.is_monitoring or state.processing:
            return

        # Prevent out-of-range access
        if state.current_step_idx >= len(ui_views.CALIB_STEPS):
            return

        state.processing = True  # Processing guard

        try:
            step_info = ui_views.CALIB_STEPS[state.current_step_idx]
            axis = step_info["axis"]
            pt_type = step_info["type"]

            # 1. Raw values
            raw = state.comm.get_raw()
            if raw is None:
                page.dialog = ft.AlertDialog(title=ft.Text("取得エラー"))
                page.dialog.open = True
                page.update()
                return

            idx_map = {"AILERON": 0, "ELEVATOR": 1, "RUDDER": 2, "BRAKE": 3}
            val = raw[idx_map[axis]]

            state.temp_raw_data[axis][pt_type] = val
            print(f"Step {state.current_step_idx + 1}: Recorded {axis} {pt_type} = {val}")

            # 2. Next step
            state.current_step_idx += 1

            if state.current_step_idx < len(ui_views.CALIB_STEPS):
                await ui_views.show_calib_wizard(page, state.current_step_idx, next_step)
            else:
                ok, err = await finalize_calibration()
                if ok:
                    if not send_all_luts():
                        return
                    async def on_monitor(e):
                        await enter_monitor()

                    await ui_views.show_complete_view(page, on_monitor, exit_app)
                else:
                    await ui_views.show_error_view(page, err, back_to_start)
        finally:
            state.processing = False  # Processing done

    async def finalize_calibration():
        print("--- Finalizing Calibration ---")
        state.pending_luts = {}
        state.pending_brake = None
        for axis, calib in state.calibrators.items():
            d = state.temp_raw_data[axis]
            raw_min = d.get("min", 0)
            raw_mid = d.get("mid", 512)
            raw_max = d.get("max", 1023)
            if axis != "BRAKE":
                if not ((raw_min <= raw_mid <= raw_max) or (raw_max <= raw_mid <= raw_min)):
                    message = (
                        f"{axis}: center value is not between min and max.\n"
                        "Please restart calibration."
                    )
                    return False, message
            invert = False
            if axis != "BRAKE" and raw_min > raw_max:
                invert = True
                raw_min, raw_max = raw_max, raw_min
            # Fallback when data is missing
            calib.set_points(raw_min, raw_mid, raw_max)
            if axis == "BRAKE":
                state.pending_brake = (calib.min_val, calib.max_val)
            else:
                lut = calib.generate_33_lut()
                if invert:
                    lut = [1023 - v for v in lut]
                state.pending_luts[axis] = lut
        return True, None

    async def reset_process(e):
        state.is_monitoring = False
        state.processing = False
        close_comm()
        await ui_views.show_start_view(
            page,
            start_process,
            start_monitor,
            state.comm.ser is not None,
            state.is_dummy,
            on_toggle_dummy,
        )
        if state.comm.ser is None and not state.is_dummy:
            state.connect_task = asyncio.create_task(auto_connect_loop())


    def send_all_luts():
        if not state.pending_luts and state.pending_brake is None:
            return False
        idx_map = {"AILERON": 0, "ELEVATOR": 1, "RUDDER": 2}
        lut_map = {}
        for axis, idx in idx_map.items():
            lut = state.pending_luts.get(axis)
            if lut is not None:
                print(f"[LUT] Sending {axis}")
                lut_map[idx] = lut
        if state.pending_brake is not None:
            print("[LUT] Sending BRAKE endpoints")
        ok = state.comm.send_lut_batch(lut_map, state.pending_brake)
        if not ok:
            page.dialog = ft.AlertDialog(
                title=ft.Text("Save error"),
                content=ft.Text("LUT save failed."),
            )
            page.dialog.open = True
            page.update()
        return ok

    async def exit_app(e):
        state.is_monitoring = False
        state.processing = False
        close_comm()
        await page.window.close()

    async def monitor_loop():
        import math

        t = 0
        while state.is_monitoring:
            t += 0.1
            refs = state.monitor_refs or {}
            fallback_size = min(
                page.window.width or 0,
                page.window.height or 0,
            )
            plot_size = refs.get("plot_size") or fallback_size
            plot_inner = refs.get("plot_inner") or plot_size
            if plot_inner <= 0:
                plot_inner = 1

            axes = state.hid.read_axes()
            if axes:
                state.hid_state.update(axes)

            x_raw = state.hid_state.get("x", 512)
            y_raw = state.hid_state.get("y", 512)
            rud_raw = state.hid_state.get("rudder", 512)
            brk_raw = state.hid_state.get("brake", 0)

            pointer = refs.get("pointer")
            if pointer:
                plot_mid = plot_inner // 2
                half_span = max(1, (plot_inner // 2) - 10)
                x_norm = (x_raw - 512) / 511
                y_norm = (y_raw - 512) / 511
                pointer.left = plot_mid + int(x_norm * half_span) - 10
                pointer.top = plot_mid + int(y_norm * half_span) - 10

            brk_fill = refs.get("brake_fill")
            rud_fill_pos = refs.get("rudder_fill_pos")
            rud_fill_neg = refs.get("rudder_fill_neg")
            brk_val_txt = refs.get("brake_val")
            rud_val_txt = refs.get("rudder_val")

            def normalize_value(raw):
                return int(round(((raw - 512) / 511) * 100))

            def scale_to_pixels(raw, max_pixels):
                return max(0, min(max_pixels, int(round((raw / 1023) * max_pixels))))

            if brk_fill:
                brk_height = refs.get("brake_height", plot_size)
                brk_norm = max(0, min(100, int(round((brk_raw / 1023) * 100))))
                brk_fill.height = int(round((brk_norm / 100) * brk_height))
            if rud_fill_pos or rud_fill_neg:
                rudder_width = refs.get("rudder_width", plot_inner)
                rud_pixels = scale_to_pixels(abs(rud_raw - 512), rudder_width // 2)
                if rud_fill_pos:
                    rud_fill_pos.width = rud_pixels if rud_raw >= 512 else 0
                    rud_fill_pos.left = rudder_width // 2
                if rud_fill_neg:
                    rud_fill_neg.width = rud_pixels if rud_raw < 512 else 0
                    rud_fill_neg.left = (rudder_width // 2) - rud_pixels
            if brk_val_txt:
                brk_val_txt.value = f"{brk_norm:d}"
            if rud_val_txt:
                rud_val_txt.value = f"{normalize_value(rud_raw):+d}"

            try:
                page.update()
            except RuntimeError:
                state.is_monitoring = False
                break
            await asyncio.sleep(0.03)

    def on_window_event(e):
        if e.data == "close":
            asyncio.create_task(exit_app(None))

    def on_disconnect(e):
        close_comm()
        state.is_monitoring = False

    def on_keyboard(e: ft.KeyboardEvent):
        if e.key == "Enter":
            asyncio.run_coroutine_threadsafe(next_step(), asyncio.get_running_loop())

    def on_resize(e):
        if state.is_monitoring:
            async def refresh_monitor():
                state.monitor_refs = await ui_views.show_monitor_view(page, reset_process, exit_app)
            asyncio.run_coroutine_threadsafe(refresh_monitor(), asyncio.get_running_loop())

    async def on_toggle_dummy(e):
        set_dummy_mode(e.control.value)
        await ui_views.show_start_view(
            page,
            start_process,
            start_monitor,
            state.comm.ser is not None,
            state.is_dummy,
            on_toggle_dummy,
        )
        if state.comm.ser is None and not state.is_dummy:
            state.connect_task = asyncio.create_task(auto_connect_loop())

    page.on_keyboard_event = on_keyboard
    page.on_resize = on_resize
    page.on_window_event = on_window_event
    page.on_disconnect = on_disconnect
    await ui_views.show_start_view(
        page,
        start_process,
        start_monitor,
        state.comm.ser is not None,
        state.is_dummy,
        on_toggle_dummy,
    )
    if state.comm.ser is None and not state.is_dummy:
        state.connect_task = asyncio.create_task(auto_connect_loop())


if __name__ == "__main__":
    ft.run(main)

