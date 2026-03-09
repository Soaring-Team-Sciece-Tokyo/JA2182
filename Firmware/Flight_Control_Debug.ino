/*
Debug sketch for HID/analog troubleshooting.
Sends joystick HID reports and prints raw/processed values over Serial.
*/
#include <Arduino.h>
#include <EEPROM.h>
#include "Joystick.h"

Joystick_ Joystick(
    JOYSTICK_DEFAULT_REPORT_ID,
    JOYSTICK_TYPE_JOYSTICK,
    32,
    0,
    true,
    true,
    false,
    false,
    false,
    false,
    true,
    false,
    false,
    true,
    false);

const uint8_t AXIS_X = 0;
const uint8_t AXIS_Y = 1;
const uint8_t AXIS_RUDDER = 2;
const uint8_t AXIS_BRAKE = 3;
const uint8_t AXIS_COUNT = 4;
const uint8_t LUT_POINTS = 33;
const uint8_t SERIAL_BUF_MAX = 120;
const uint8_t EEPROM_MAGIC_ADDR = 0;
const uint8_t EEPROM_DATA_ADDR = 1;
const uint8_t EEPROM_MAGIC = 0xA5;

uint16_t axis_luts[AXIS_COUNT][LUT_POINTS];
uint16_t brake_min = 0;
uint16_t brake_max = 1023;
String serial_buffer;
bool serial_overflow = false;
bool raw_dump_enabled = true;
bool lut_enabled = true;
unsigned long last_dump_ms = 0;
const unsigned long dump_interval_ms = 50;

uint16_t x_i(uint8_t idx) {
  return (uint16_t)((1023UL * idx + 16) / 32);
}

int getCorrectedValue(int inputValue, const uint16_t *lut) {
  if (inputValue <= 0) {
    return lut[0];
  }
  if (inputValue >= 1023) {
    return lut[LUT_POINTS - 1];
  }
  uint8_t idx = (uint8_t)((inputValue * 32UL) / 1023UL);
  if (idx >= (LUT_POINTS - 1)) {
    idx = LUT_POINTS - 2;
  }
  uint16_t x0 = x_i(idx);
  uint16_t x1 = x_i(idx + 1);
  int32_t y0 = (int32_t)lut[idx];
  int32_t y1 = (int32_t)lut[idx + 1];
  if (x1 <= x0) {
    int out = (int)y0;
    if (out < 0) {
      return 0;
    }
    if (out > 1023) {
      return 1023;
    }
    return out;
  }
  int32_t num = (y1 - y0) * (inputValue - x0);
  int32_t den = (x1 - x0);
  int32_t out = y0 + (num / den);
  if (out < 0) {
    return 0;
  }
  if (out > 1023) {
    return 1023;
  }
  return (int)out;
}

void init_default_luts() {
  for (uint8_t axis = 0; axis < AXIS_COUNT; axis++) {
    for (uint8_t i = 0; i < LUT_POINTS; i++) {
      axis_luts[axis][i] = (uint16_t)((1023UL * i + 16) / 32);
    }
  }
  brake_min = axis_luts[AXIS_BRAKE][0];
  brake_max = axis_luts[AXIS_BRAKE][LUT_POINTS - 1];
}

void load_luts() {
  if (EEPROM.read(EEPROM_MAGIC_ADDR) != EEPROM_MAGIC) {
    init_default_luts();
    return;
  }
  EEPROM.get(EEPROM_DATA_ADDR, axis_luts);
  brake_min = axis_luts[AXIS_BRAKE][0];
  brake_max = axis_luts[AXIS_BRAKE][LUT_POINTS - 1];
}

void dump_raw(int x, int y, int r, int b, int cx, int cy, int cr, int cb) {
  Serial.print("<RAW{");
  Serial.print(x); Serial.print(',');
  Serial.print(y); Serial.print(',');
  Serial.print(r); Serial.print(',');
  Serial.print(b);
  Serial.print("}>");
  Serial.print(" <COR{");
  Serial.print(cx); Serial.print(',');
  Serial.print(cy); Serial.print(',');
  Serial.print(cr); Serial.print(',');
  Serial.print(cb);
  Serial.println("}>");
}

void dump_axis(int axis) {
  Serial.print("<LUT{");
  Serial.print(axis);
  for (uint8_t i = 0; i < LUT_POINTS; i++) {
    Serial.print(',');
    Serial.print(axis_luts[axis][i]);
  }
  Serial.println("}>");
}

void dump_all() {
  for (uint8_t i = 0; i < AXIS_COUNT; i++) {
    dump_axis(i);
  }
}

void handle_command(const String &line) {
  if (line == "*RAW_ON") {
    raw_dump_enabled = true;
    Serial.println("<OK>");
    return;
  }
  if (line == "*RAW_OFF") {
    raw_dump_enabled = false;
    Serial.println("<OK>");
    return;
  }
  if (line == "*LUT_ON") {
    lut_enabled = true;
    Serial.println("<OK>");
    return;
  }
  if (line == "*LUT_OFF") {
    lut_enabled = false;
    Serial.println("<OK>");
    return;
  }
  if (line == "*LUT_DEFAULT") {
    init_default_luts();
    Serial.println("<OK>");
    return;
  }
  if (line.startsWith("*LUT_DUMP{")) {
    int left = line.indexOf('{');
    int right = line.lastIndexOf('}');
    if (left < 0 || right <= left) {
      Serial.println("<ERR>");
      return;
    }
    int axis = line.substring(left + 1, right).toInt();
    if (axis < 0 || axis >= AXIS_COUNT) {
      Serial.println("<ERR>");
      return;
    }
    dump_axis(axis);
    return;
  }
  if (line == "*LUT_DUMPALL") {
    dump_all();
    return;
  }
  if (line == "*PING") {
    Serial.println("<OK>");
    return;
  }
  Serial.println("<ERR>");
}

void poll_serial() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == 13) {
      continue;
    }
    if (c == 10) {
      if (serial_overflow) {
        serial_overflow = false;
        serial_buffer = "";
        continue;
      }
      if (serial_buffer.length() > 0) {
        handle_command(serial_buffer);
        serial_buffer = "";
      }
      continue;
    }
    if (serial_overflow) {
      continue;
    }
    if (serial_buffer.length() < SERIAL_BUF_MAX) {
      serial_buffer += c;
    } else {
      serial_overflow = true;
    }
  }
}

void setup() {
  pinMode(A0, INPUT);
  pinMode(A1, INPUT);
  pinMode(A2, INPUT);
  pinMode(A3, INPUT);
  Serial.begin(115200);
  Joystick.begin(false);
  Joystick.setXAxisRange(0, 1023);
  Joystick.setYAxisRange(0, 1023);
  Joystick.setRudderRange(0, 1023);
  Joystick.setBrakeRange(0, 1023);
  load_luts();
  Serial.println("<READY>");
}

void loop() {
  poll_serial();

  int x = analogRead(A0);
  int y = analogRead(A1);
  int rudder = analogRead(A2);
  int brake = analogRead(A3);

  x = constrain(x, 0, 1023);
  y = constrain(y, 0, 1023);
  rudder = constrain(rudder, 0, 1023);
  brake = constrain(brake, 0, 1023);

  int brake_scaled = map(brake, 0, 1023, brake_min, brake_max);
  brake_scaled = constrain(brake_scaled, brake_min, brake_max);

  int cx = x;
  int cy = y;
  int cr = rudder;
  int cb = brake_scaled;
  if (lut_enabled) {
    cx = getCorrectedValue(x, axis_luts[AXIS_X]);
    cy = getCorrectedValue(y, axis_luts[AXIS_Y]);
    cr = getCorrectedValue(rudder, axis_luts[AXIS_RUDDER]);
    cb = getCorrectedValue(brake_scaled, axis_luts[AXIS_BRAKE]);
  }

  Joystick.setXAxis(cx);
  Joystick.setYAxis(cy);
  Joystick.setRudder(cr);
  Joystick.setBrake(cb);
  Joystick.sendState();

  unsigned long now = millis();
  if (raw_dump_enabled && (now - last_dump_ms >= dump_interval_ms)) {
    last_dump_ms = now;
    dump_raw(x, y, rudder, brake, cx, cy, cr, cb);
  }

  delay(10);
}
