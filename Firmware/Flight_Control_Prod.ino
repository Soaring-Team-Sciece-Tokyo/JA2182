/*
ジョイスティックライブラリ：https://github.com/MHeironimus/ArduinoJoystickLibrary
*/
#include <Arduino.h>
#include <EEPROM.h>
#include "Joystick.h"

Joystick_ Joystick(
    JOYSTICK_DEFAULT_REPORT_ID,
    JOYSTICK_TYPE_JOYSTICK,
    32, //ボタンの数
    0,
    true,  //X軸 (エルロン)
    true,  //Y軸 (エレベーター)
    true,  //Z軸 (ラダー) ← Generic Desktop 0x32
    false,
    false,
    true,  //Rz軸 (ブレーキ) ← Generic Desktop 0x35
    false, //Rudder OFF
    false,
    false,
    false, //Brake OFF
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
String serial_buffer;
bool serial_overflow = false;
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

void save_luts() {
  EEPROM.put(EEPROM_DATA_ADDR, axis_luts);
  EEPROM.update(EEPROM_MAGIC_ADDR, EEPROM_MAGIC);
}

bool verify_luts_written() {
  if (EEPROM.read(EEPROM_MAGIC_ADDR) != EEPROM_MAGIC) {
    return false;
  }
  uint16_t tmp[AXIS_COUNT][LUT_POINTS];
  EEPROM.get(EEPROM_DATA_ADDR, tmp);
  for (uint8_t axis = 0; axis < AXIS_COUNT; axis++) {
    for (uint8_t i = 0; i < LUT_POINTS; i++) {
      if (tmp[axis][i] != axis_luts[axis][i]) {
        return false;
      }
    }
  }
  return true;
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
    if (!calib_active) {
      send_err();
      return;
    }
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
    if (!verify_luts_written()) {
      send_err();
      return;
    }
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
    if (!verify_luts_written()) {
      send_err();
      return;
    }
    send_ok();
    dump_all();
    return;
  }
  if (line == "*GETRAW") {
    int x = analogRead(A0);
    int y = analogRead(A1);
    int r = analogRead(A2);
    int b = analogRead(A3);
    x = constrain(x, 0, 1023);
    y = constrain(y, 0, 1023);
    r = constrain(r, 0, 1023);
    b = constrain(b, 0, 1023);
    Serial.print("<RAW{");
    Serial.print(x);
    Serial.print(',');
    Serial.print(y);
    Serial.print(',');
    Serial.print(r);
    Serial.print(',');
    Serial.print(b);
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
  if (line == "*DUMPALL") {
    dump_all();
    return;
  }
  if (line == "*PING") {
    send_ok();
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
  pinMode(10, INPUT_PULLUP);
  Serial.begin(115200);
  Joystick.begin(false);
  Joystick.setXAxisRange(0, 1023);
  Joystick.setYAxisRange(0, 1023);
  Joystick.setZAxisRange(0, 1023);   // ラダー
  Joystick.setRzAxisRange(0, 1023);  // ブレーキ
  load_luts();
  Serial.println("<READY>");
}

void loop() {
  poll_serial();

  if (hid_active) {
    int x = analogRead(A0);
    int y = analogRead(A1);
    int rudder = analogRead(A2);
    int brake = analogRead(A3);
    int Release = !digitalRead(10);
    
    brake = map(brake, 0, 1023, brake_min, brake_max);
    brake = constrain(brake, brake_min, brake_max);

    x = getCorrectedValue(x, axis_luts[AXIS_X]);
    y = getCorrectedValue(y, axis_luts[AXIS_Y]);
    rudder = getCorrectedValue(rudder, axis_luts[AXIS_RUDDER]);
    brake = getCorrectedValue(brake, axis_luts[AXIS_BRAKE]);

    
    Joystick.setButton(0, Release);
    Joystick.setXAxis(x);
    Joystick.setYAxis(y);
    Joystick.setZAxis(rudder);   // ラダー → Z軸
    Joystick.setRzAxis(brake);  // ブレーキ → Rz軸
    Joystick.sendState();
    delay(20);
  }
}
