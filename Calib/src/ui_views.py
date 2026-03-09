import flet as ft

MIN_WINDOW_WIDTH = 480
MIN_WINDOW_HEIGHT = 600
GRID_THICKNESS = 1

# Calibration steps definition
CALIB_STEPS = [
    {"axis": "AILERON", "label": "エルロン左いっぱい", "type": "min"},
    {"axis": "AILERON", "label": "エルロン右いっぱい", "type": "max"},
    {"axis": "AILERON", "label": "エルロン中立", "type": "mid"},
    {"axis": "ELEVATOR", "label": "エレベーターアップいっぱい", "type": "max"},
    {"axis": "ELEVATOR", "label": "エレベーターダウンいっぱい", "type": "min"},
    {"axis": "ELEVATOR", "label": "エレベーター中立", "type": "mid"},
    {"axis": "RUDDER", "label": "ラダー左いっぱい", "type": "min"},
    {"axis": "RUDDER", "label": "ラダー右いっぱい", "type": "max"},
    {"axis": "RUDDER", "label": "ラダー中立", "type": "mid"},
    {"axis": "BRAKE", "label": "ダイブブレーキ全開", "type": "max"},
    {"axis": "BRAKE", "label": "ダイブブレーキ全閉", "type": "min"},
]
# --- Start view ---
async def show_start_view(page: ft.Page, on_start, on_monitor, connected: bool, is_dummy: bool, on_toggle_dummy):
    page.controls.clear()
    connected = connected or is_dummy
    status_text = "Dummy mode" if is_dummy else ("Arduino connected" if connected else "Arduino not connected")
    status_color = ft.Colors.AMBER_300 if is_dummy else (ft.Colors.BLUE_200 if connected else ft.Colors.GREY_500)
    button_color = ft.Colors.BLUE_700 if connected else ft.Colors.GREY_700
    ring = ft.ProgressRing() if not connected and not is_dummy else ft.Container(height=0)
    dummy_switch = ft.Switch(label="Dummy mode", value=is_dummy, on_change=on_toggle_dummy)
    content = ft.Column(
        [
            ft.Text("GLIDER CALIBRATOR", size=40, weight=ft.FontWeight.BOLD),
            ft.Text(status_text, italic=True, color=status_color),
            dummy_switch,
            ring,
            ft.ElevatedButton(
                "Start Calibration",
                width=250,
                height=60,
                on_click=on_start,
                bgcolor=button_color,
                disabled=not connected,
                color=ft.Colors.WHITE,
            ),
            ft.ElevatedButton(
                "Monitor Mode",
                width=250,
                height=60,
                on_click=on_monitor,
                bgcolor=button_color,
                disabled=not connected,
                color=ft.Colors.WHITE,
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=30,
    )
    container = ft.Container(content=content, alignment=ft.Alignment(0, 0), expand=True)
    page.add(container)
    page.update()

# --- Calibration wizard ---

async def show_calib_wizard(page: ft.Page, step_idx, on_next):
    page.controls.clear()
    step = CALIB_STEPS[step_idx]
    progress = (step_idx + 1) / len(CALIB_STEPS)

    content = ft.Column(
        [
            ft.Text(f"STEP {step_idx + 1} / {len(CALIB_STEPS)}", size=16, color=ft.Colors.GREY_400),
            ft.Text(step["axis"], size=30, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_200),
            ft.Container(
                content=ft.Text(
                    f"{step['label']}\nOK\u30dc\u30bf\u30f3\u3092\u62bc\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
                    # 「OKボタンを押してください」
                    size=24,
                    text_align=ft.TextAlign.CENTER,
                ),
                padding=15,
                bgcolor=ft.Colors.TRANSPARENT,
                border_radius=15,
                width=600,
                alignment=ft.Alignment(0, 0),
            ),
            ft.ElevatedButton(
                "OK",
                width=200,
                height=70,
                on_click=on_next,
                bgcolor=ft.Colors.BLUE_700,
                color=ft.Colors.WHITE,
            ),
            ft.ProgressBar(width=500, value=progress, color=ft.Colors.BLUE_400),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=30,
    )
    container = ft.Container(content=content, alignment=ft.Alignment(0, 0), expand=True)
    page.add(container)
    page.update()


# --- Error view ---
async def show_error_view(page: ft.Page, message: str, on_back):
    page.controls.clear()
    content = ft.Column(
        [
            ft.Text("CALIBRATION ERROR", size=26, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_300),
            ft.Text(message, size=18, text_align=ft.TextAlign.CENTER),
            ft.ElevatedButton(
                "OK",
                width=220,
                height=60,
                on_click=on_back,
                bgcolor=ft.Colors.BLUE_700,
                color=ft.Colors.WHITE,
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=25,
    )
    container = ft.Container(content=content, alignment=ft.Alignment(0, 0), expand=True)
    page.add(container)
    page.update()


# --- Completion view ---
async def show_complete_view(page: ft.Page, on_monitor, on_exit):
    page.controls.clear()
    content = ft.Column(
        [
            ft.Text("UPDATE COMPLETE", size=28, weight=ft.FontWeight.BOLD),
            ft.Text("Data updated.", color=ft.Colors.BLUE_200),
            ft.Row(
                [
                    ft.ElevatedButton(
                        "Monitor Mode",
                        icon=ft.Icons.PLAY_ARROW,
                        on_click=on_monitor,
                        bgcolor=ft.Colors.BLUE_700,
                        color=ft.Colors.WHITE,
                        width=220,
                        height=60,
                    ),
                    ft.ElevatedButton(
                        "Exit",
                        icon=ft.Icons.CLOSE,
                        on_click=on_exit,
                        bgcolor=ft.Colors.BLUE_900,
                        color=ft.Colors.WHITE,
                        width=160,
                        height=60,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=20,
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=30,
    )
    container = ft.Container(content=content, alignment=ft.Alignment(0, 0), expand=True)
    page.add(container)
    page.update()

# --- Monitor view ---
async def show_monitor_view(page: ft.Page, on_reset, on_exit):
    page.controls.clear()
    window_w = page.window.width or MIN_WINDOW_WIDTH
    window_h = page.window.height or MIN_WINDOW_HEIGHT
    effective_w = max(MIN_WINDOW_WIDTH, window_w)
    effective_h = max(MIN_WINDOW_HEIGHT, window_h)

    left_w = int(effective_w * 0.1)
    center_w = int(effective_w * 0.7)
    right_w = max(GRID_THICKNESS, effective_w - left_w - center_w)

    plot_size = int(min(center_w * 0.95, effective_h * 0.55))
    plot_size = max(GRID_THICKNESS * 10, plot_size)

    plot_inner = plot_size - (plot_size % 4)
    scale_labels_width = max(GRID_THICKNESS * 4, int(plot_size * 0.08))
    tick_band = max(scale_labels_width, int(plot_inner * 0.12))
    tick_w = tick_band
    tick_h = max(GRID_THICKNESS * 6, int(plot_inner * 0.08))
    brake_panel_padding = max(GRID_THICKNESS * 4, int(left_w * 0.08))

    brake_height = plot_size
    brake_width = max(GRID_THICKNESS * 6, int(left_w * 0.6))
    rudder_width = plot_inner
    rudder_height = max(GRID_THICKNESS * 2, int(effective_h * 0.02))

    brake_fill = ft.Container(
        width=brake_width,
        height=0,
        bgcolor=ft.Colors.BLUE_400,
        border_radius=10,
        bottom=0,
    )
    brake_meter = ft.Stack(
        [
            ft.Container(
                width=brake_width,
                height=brake_height,
                bgcolor=ft.Colors.TRANSPARENT,
                border_radius=10,
            ),
            ft.Container(
                width=brake_width,
                height=2,
                bgcolor=ft.Colors.WHITE_24,
                top=(brake_height // 2) - 1,
                left=0,
            ),
            brake_fill,
        ],
        width=brake_width,
        height=brake_height,
    )
    brake_val_text = ft.Text("0", size=12)
    brake_col = ft.Column(
        [
            ft.Text("BRAKE", size=12, weight=ft.FontWeight.BOLD),
            brake_meter,
            brake_val_text,
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    rudder_fill_pos = ft.Container(
        width=0,
        height=rudder_height,
        bgcolor=ft.Colors.BLUE_400,
        border_radius=6,
        left=rudder_width // 2,
        top=0,
    )
    rudder_fill_neg = ft.Container(
        width=0,
        height=rudder_height,
        bgcolor=ft.Colors.BLUE_400,
        border_radius=6,
        left=rudder_width // 2,
        top=0,
    )
    rudder_meter = ft.Stack(
        [
            ft.Container(
                width=rudder_width,
                height=rudder_height,
                bgcolor=ft.Colors.TRANSPARENT,
                border_radius=6,
            ),
            ft.Container(
                width=2,
                height=rudder_height + (GRID_THICKNESS * 6),
                bgcolor=ft.Colors.WHITE_24,
                left=(rudder_width // 2) - 1,
                top=-(GRID_THICKNESS * 3),
            ),
            rudder_fill_neg,
            rudder_fill_pos,
        ],
        width=rudder_width,
        height=rudder_height,
    )
    rudder_val_text = ft.Text("0", size=12)
    rudder_col = ft.Column(
        [
            ft.Text("RUDDER", size=12, weight=ft.FontWeight.BOLD),
            rudder_meter,
            rudder_val_text,
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=6,
    )

    plot_mid = plot_inner // 2
    plot_quarter = plot_inner // 4
    plot_three_quarter = plot_inner - plot_quarter
    inner_span = plot_inner - max(GRID_THICKNESS, 1)
    tick_positions = [int(round(i * inner_span / 4)) for i in range(5)]
    x_labels = ["-100", "-50", "0", "50", "100"]
    y_labels = ["100", "50", "0", "-50", "-100"]
    label_size = 10
    tick_len = max(GRID_THICKNESS * 6, int(plot_inner * 0.06))
    label_band = max(GRID_THICKNESS * 6, int(plot_inner * 0.08), (label_size * 3) + 6)
    if label_band % 2 == 1:
        label_band += 1
    label_box_h = label_size + 4
    if label_box_h % 2 == 1:
        label_box_h += 1
    half_label_band = label_band // 2
    half_label_box = label_box_h // 2
    label_gap = 2
    label_pad = half_label_box
    grid_lines = (
        [
            ft.Container(
                width=plot_inner,
                height=GRID_THICKNESS,
                bgcolor=ft.Colors.WHITE_12,
                left=0,
                top=pos,
            )
            for pos in tick_positions
        ]
        + [
            ft.Container(
                width=GRID_THICKNESS,
                height=plot_inner,
                bgcolor=ft.Colors.WHITE_12,
                left=pos,
                top=0,
            )
            for pos in tick_positions
        ]
    )
    pointer = ft.Container(
        width=20,
        height=20,
        bgcolor=ft.Colors.RED_ACCENT,
        border_radius=10,
        left=plot_mid - 10,
        top=plot_mid - 10,
        key="pointer",
    )

    plot_area = ft.Container(
        content=ft.Stack(grid_lines + [pointer]),
        width=plot_inner,
        height=plot_inner,
        bgcolor=ft.Colors.BLACK_38,
        border_radius=0,
        border=ft.border.all(1, ft.Colors.WHITE_24),
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )

    x_origin = label_band + tick_len
    y_origin = label_pad
    left_ticks = ft.Stack(
        [
            ft.Container(
                width=tick_len,
                height=GRID_THICKNESS,
                bgcolor=ft.Colors.WHITE_24,
                left=0,
                top=pos,
            )
            for pos in tick_positions
        ],
        width=tick_len,
        height=plot_inner,
    )
    bottom_ticks = ft.Stack(
        [
            ft.Container(
                width=GRID_THICKNESS,
                height=tick_len,
                bgcolor=ft.Colors.WHITE_24,
                left=pos,
                top=0,
            )
            for pos in tick_positions
        ],
        width=plot_inner,
        height=tick_len,
    )
    left_labels = ft.Stack(
        [
            ft.Container(
                content=ft.Text(label, size=label_size, color=ft.Colors.WHITE),
                width=label_band,
                height=label_box_h,
                left=0,
                top=pos,
                alignment=ft.Alignment(1, 0),
            )
            for label, pos in zip(y_labels, tick_positions)
        ],
        width=label_band,
        height=plot_inner + label_box_h,
    )
    bottom_labels = ft.Stack(
        [
            ft.Container(
                content=ft.Text(label, size=label_size, color=ft.Colors.WHITE),
                width=label_band,
                height=label_box_h,
                left=pos,
                top=0,
                alignment=ft.Alignment(0, 0),
            )
            for label, pos in zip(x_labels, tick_positions)
        ],
        width=plot_inner + label_band,
        height=label_box_h,
    )

    plot_stack = ft.Stack(
        [
            ft.Container(
                content=plot_area,
                left=x_origin,
                top=y_origin,
            ),
            ft.Container(
                content=left_labels,
                left=0,
                top=y_origin - half_label_box,
            ),
            ft.Container(
                content=left_ticks,
                left=label_band,
                top=y_origin,
            ),
            ft.Container(
                content=bottom_ticks,
                left=x_origin,
                top=y_origin + plot_inner,
            ),
            ft.Container(
                content=bottom_labels,
                left=x_origin - half_label_band,
                top=y_origin + plot_inner + tick_len + label_gap,
            ),
        ],
        width=x_origin + plot_inner + half_label_band,
        height=y_origin + plot_inner + tick_len + label_gap + label_box_h,
    )
    plot_frame = ft.Container(
        width=x_origin + plot_inner + half_label_band,
        height=y_origin + plot_inner + tick_len + label_gap + label_box_h,
        content=plot_stack,
        alignment=ft.Alignment(0, 0),
    )

    rudder_frame = ft.Container(
        width=plot_inner + tick_band + tick_w,
        content=ft.Row(
            [
                ft.Container(width=x_origin),
                rudder_col,
            ],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        ),
        alignment=ft.Alignment(0, 0),
    )

    plot_column = ft.Container(
        width=plot_inner + tick_band + tick_w,
        content=ft.Column(
            [
                rudder_frame,
                plot_frame,
                ft.Text(
                    "STICK MONITOR (AILERON / ELEVATOR)",
                    size=12,
                    weight=ft.FontWeight.BOLD,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=6,
        ),
        alignment=ft.Alignment(0, 0),
    )

    button_height = max(GRID_THICKNESS * 6, int(effective_h * 0.06))

    buttons_layout = ft.Column(
        [
            ft.ElevatedButton(
                "Back to Calibration",
                icon=ft.Icons.REPLAY,
                on_click=on_reset,
                height=button_height,
            ),
            ft.ElevatedButton(
                "Exit",
                icon=ft.Icons.CLOSE,
                bgcolor=ft.Colors.BLUE_900,
                on_click=on_exit,
                height=button_height,
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=8,
    )

    left_panel = ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=brake_col,
                    padding=brake_panel_padding,
                    bgcolor=ft.Colors.TRANSPARENT,
                    border_radius=15,
                    alignment=ft.Alignment(1, 0),
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.END,
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        alignment=ft.Alignment(1, 0),
        expand=3,
    )

    center_panel = ft.Container(
        content=ft.Column(
            [
                plot_column,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        alignment=ft.Alignment(0, 0),
        expand=4,
    )

    right_panel = ft.Container(
        content=ft.Column(
            [
                buttons_layout,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.START,
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        alignment=ft.Alignment(-1, 0),
        padding=ft.padding.symmetric(horizontal=GRID_THICKNESS * 2),
        expand=3,
    )

    layout = ft.Row(
        [
            left_panel,
            center_panel,
            right_panel,
        ],
        alignment=ft.MainAxisAlignment.START,
        expand=True,
    )

    page.add(layout)
    page.update()
    return {
        "pointer": pointer,
        "brake_fill": brake_fill,
        "rudder_fill_pos": rudder_fill_pos,
        "rudder_fill_neg": rudder_fill_neg,
        "brake_val": brake_val_text,
        "rudder_val": rudder_val_text,
        "brake_height": brake_height,
        "rudder_width": rudder_width,
        "plot_inner": plot_inner,
        "plot_size": plot_size,
    }

