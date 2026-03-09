#include "Joystick.h"
#include <EEPROM.h>

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

// Default LUTs (33-point)
const uint16_t X_CURVE_LUT[33] = {
    0, 30, 60, 91, 121, 152, 184, 215, 246, 277, 309, 341, 372, 404, 436, 468, 500,
    532, 564, 596, 628, 660, 693, 725, 757, 790, 823, 856, 889, 922, 955, 989, 1023};

const uint16_t Y_CURVE_LUT[33] = {
    0, 17, 38, 61, 85, 110, 135, 162, 189, 217, 245, 274, 303, 333, 363, 394, 425,
    457, 489, 522, 556, 589, 624, 659, 694, 731, 768, 806, 845, 885, 927, 971, 1023};

const uint16_t RD_CURVE_LUT[33] = {
    0, 37, 72, 106, 140, 174, 207, 241, 274, 307, 340, 372, 405, 437, 469, 501, 533,
    565, 597, 629, 660, 692, 723, 754, 785, 816, 846, 877, 907, 937, 966, 995, 1023};

const uint8_t AXIS_X = 0;
const uint8_t AXIS_Y = 1;
const uint8_t AXIS_RUDDER = 2;
const uint8_t AXIS_BRAKE = 3;
const uint8_t AXIS_COUNT = 4;
const uint8_t LUT_POINTS = 33;
const uint8_t EEPROM_MAGIC_ADDR = 0;
const uint8_t EEPROM_DATA_ADDR = 1;
const uint8_t EEPROM_MAGIC = 0xA5;

uint16_t axis_luts[AXIS_COUNT][LUT_POINTS];
bool lut_received[AXIS_COUNT] = {false, false, false, false};
bool calib_active = false;
const uint8_t SERIAL_BUF_MAX = 200;
String serial_buffer;
bool serial_overflow = false;

uint16_t x_i(uint8_t idx) {
  return (uint16_t)((1023UL * idx + 16) / 32);
}

void init_default_luts() {
  for (uint8_t i = 0; i < LUT_POINTS; i++) {
    axis_luts[AXIS_X][i] = X_CURVE_LUT[i];
    axis_luts[AXIS_Y][i] = Y_CURVE_LUT[i];
    axis_luts[AXIS_RUDDER][i] = RD_CURVE_LUT[i];
    axis_luts[AXIS_BRAKE][i] = (uint16_t)((1023UL * i + 16) / 32);
  }
}

void load_luts() {
  if (EEPROM.read(EEPROM_MAGIC_ADDR) != EEPROM_MAGIC) {
    init_default_luts();
    return;
  }
  EEPROM.get(EEPROM_DATA_ADDR, axis_luts);
}

void save_luts() {
  EEPROM.put(EEPROM_DATA_ADDR, axis_luts);
  EEPROM.update(EEPROM_MAGIC_ADDR, EEPROM_MAGIC);
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
    send_ok();
    return;
  }
  if (line == "*SAVE_ALL") {
    if (!any_lut_received()) {
      send_err();
      return;
    }
    save_luts();
    send_ok();
    return;
  }
  send_err();
}

void poll_serial() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r') {
      continue;
    }
    if (c == '\n') {
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
  pinMode(2, INPUT);
  pinMode(9, INPUT_PULLUP);
  pinMode(10, INPUT_PULLUP);
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200);
  Joystick.begin(false);
  load_luts();
}

void loop() {
  poll_serial();

  digitalWrite(LED_BUILTIN, 1);
  unsigned int xAxis = analogRead(A0);
  unsigned int yAxis = analogRead(A1);
  unsigned int rudder = analogRead(A2);
  unsigned int AirBrake = analogRead(A3);
  int Release = !digitalRead(10);

  xAxis = getCorrectedValue(xAxis, axis_luts[AXIS_X]);
  yAxis = getCorrectedValue(yAxis, axis_luts[AXIS_Y]);
  rudder = getCorrectedValue(rudder, axis_luts[AXIS_RUDDER]);
  AirBrake = getCorrectedValue(AirBrake, axis_luts[AXIS_BRAKE]);

  Joystick.setXAxis(xAxis);
  Joystick.setYAxis(yAxis);
  Joystick.setRudder(rudder);
  Joystick.setBrake(AirBrake);

  if (Release == 0) {
    Joystick.releaseButton(0);
  } else {
    Joystick.pressButton(0);
  }

  Joystick.sendState();
  delay(50);
}
