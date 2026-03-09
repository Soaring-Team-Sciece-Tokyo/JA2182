# /// script
# dependencies = [
#   "pywinusb",
# ]
# ///

import pywinusb.hid as hid

for dev in hid.HidDeviceFilter().get_devices():
    try:
        print(
            f"VID=0x{dev.vendor_id:04X} PID=0x{dev.product_id:04X} "
            f"{dev.product_name}"
        )
    except Exception as e:
        print("error:", e, getattr(dev, "device_path", ""))
