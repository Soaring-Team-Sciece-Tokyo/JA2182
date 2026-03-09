// test.ino: serial protocol + HID test sketch
#include <Arduino.h>
#include <EEPROM.h>
#include "Joystick.h"

  Joystick_ Joystick(
      JOYSTICK_DEFAULT_REPORT_ID,
      JOYSTICK_TYPE_MULTI_AXIS,
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
const uint8_t SERIAL_BUF_MAX = 200;
const uint8_t EEPROM_MAGIC_ADDR = 0;
const uint8_t EEPROM_DATA_ADDR = 1;
const uint8_t EEPROM_MAGIC = 0xA5;

uint16_t axis_luts[AXIS_COUNT][LUT_POINTS];
bool lut_received[AXIS_COUNT] = {false, false, false, false};
bool calib_active = false;
bool hid_active = true;
bool use_dummy_axes = true;
uint16_t brake_min = 0;
uint16_t brake_max = 1023;

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
  uint16_t y0 = lut[idx];
  uint16_t y1 = lut[idx + 1];
  if (x1 <= x0) {
    return y0;
  }
  int32_t num = (int32_t)(y1 - y0) * (inputValue - x0);
  int32_t den = (x1 - x0);
  return (int)(y0 + (num / den));
}
String serial_buffer;
bool serial_overflow = false;

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

void save_luts() {
  EEPROM.put(EEPROM_DATA_ADDR, axis_luts);
  EEPROM.update(EEPROM_MAGIC_ADDR, EEPROM_MAGIC);
}

bool parse_setlut(const String &line) {
  int left = line.indexOf('{');
  int right = line.lastIndexOf('}');
  if (left < 0 || right <= left) {
    return false;
  }
  String payload = line.substring(left + 1, right);
  if (payload.length() >= 240) {
    return false;
  }
  char buf[240];
  payload.toCharArray(buf, sizeof(buf));
  char *token = strtok(buf, ",");
  if (!token) {
    return false;
  }
  int axis = atoi(token);
  if (axis < 0 || axis >= AXIS_COUNT) {
    return false;
  }
  for (uint8_t i = 0; i < LUT_POINTS; i++) {
    token = strtok(NULL, ",");
    if (!token) {
      return false;
    }
    long v = atol(token);
    if (v < 0 || v > 1023) {
      return false;
    }
    axis_luts[axis][i] = (uint16_t)v;
  }
  if (strtok(NULL, ",") != NULL) {
    return false;
  }
  lut_received[axis] = true;
  return true;
}

bool parse_setbrk(const String &line, uint16_t &out_min, uint16_t &out_max) {
  int left = line.indexOf('{');
  int right = line.lastIndexOf('}');
  if (left < 0 || right <= left) {
    return false;
  }
  String payload = line.substring(left + 1, right);
  char buf[64];
  payload.toCharArray(buf, sizeof(buf));
  char *token = strtok(buf, ",");
  if (!token) {
    return false;
  }
  long v1 = atol(token);
  token = strtok(NULL, ",");
  if (!token) {
    return false;
  }
  long v2 = atol(token);
  if (v1 < 0 || v1 > 1023 || v2 < 0 || v2 > 1023) {
    return false;
  }
  if (v1 > v2) {
    long tmp = v1;
    v1 = v2;
    v2 = tmp;
  }
  out_min = (uint16_t)v1;
  out_max = (uint16_t)v2;
  return true;
}

bool any_lut_received() {
  for (uint8_t i = 0; i < AXIS_COUNT; i++) {
    if (lut_received[i]) {
      return true;
    }
  }
  return false;
}

void send_ok() { Serial.println("<OK>"); }
void send_err() { Serial.println("<ERR>"); }

void dump_axis(int axis) {
  Serial.print("<LUT{");
  Serial.print(axis);
  for (uint8_t i = 0; i < LUT_POINTS; i++) {
    Serial.print(',');
    Serial.print(axis_luts[axis][i]);
  }
  Serial.println("}>");
}

void dump_brake() {
  Serial.print("<BRK{");
  Serial.print(brake_min);
  Serial.print(',');
  Serial.print(brake_max);
  Serial.println("}>");
}

void dump_all() {
  for (uint8_t i = 0; i < AXIS_COUNT; i++) {
    dump_axis(i);
  }
  dump_brake();
}

void handle_command(const String &line) {
  if (line == "<BEGIN_CALIBRATION>") {
    calib_active = true;
    for (uint8_t i = 0; i < AXIS_COUNT; i++) {
      lut_received[i] = false;
    }
    send_ok();
    return;
  }
  if (line == "<END_CALIBRATION>") {
    if (!calib_active) {
      send_err();
      return;
    }
    calib_active = false;
    send_ok();
    return;
  }
  if (line.startsWith("*SETLUT{")) {
    if (!calib_active) {
      send_err();
      return;
    }
    if (parse_setlut(line)) {
      send_ok();
    } else {
      send_err();
    }
    return;
  }
  if (line.startsWith("*SETBRK{")) {
    uint16_t bmin = 0;
    uint16_t bmax = 1023;
    if (parse_setbrk(line, bmin, bmax)) {
      brake_min = bmin;
      brake_max = bmax;
      axis_luts[AXIS_BRAKE][0] = bmin;
      axis_luts[AXIS_BRAKE][LUT_POINTS - 1] = bmax;
      send_ok();
    } else {
      send_err();
    }
    return;
  }
  if (line == "*SAVE") {
    if (!calib_active || !any_lut_received()) {
      send_err();
      return;
    }
    save_luts();
    load_luts();
    send_ok();
    dump_all();
    return;
  }
  if (line == "*SAVE_ALL") {
    if (!any_lut_received()) {
      send_err();
      return;
    }
    save_luts();
    load_luts();
    send_ok();
    dump_all();
    return;
  }
  if (line == "*GETRAW") {
    static const uint16_t patterns[11][4] = {
      {0,   512, 512, 512},  // AILERON min
      {1023,512, 512, 512},  // AILERON max
      {512, 512, 512, 512},  // AILERON mid
      {512, 1023,512, 512},  // ELEVATOR max
      {512, 0,   512, 512},  // ELEVATOR min
      {512, 512, 512, 512},  // ELEVATOR mid
      {512, 512, 0,   512},  // RUDDER min
      {512, 512, 1023,512},  // RUDDER max
      {512, 512, 512, 512},  // RUDDER mid
      {512, 512, 512, 1023}, // BRAKE max
      {512, 512, 512, 0},    // BRAKE min
    };
    static uint8_t idx = 0;
    const uint16_t *p = patterns[idx];
    idx = (idx + 1) % 11;
    Serial.print("<RAW{");
    Serial.print(p[0]);
    Serial.print(',');
    Serial.print(p[1]);
    Serial.print(',');
    Serial.print(p[2]);
    Serial.print(',');
    Serial.print(p[3]);
    Serial.println("}>");
    return;
  }
  if (line == "*HID_ON") {
    hid_active = true;
    send_ok();
    return;
  }
  if (line.startsWith("*DUMP{")) {
    int left = line.indexOf('{');
    int right = line.lastIndexOf('}');
    if (left < 0 || right <= left) {
      send_err();
      return;
    }
    int axis = line.substring(left + 1, right).toInt();
    if (axis < 0 || axis >= AXIS_COUNT) {
      send_err();
      return;
    }
    dump_axis(axis);
    return;
  }
  if (line == "*PING") {
    send_ok();
    return;
  }
  if (line == "*DUMPALL") {
    dump_all();
    return;
  }
  send_err();
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

  if (hid_active) {
    int x = 512;
    int y = 512;
    int rudder = 512;
    int brake = 0;
    if (use_dummy_axes) {
      static uint16_t t = 0;
      t += 1;
      x = (uint16_t)(512 + 200 * sin(t * 0.03));
      y = (uint16_t)(512 + 200 * cos(t * 0.03));
      rudder = (uint16_t)(512 + 300 * sin(t * 0.02));
      brake = (uint16_t)(512 + 400 * cos(t * 0.025));
    } else {
      x = analogRead(A0);
      y = analogRead(A1);
      rudder = analogRead(A2);
      brake = analogRead(A3);
    }
    brake = map(brake, 0, 1023, brake_min, brake_max);
    brake = constrain(brake, brake_min, brake_max);

    x = getCorrectedValue(x, axis_luts[AXIS_X]);
    y = getCorrectedValue(y, axis_luts[AXIS_Y]);
    rudder = getCorrectedValue(rudder, axis_luts[AXIS_RUDDER]);
    brake = getCorrectedValue(brake, axis_luts[AXIS_BRAKE]);

    Joystick.setXAxis(x);
    Joystick.setYAxis(y);
    Joystick.setRudder(rudder);
    Joystick.setBrake(brake);
    Joystick.sendState();
    delay(20);
  }
}
