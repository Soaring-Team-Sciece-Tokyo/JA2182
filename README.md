このリポジトリは、東京工業大学グライダー部のフライトシミュレータ関連コードを保守・改造するための作業用リポジトリです。  
主に 2 つの要素があります。

- `Calib/`: Windows PC 側で動く較正ツール
- `Firmware/`: 操縦系入力を読み取り、HID ジョイスティックとして出すマイコン側コード

現状の運用前提は「PC で較正し、マイコンへLUTを保存し、その後 HID として使う」です。  

## 1. まず何をすればいいか

まず以下だけ把握すれば十分です。

1. `Firmware/Flight_Control_Prod.ino` をマイコンに書き込む
2. `Calib/` の較正ツールを Windows で起動する
3. UI の指示に従って 11 ステップの較正を行う
4. 保存後、モニタ画面で軸の動きを確認する

もし「コードを直したい」のが目的なら、先に [6. どのファイルをいじるか](#6-どのファイルをいじるか) を読んでください。

## 2. リポジトリ構成

```text
Ka8Sim/
├─ README.md
├─ 3DModels/                         # 機体・筐体まわりの 3D データ
├─ Calib/
│  ├─ config.ini                     # COM ポート設定。AUTO/空欄で自動検出
│  ├─ pyproject.toml                 # Python 依存関係
│  ├─ uv.lock                        # uv 用 lock file
│  ├─ main.spec                      # PyInstaller 設定
│  ├─ Ka8SimCalibrator.spec          # PyInstaller 設定
│  └─ src/
│     ├─ main.py                     # Flet 起動エントリポイント
│     ├─ app.py                      # 状態管理、画面遷移、較正フロー本体
│     ├─ ui_views.py                 # 画面レイアウトと文言
│     ├─ communication.py            # Serial/HID 通信
│     ├─ calibration.py             # LUT 生成ロジック
│     ├─ config.py                   # VID/PID と COM ポート読込
│     ├─ foundDeviceID.py            # 接続デバイスの調査用
│     └─ hid_debug.py                # HID 調査用
└─ Firmware/
   ├─ Flight_Control_Prod.ino        # 現行の本番ファームウェア
   ├─ Flight_Control_Debug.ino       # デバッグ用派生
   ├─ Flight_Control.ino             # 旧版 / 参考実装
   └─ test.ino                       # 通信確認用
```

## 3. システム全体像

処理の流れは次のとおりです。

1. マイコンが `A0` から `A3` のアナログ値を読む
2. PC 側ツールが `*GETRAW` で生値を収集する
3. `Calib/src/calibration.py` が 33 点 LUT を生成する
4. PC 側ツールが `*SETLUT{...}` / `*SETBRK{...}` / `*SAVE` を送る
5. マイコンが EEPROM に保存する
6. マイコンが補正後の値を HID ジョイスティックとして出力する

対応軸は以下です。

- `AILERON`
- `ELEVATOR`
- `RUDDER`
- `BRAKE`

## 4. 開発環境と起動方法

### 4.1 前提

- OS: Windows 前提
- Python: `3.12.5` 以上
- パッケージ管理: `uv`
- マイコン: 現状コードは Arduino 系 HID デバイスを前提

`Calib/pyproject.toml` の主な依存関係:

- `flet[all]`
- `pyserial`
- `numpy`
- `scipy`
- `pywinusb`
- `pyinstaller`

### 4.2 較正ツールの起動

```powershell
cd Calib
uv run src/main.py
```

後輩が普段使う想定は Python 実行ではなく EXE 配布版です。  
その場合は `Calib.exe` を起動するだけでよく、Python や `uv` のセットアップは不要です。

### 4.3 EXE 配布版の扱い

EXE 版を使う人向けの重要点は `config.ini` です。

- `Calib.exe` と同じフォルダに `config.ini` を置く
- COM ポートを固定したいときはその `config.ini` を編集する
- `AUTO` または空欄にすると自動検出になる

EXE 版では、利用者は原則として `Calib/src/config.py` を触る必要はありません。  
PC ごとの差分はまず `config.ini` で吸収する運用を推奨します。

### 4.4 COM ポート設定

COM ポートは `Calib/config.ini` または `Calib/src/config.py` で決まります。

- 推奨: `Calib/config.ini` を使う
- `port = AUTO` または空欄なら自動検出
- 現在のデフォルト値は `COM17`

`Calib/config.ini`

```ini
[serial]
port = COM17
```

`config.py` の実装上、COM ポート設定は次の順で探索されます。

1. EXE と同じフォルダの `config.ini`
2. カレントディレクトリの `config.ini`
3. `Calib/src/config.ini`
4. `Calib/config.ini`

つまり EXE 配布版では、「`Calib.exe` の横に `config.ini` を置く」が最も分かりやすく安全です。

USB VID/PID は `Calib/src/config.py` にあります。

- `USB_VID = 0x2341`
- `USB_PID = 0x8037`

デバイスが見つからないときは `Calib/src/foundDeviceID.py` で確認してください。

### 4.5 ダミーモード

較正ツールにはダミーモードがあります。実機がなくても UI とフロー確認ができます。

- 実装場所: `Calib/src/app.py`
- 通信スタブ: `DummyComm`, `DummyHID`
- 用途: UI 修正、画面遷移確認、モニタ表示確認

実機がない状態で UI を触るなら、まずダミーモードで十分です。

## 5. 較正の流れ

UI 上では次の 11 ステップを順番に記録します。

1. AILERON 左端
2. AILERON 右端
3. AILERON 中立
4. ELEVATOR 上端
5. ELEVATOR 下端
6. ELEVATOR 中立
7. RUDDER 左端
8. RUDDER 右端
9. RUDDER 中立
10. BRAKE 全開
11. BRAKE 全閉

実装上の注意:

- `AILERON`, `ELEVATOR`, `RUDDER` は `min/mid/max` から LUT を生成
- `BRAKE` は端点中心の扱いで、専用の線形 + deadzone ロジックを使う
- 中立値が両端の間に入っていない場合はエラー終了
- LUT 生成に失敗した場合は線形補間にフォールバック

ロジック本体は `Calib/src/calibration.py` にあります。

## 6. どのファイルをいじるか

目的別に見れば、触る場所はほぼ決まっています。

### 6.1 UI 文言や画面を変えたい

- `Calib/src/ui_views.py`

ここに開始画面、較正画面、完了画面、モニタ画面があります。  
ラベルやレイアウト変更はまずここです。

注意:

- 現在このファイルには文字化けした文字列が残っています
- UI 文言の修正は高優先でやってよい変更です
- ただし `CALIB_STEPS` の順序を変えると較正の意味も変わるので注意

### 6.2 較正フローや状態管理を変えたい

- `Calib/src/app.py`

ここがアプリの中心です。

- シリアル接続開始
- 画面遷移
- 生値の記録
- LUT 生成呼び出し
- マイコンへの送信
- モニタ更新

「ボタンを増やす」「途中確認を入れる」「手順を増減する」といった変更はここを見るのが早いです。

### 6.3 通信仕様を変えたい

- PC 側: `Calib/src/communication.py`
- マイコン側: `Firmware/Flight_Control_Prod.ino`

この 2 つは必ずセットで見てください。片方だけ変えるとほぼ確実に壊れます。

### 6.4 補正カーブを変えたい

- `Calib/src/calibration.py`

今は以下の設計です。

- 通常軸: Beta 分布ベースの S 字カーブ
- 失敗時: piecewise linear
- ブレーキ: deadzone 付き線形

操縦感を変えたいならここです。

### 6.5 マイコン入出力や EEPROM 保存を変えたい

- `Firmware/Flight_Control_Prod.ino`

ここでやっていること:

- アナログ入力読み取り
- シリアルコマンド解釈
- LUT の RAM 保持
- EEPROM 保存 / 読み出し
- HID ジョイスティック出力

## 7. 通信プロトコル

シリアル通信は `115200 baud` です。  
PC 側は 1 行 1 コマンドで送っています。

### 7.1 制御コマンド

- `<BEGIN_CALIBRATION>`: 較正モード開始
- `<END_CALIBRATION>`: 較正モード終了
- `*SAVE`: 較正モード中に受け取った LUT を保存
- `*SAVE_ALL`: 較正モードでなくても保存
- `*HID_ON`: HID 出力を有効化
- `*PING`: 応答確認

### 7.2 データ送信

- `*SETLUT{axis_idx,v0,v1,...,v32}`
- `*SETBRK{min,max}`

補足:

- `axis_idx` は `0:AILERON`, `1:ELEVATOR`, `2:RUDDER`, `3:BRAKE`
- 実際の PC 側送信では通常 `BRAKE` は `*SETBRK` を使う

### 7.3 生値取得

- 送信: `*GETRAW`
- 応答: `<RAW{a,e,r,b}>`

### 7.4 ダンプ

- `*DUMP{axis_idx}`
- `*DUMPALL`
- 応答例: `<LUT{axis,...}>`, `<BRK{min,max}>`

### 7.5 成功 / 失敗

- 成功: `<OK>`
- 失敗: `<ERR>`

## 8. ハードウェア対応

`Flight_Control_Prod.ino` では以下の入力を使っています。

- `A0`: AILERON
- `A1`: ELEVATOR
- `A2`: RUDDER
- `A3`: BRAKE

HID 出力側では 4 軸を使います。

- X
- Y
- Rudder 相当
- Brake/Throttle 相当

EEPROM には LUT と brake 端点を保存します。  
起動時に有効な保存値がなければ、線形 LUT で初期化します。

## 9. よくある作業

### 9.1 UI の文言だけ直したい

1. `Calib/src/ui_views.py` を編集
2. `uv run src/main.py` で起動
3. ダミーモードで画面確認

### 9.2 COM ポートが変わった

1. `Calib/config.ini` を開く
2. `port = COMxx` を修正
3. 自動検出したいなら `AUTO` にする

### 9.3 マイコンがつながらない

確認順は以下です。

1. `config.ini` の COM ポート
2. `Calib/src/config.py` の VID/PID
3. 実際の USB デバイス ID
4. マイコン側ファームが正しいか

### 9.4 モニタだけ見たい

- 較正ツール起動
- Start 画面から `Monitor Mode`
- 実機なしならダミーモードで確認可能

## 10. 既知の問題

- `Calib/src/ui_views.py` に文字化けした日本語が残っている
- `Calib/src/app.py` にも一部文字化けメッセージがある
- README 以外の各ディレクトリに個別 README はまだない
- 現行 VID/PID や COM ポートは環境依存なので、別 PC ではそのまま動かないことがある

## 11. 安全に改造するためのルール

壊しやすいポイントだけ先に書きます。

- `communication.py` と `Flight_Control_Prod.ino` の仕様は必ず同期させる
- `CALIB_STEPS` の順番を変えるなら、`app.py` のロジックと合わせて確認する
- `USB_VID`, `USB_PID`, `COM_PORT` はハード依存値なので、コード直書きより `config.ini` 優先が安全
- ブレーキ軸は通常軸と同じ扱いではない
- EEPROM の保存形式を変えると、既存機体の保存データ互換性が壊れる

## 12. LLM / 自動化ツール向けメモ

この節将来このリポジトリを読む別の LLM や自動化ツール向けです。

### 12.1 信頼してよい入口

- PC 側アプリ入口: `Calib/src/main.py`
- PC 側アプリ本体: `Calib/src/app.py`
- UI 定義: `Calib/src/ui_views.py`
- 通信層: `Calib/src/communication.py`
- LUT 生成: `Calib/src/calibration.py`
- 現行本番ファーム: `Firmware/Flight_Control_Prod.ino`

### 12.2 変更時の前提

- 実運用対象は `Flight_Control_Prod.ino`
- `Flight_Control.ino` と `test.ino` は参考用であり、最新仕様と一致する保証はない
- UI 文言には文字化けが混在しているため、自然言語文字列だけを根拠に仕様推定しない
- 通信仕様は README と実装の両方を確認すること
- BRAKEは通常軸と別ロジックで扱うこと

### 12.3 推奨する変更単位

- UI 変更: `ui_views.py` のみ
- 較正フロー変更: `app.py` + 必要に応じて `ui_views.py`
- 通信変更: `communication.py` + `Flight_Control_Prod.ino`
- カーブ変更: `calibration.py`
- 接続設定変更: `config.ini` または `config.py`

### 12.4 変更後に最低限やる確認

- ダミーモードで起動できるか
- 実機接続できるか
- `*GETRAW` が読めるか
- LUT 保存後に `<OK>` が返るか
- モニタ画面で軸が動くか

## 13. 今後の整理候補

すぐ必須ではないですが、次に手を入れる価値があります。

- `Calib/README.md` と `Firmware/README.md` を分ける
- 文字化けした UI 文言を修正する
- 通信仕様を別ファイルに切り出す
- EEPROM 保存形式を明文化する
- ビルド済み配布物の置き場所を決める

## 14. 参考

- Arduino Joystick Library: `MHeironimus/ArduinoJoystickLibrary`



