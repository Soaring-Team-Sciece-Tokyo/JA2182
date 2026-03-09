# JA2182 - T8 フライトシミュレータ

## About

このリポジトリは、東京工業大学グライダー部が 2022 年度から行っているフライトシミュレータ制作（T8 / Ka8 コックピット再利用）に関連するソフトウェア・ハードウェア資料の引き継ぎ用です。現在の MCU は **Linino One** ですが、販売終了のため入手が難しくなっています。今後は**Arduino Microに置き換える予定**です。

## 1. 構成

本リポジトリのファイル構成を示します。

```
root/
├─ Calib/                 # PC 側の較正ツール (Python/Flet)
│  ├─ src/
│  │  ├─ main.py           # エントリポイント
│  │  ├─ app.py            # 状態管理 + 画面遷移
│  │  ├─ ui_views.py       # UI 表示
│  │  ├─ communication.py  # シリアル + HID 通信
│  │  ├─ calibration.py    # LUT 生成ロジック
│  │  └─ config.py         # VID/PID 設定
│  ├─ dist/Calib.exe       # ビルド済みバイナリ (PyInstaller)
│  ├─ foundDeviceID.py     # VID/PID 調査用スクリプト
│  └─ pyproject.toml       # 依存関係
└─ Firmware/
   ├─ Flight_Control_Prod.ino  # 本番ファーム
   ├─ Flight_Control.ino       # 旧版 / 参考
   └─ test.ino                  # 通信/HID テスト用
```

---

## 2. 依存関係 (Calib)

- Python 3.12 以降
- `uv` （`pyproject.toml` / `uv.lock` を使用）
- 主要ライブラリ: `flet`, `pyserial`, `pywinusb`, `numpy`, `scipy`

---

## 3. 起動方法 (Windows)

### 3.1 Python から起動

```
cd Calib
uv run src/main.py
```

### 3.2 EXE から起動

```
Calib/dist/Calib.exe
```

---

## 4. 較正の流れ

UI の指示に従って**11 ステップ**で生値を取得します。

1. AILERON: 左 (min) / 右 (max) / 中立 (mid)
2. ELEVATOR: 上 (max) / 下 (min) / 中立 (mid)
3. RUDDER: 左 (min) / 右 (max) / 中立 (mid)
4. BRAKE: 全開 (max) / 全閉 (min)

- PC 側で **33 点 LUT** を生成（BRAKE は端点のみ）
- LUT をシリアル送信 → マイコン EEPROM に保存
- 保存後は HID ジョイスティックとして補正値を出力

---

## 5. 通信プロトコル (Firmware)

シリアルは 115200 baud。PC から以下のコマンドを送信します。

### 5.1 制御コマンド

- `<BEGIN_CALIBRATION>` : 較正開始
- `<END_CALIBRATION>` : 較正終了
- `*SAVE` : LUT 保存 (EEPROM 書き込み + dump)
- `*SAVE_ALL` : LUT 保存 (calib 状態でなくても可)
- `*HID_ON` : HID 出力開始
- `*PING` : 応答確認

### 5.2 LUT / ブレーキ設定

- `*SETLUT{axis_idx,v0,v1,...,v32}`
  - `axis_idx` は 0..3
  - 33 個の値 (0..1023)
- `*SETBRK{min,max}`
  - ブレーキ端点のみ更新

### 5.3 生値取得

- `*GETRAW`
  - 返却: `<RAW{a,e,r,b}>` (各 0..1023)
    - `a`：エルロン
    - `e`：エレベータ
    - `r`：ラダー
    - `b`：ダイブブレーキ

### 5.4 ダンプ

- `*DUMP{axis_idx}`
- `*DUMPALL`
  - return: `<LUT{axis, ...}>` + `<BRK{min,max}>`

---

## 6. 入出力仕様 (Firmware)

- アナログ入力
  - A0: Aileron
  - A1: Elevator
  - A2: Rudder
  - A3: Brake
- 出力
  - HID Joystick (X/Y/Rudder/Throttle)
- LUT
  - 33 点 (0..1023)
  - 線形補間で 10bit 値に変換

---

## 7. LUT 生成ロジック (Calib)

- `calibration.py` で **S 字カーブ (Beta 分布ベース)** を生成
- 必要条件: `min < mid < max`
- 失敗時は **線形補間 LUT** に自動フォールバック

---

## 8. 既知の注意点

- `Calib/src/ui_views.py` の一部ラベルが文字化けしている場合があります。
  - UTF-8 で保存されていない場合は修正が必要です。
- VID/PID は `Calib/src/config.py` の `USB_VID`, `USB_PID` を使用します。
  - 例: `0x2341` / `0x8037`
- シリアル接続が確立しない場合は `foundDeviceID.py` で VID/PID を確認してください。

---

## 9. 使い分け

- `Flight_Control_Prod.ino`
  - 本番用。EEPROM に LUT を保存し HID 出力。
- `Flight_Control.ino`
  - 旧版。固定 LUT が入っている参考コード。
- `test.ino`
  - シリアル/HID の検証用。固定パターンで RAW を返す。

---

## 10. よくあるトラブル

- **スタート画面でボタンが無効**
  - シリアル接続が確立していないためです。Arduino を再接続してください。
- **LUT 保存が失敗する**
  - 途中で通信が切れると `<ERR>` になることがあります。再度較正してください。
- **HID が動かない**
  - `*HID_ON` 後に `pywinusb` が認識できているか確認してください。

---

## 11. ライセンス / 参照

- Joystick ライブラリ: MHeironimus/ArduinoJoystickLibrary


