# Monitoring solar power generator with RPi5 Ble

[日本語の説明はこちら](#Japanese)

This is a machine translation. There may be miss translation.

## Overview of this project
The capacity of the AGM battery for the off-grid solar power generation in my workshop has decreased over time, so I replaced the battery with a LiFe battery and updated the charge controller to be LiFe compatible.

My new battery and charge controller are equipped with Bluetooth LE as standard, so they can be monitored from a smartphone app. Since I had the chance, I decided to graph the amount of power generated and the remaining capacity with the RaspberryPi5.

### Configuration of my new solar power generation system
* [Vatrer 12V 300AH Bluetooth LiFePO4 Lithium Battery with Self-Heating](https://www.vatrerpower.com/products/vatrer-12v-300ah-bluetooth-lifepo4-lithium-battery-with-self-heating-200a-bms-supports-low-temp-charging-4-f-5000-cycles-2560w-power): 2 units
* [60A Solar MPPT 12V/24V/36V/48V Bluetooth Charge Controller](https://www.litime.com/products/60a-mppt-with-bluetooth): 1 unit
* [110W class 12V power generation panel](https://gwsolar-store.com/products/%e5%bd%b1%e3%81%ab%e5%bc%b7%e3%81%84-gwsolar%e3%80%90-%e5%a4%aa%e9%99%bd%e5%85%89%e3%83%91%e3%83%8d%e3%83%ab100w%e3%80%91-%e5%85%a8%e4%b8%a6%e5%88%97%e3%82%bd%e3%83%bc%e3%83%a9%e3%83%bc%e3%83%91/): 4 in parallel

### RPi5 configuration
#### RPi5 hardware materials
* [RPi5](https://www.raspberrypi.com/products/raspberry-pi-5/)
* [RTC battery](https://www.raspberrypi.com/products/rtc-battery/)
* [Active cooler](https://www.amazon.com/dp/B0CNVFCWQR)
* [7-inch DSI touch screen](https://osoyoo.com/2024/05/15/osoyoo-7-ips-touch-screen-for-raspberry-pi/)
* [All-in-one case](https://osoyoo.com/2024/05/28/instruction-of-osoyoo-pistudio-case-all-in-one-desktop-solution-for-raspberry-pi-model-2024003100/)
#### RPi5 software materials
* [mosquitto](https://github.com/eclipse-mosquitto/mosquitto)
* [InfluxDB](https://github.com/influxdata/influxdb)
* [Grafana](https://github.com/grafana/grafana)
* [Python](https://www.python.org/)
  * [Break](https://github.com/hbldh/bleak)
  * [Paho MQTT Python](https://github.com/eclipse/paho.mqtt.python)
  * [Influxdb Client Python](https://github.com/influxdata/influxdb-client-python)

The data flow is "BluetoothLE -> mosquitto -> InfluxDB -> Grafana", and I implemented "BluetoothLE -> mosquitto" and "mosquitto -> InfluxDB" in Python.

## Installation procedure

1) Generate an ssh_key pair to use for connecting to RPi5. (The generated key pair will be used later)

2) Start [RasbperryPi Imager](https://www.raspberrypi.com/software/) on your PC -> RASPBERRY PI 5 -> RASPBERRY PI OS (64bit) -> Select microSD -> Next -> EditConfig -> General: SetUserNamePassword, SetLocale Service: SSH, PublicKey (PubKey generated in 1.) -> Save -> Yes -> Yes to write to microSD

3) Assemble a 7-inch DSI touch screen in an all-in-one case, and attach the RPi5 with the RTC battery + active cooler + microSD. <br>
The initial settings are controlled by the PC (Ansible host) via the network, so connect the RPi5 and the PC running the Ansible host to the same network and start the RPi5. (If the PC used for initial setup is Windows, it is easier to install Ansible on Ubuntu in WSL2.)<br>
The IP address of the RPi5 is obtained by DHCP, so make a note of the IP address that appears in the upper right corner of the RPi5 desktop screen immediately after it starts up. (You will need to enter the IP address of the RPi5 in the Ansible configuration file later.)<br>
The RPi5 downloads packages from the Internet during setup by the Ansible host, so the RPi5 needs to have Internet connectivity during setup. (Note that the RPi5 can operate offline after the initial setup is complete.)

4) Open .\inventories\host_vars\target.yaml on the PC, delete the # at the beginning of the line, and write the IP address, password, device name, etc. of the RPi5 and save it.<br>
Load the SSH PrivateKey (the PrivateKey generated in 1.) into ssh_agent on the PC running the Ansible host, and run ./play.sh. (The Ansible host will start, and the RPi5 will automatically restart while the settings are being made. If the PLAY RECAP unreachable and failed are 0 at the end, the settings are successful.)

5) Install near the charge controller and battery. (The status of the charge controller and battery obtained via Ble will be displayed on the RPi touch screen.)

## Difficulty and ingenuity during development
### Communication protocol investigation
There was no protocol documentation for the charge controller on the manufacturer's website, but I was able to connect via Ble and send and receive MODBUS packets using the vendor's unique UUID.

There is protocol documentation for the battery on the BMS manufacturer's website, but even when I connected via Ble and sent a packet according to the protocol using the vendor's unique UUID, there was no response. <br>
Compared to the behavior of the Android Xiaoxiang app, it seems that [BMS will not respond unless password authentication is performed after Ble connection](https://diysolarforum.com/threads/jbd-bms-i-set-the-bluetooth-password-in-the-xiaoxiang-app-and-now-i-cant-connect-with-overkill-app.83662/). <br>
Since there is no explanation of Ble password authentication in the JBD documentation, I analyzed the Xiaoxiang app. For the analysis, I used [jadx](https://github.com/skylot/jadx). <br>
I imitated the authentication procedure by trial and error, referring to sendAppKey, sendFirstLevPsw, and sendRootPsw in com.jiabaida.little_elephant.util.BleUtils. <br>
(The authentication procedure may differ depending on the version of the BMS and the BMS Ble adapter, but both of the batteries purchased this time were able to communicate using my imitated authentication procedure.)

### Device not responding, but it was a Bluez bug
When I was trying to check the operation of my imitated authentication procedure by repeating "Ble connection → data collection → Ble disconnection" for each device, I found that the device would occasionally be unable to connect to Ble. (At this time, turning off and on the RPi's Bluetooth would allow it to connect.)

After some research, I found that [Linux bluez has a bug where it does not respond when disconnected](https://github.com/bluez/bluez/issues/947).

It seems that it will take some time for the fixed version to be reflected in the RPi update, so as a workaround, I changed it so that Ble does not disconnect even after data collection.

### Downsampling of InfluxDB
The device status is collected every 27 seconds on a per-device basis, taking into account the device response time via Ble + a margin of response time. <br>
I want to keep the data for 10 years because I want to compare the collected power generation and charging/discharging status with records from the same period in the past. <br>
If the data is stored raw, it will be over 1M samples in a year, and over 10M samples in 10 years, which is a concern for the load on the RPi when displaying data, so we considered reducing the load by downsampling old data like RRD. <br>
Measurements such as current and voltage are aggregated using three types: mean, max, and min, fixed values ​​and binary values ​​are aggregated using last, and bit flags are aggregated using bit_or. <br>
Create a bucket for each retention period, create a measurement for each aggregation method, and create a tag using device identification information.

#### Data storage amount calculation
* Period from now to 24 hours ago: Raw data: 3k samples
* Period from now to 7 days ago: Downsampled in 2-minute span: 5k samples
* Period from now to 1 month ago: Downsampled in 5-minute span: 8k samples
* Period from now to 1 year ago: Downsampled in 30-minute span: 18k samples
* Period from now to 10 years ago: Downsampled in 2-hour span: 44k samples

Total: 78k samples<br>
Actual Bucket size for 24 hours ago after several days of operation was 4.9MByte. Therefore, the estimated DB capacity is about 128MByte.

### Problems with InfluxDB task offset
I set task.offset to shift the timing of the aggregation process so that the transmission delay via mqtt does not affect the downsampling. <br>
The Flux started by the task is set to the time offset by Now(), so there was no need to be aware of the offset in the aggregation process, which was easy. <br>
It seemed to be going well without any missing data, but when I restarted the RPi5, I found that downsampling was not performed from "shutdown time - offset" to "start time". <br>
The symptom was that the task would not start until the offset time had passed after startup. <br>
I left task.offset unspecified, and changed the method to calculate the start and stop of the target to be aggregated within the Flux process and pass them to Range.

### Vertical axis of current graph
The controller's battery current is recorded as the MPPT output current (current generated) as a positive value, and the load current is recorded as the load terminal output current (current consumed) as a positive value. <br>
The battery's charge current is recorded as a positive value when the battery is charged, and a negative value when the battery is discharged. <br>
When displaying current values ​​in one graph in Grafana, the signs were adjusted so that supply (power generation & discharge) is a positive value and consumption (load & charge) is a negative value.

### 7-inch DSI touch screen + all-in-one case
I chose this product because it has a touch panel LCD, a special case so the board is not exposed, and easy connection with DSI.

* The resolution is 800x480, so the amount of information that can be displayed is limited.
* The microSD cannot be inserted or removed unless the screws fixing the RPi5 are removed.

For this reason, I omitted the title of the Grafana graph panel to increase the amount of information and visibility as much as possible. <br>
When viewing past data stored on the microSD by the RPi5, I decided to access the RPi5's Grafana from a PC via the network and display it. <br>
The microSD tends to be inserted and removed many times during development, but the configuration procedure was automated with Ansible, reducing the need to rewrite the OS due to work errors or missed steps.

## References
### Controller reference material
https://diysolarforum.com/threads/charge-controllers-that-have-low-temp-protection.66378/

https://www.helios-ne.com/jp/60a-mppt-charge-controller-12-24-36-48v-auto-negative-grounded-model.html

https://www.hobbielektronika.hu/forum/getfile.php?id=403514

### BMS reference material
https://jiabaida-bms.com/pages/download-files

https://github.com/FurTrader/OverkillSolarBMS/tree/master/Comm_Protocol_Documentation

### Communication protocol reverse engineering reference material
https://github.com/Olen/solar-monitor/blob/master/REVERSE-ENGNEER.md
https://github.com/snichol67/solar-bt-monitor

# RPi５のBleでソーラー発電モニター (Japanese)<a name="Japanese"></a>

## このプロジェクトの概略
作業小屋のオフグリッドソーラー発電のAGMバッテリーが経年で容量低下したので、バッテリーをLiFeに交換しつつ充電コントローラーもLiFe対応に更新した。

新しいバッテリーと充電コントローラはBluetoothLE標準装備で、スマホアプリからモニタリングできる。せっかくなので、RasbperryPi5で発電量と残容量のグラフ化してみることにした。

### 新しいソーラー発電システムの構成
* [Vatler 12V 300AH Bluetooth LiFePO4 リチウム電池（自己発熱付き）](https://www.vatrerpower.com/ja-jp/products/vatrer-12v-300ah-bluetooth-lifepo4-lithium-battery-with-self-heating-jp) ：２台
* [LiTime60A MPPT チャージコントローラー](https://jp.litime.com/products/60a-mppt-with-bluetooth)：１台
* [110W級12V発電パネル](https://gwsolar-store.com/products/%e5%bd%b1%e3%81%ab%e5%bc%b7%e3%81%84-gwsolar%e3%80%90-%e5%a4%aa%e9%99%bd%e5%85%89%e3%83%91%e3%83%8d%e3%83%ab100w%e3%80%91-%e5%85%a8%e4%b8%a6%e5%88%97%e3%82%bd%e3%83%bc%e3%83%a9%e3%83%bc%e3%83%91/)：4並列

### RPi5の構成
#### RPi5のハードウエア構成
* [RPi5](https://www.raspberrypi.com/products/raspberry-pi-5/)
* [RTCバッテリー](https://www.raspberrypi.com/products/rtc-battery/)
* [Activeクーラー](https://www.amazon.com/dp/B0CNVFCWQR)
* [7インチDSIタッチスクリーン](https://osoyoo.com/2024/05/15/osoyoo-7-ips-touch-screen-for-raspberry-pi/)
* [All-in-oneケース](https://osoyoo.com/2024/05/28/instruction-of-osoyoo-pistudio-case-all-in-one-desktop-solution-for-raspberry-pi-model-2024003100/)

#### RPi5のソフトウエア構成
* [mosquitto](https://github.com/eclipse-mosquitto/mosquitto)
* [InfluxDB](https://github.com/influxdata/influxdb)
* [Grafana](https://github.com/grafana/grafana)
* [Python](https://www.python.org/)
  * [Break](https://github.com/hbldh/bleak)
  * [Paho MQTT Python](https://github.com/eclipse/paho.mqtt.python)
  * [Influxdb Client Python](https://github.com/influxdata/influxdb-client-python)

データの流れは「BluetoothLE -> mosquitto -> InfluxDB -> Grafana」とし、「BluetoothLE -> mosquitto」と「mosquitto -> InfluxDB」はPythonで実装。

## 導入手順

1) RPi5の接続に使用するにssh_keyペアを生成する。(生成したKeyペアは後で使用する)

2) PCで[RasbperryPi Imager](https://www.raspberrypi.com/software/)を起動 -> RASPBERRY PI 5 -> RASPBERRY PI OS(64bit) -> microSD選択 -> Next -> EditConfig -> General:SetUserNamePassword,SetLocale Service:SSH,PublicKey(1.で生成したPubKey） -> Save -> Yes -> Yes でmicroSDに書き込む

3) All-in-oneケースに7インチDSIタッチスクリーンを組み付け、RTCバッテリー＋Activeクーラー＋上記microSDを装着したRPi5をに取り付ける。<br>
初期設定はPC(Ansibleホスト)からネットワーク経由でRPi5を制御して行うので、RPi5とAnsibleホストを実行するPCを同じネットワークに接続してRPi5を起動する。（初期設定に使用するPCがWindowsの場合はWSL2のUbuntuにAnsibleをインストールすると手軽）<br>
RPi5のIPアドレスはDHCPで取得するため、RPi5のデスクトップ画面起動直後に画面右上に表示されるIPアドレスをメモしておく。（後ほどAnsibleの設定ファイルにRPi5のIPアドレスを記載する必要あり）<br>
Ansibleホストによる設定作業でRPi5はインターネットからパッケージをダウンロードするため、設定作業中のRPi5はインターネット接続性が必要。（なお、初期設定完了後はRPi5はオフラインで動作可能）

4) PCで.\inventories\host_vars\target.yaml を開き、行頭の#を削除して、RPi5のIPアドレス、パスワード、デバイス名などを記載して保存する。<br>
Ansibleホストを実行するPCでSSHのPrivateKey(1.で生成したPrivKey)をssh_agentにロードし、./play.sh を実行する。（Ansibleホストが起動し、自動でRPi5を再起動しつつ設定を進め、最後にPLAY RECAPのunreachableおよびfailedが0で終了すれば設定成功。）

5) 充電コントローラおよびバッテリーの近くに設置する。(Ble経由で取得した充電コントローラおよびバッテリーの状態がRPiのタッチスクリーンに表示される。)

## 開発中に苦労・工夫した箇所
### 通信プロトコル調査
チャージコントローラーはメーカーサイトにプロトコル資料が無かったが、Bleで接続してベンダーユニークなUUIDでMODBUSパケットを送受信できた。

バッテリーはBMSメーカーサイトにプロトコルの資料があるが、Bleで接続してベンダーユニークなUUIDでプロトコルに沿ったパケットを投げても無応答。<br>
AndroidのXiaoxiangアプリの動作と見比べると、[Ble接続後にパスワード認証を行わないとBMSが応答しない](https://diysolarforum.com/threads/jbd-bms-i-set-the-bluetooth-password-in-the-xiaoxiang-app-and-now-i-cant-connect-with-overkill-app.83662/)ようだった。<br>
JBDの資料にはBleパスワード認証の説明がないので、Xiaoxiangアプリを解析。解析には[jadx](https://github.com/skylot/jadx)を使用。<br>
com.jiabaida.little_elephant.util.BleUtilsのsendAppKey、sendFirstLevPsw、sendRootPswを参考にしつつトライ＆エラーで認証手順を模造した。<br>
（BMSおよびBMSのBleアダプタのバージョンによって認証手順が異なる可能性があるが、今回購入したバッテリーは２台とも模造した認証手順で通信できた。）

### デバイス無応答と思ったらBluezのバグ
模造した認証手順の動作確認で、デバイス各々で「Ble接続→データ収集→Ble切断」を繰り返すようにして試していたところ、不定期にデバイスにBle接続できなくなる症状が発生。（このときRPiのBluetoothをoff/ONすると接続できるようになる。）<br>
あれこれ調べたところ[Linuxのbluezが切断時に応答を返さないバグがある](https://github.com/bluez/bluez/issues/947)との事。<br>
対策版がRPiのUpdateに反映されるまで時間を要しそうなので、回避策としてデータ収集後もBle切断しないように変更。

### InfluxDBのダウンサンプル
デバイスのステータス収集はBle経由でのデバイスの応答時間＋余裕時間を考慮して、デバイス単位で27秒毎にステータス収集をおこなう事とした。<br>
収集した発電状況・充放電状況は過去年同時期の記録と比較したくなるので、10年間のデータ保持をしておきたい。<br>
データを生のまま保持すると1年で約1Mサンプル超、10年だと10Mサンプル超となりRPiでは表示処理の負荷が心配なので、RRDみたいに古いデータをダウンサンプルすることで負荷を軽くすることを検討した。<br>
電流電圧などの測定値はmean・max・minの３種で集約、固定値やバイナリ値はlast、ビットフラグはbit_orで集約する。<br>
保持期間毎にBucketを作成、集計方法毎にMeasurementを作成、デバイス識別情報でtagを作成とする。

#### データ保存量試算
* 現在から24時間前までの期間：生データ：3kサンプル
* 現在から7日前までの期間：2分スパンでダウンサンプル：5kサンプル
* 現在から1か月前までの期間：5分スパンでダウンサンプル：8kサンプル
* 現在から1年前までの期間：30分スパンでダウンサンプル：18kサンプル
* 現在から10年前までの期間：2時間スパンでダウンサンプル：44kサンプル

合計：78kサンプル<br>
数日動かした状況の24時間前用Bucketサイズ実測で4.9MByte。よって推定DB容量は約128MByte。

### InfluxDBのタスクoffsetの不都合
mqtt経由での伝達遅延がダウンサンプルに影響しないようにtask.offsetで集計処理タイミングをズラす設定を行った。<br>
タスクで起動するFluxはNow()がoffsetした時刻になるとの事で、集計処理でoffsetを意識する必要はなく簡単だった。<br>
取りこぼしもなく順調と思われたが、RPi5を再起動した際に「シャットダウン時刻-offset」～「起動時刻」のダウンサンプルが行われていないことに気づいた。<br>
症状的には起動してからoffset時間を経過しないとタスクを起動しないようだった。<br>
task.offsetは未指定にして、Flux処理内で集計対象のstart,stopを算定してRangeに渡す方法に変更した。

### 電流値グラフの縦軸
コントローラーのBattery電流値はMPPTの出力電流量(発電電流)が正値で、Load電流値はLoad端子の出力電流量（消費電流）が正値で記録される。<br>
バッテリーのCharge電流値はバッテリー充電時に正値、バッテリー放電時に負値が記録される。<br>
Grafanaで電流値を１つのグラフに表示する際に、供給(発電&放電)が正値、消費(負荷&充電)が負値になるように符号を調整した。

### 7インチDSIタッチスクリーン＋All-in-oneケース
「タッチパネル液晶、専用ケースで基板がむき出しにならない、DSIで接続簡単」という点を重視しで選定したが、
* 解像度が800x480なので表示できる情報量は限られる。
* RPi5を固定しているネジを外さないとmicroSDを挿抜できない。

このためGrafanaのグラフパネルのタイトルを省略して、情報量と視認性を少しでも高めるようにした。<br>
RPi5がmicroSDに蓄積した過去データを見る際は、PCからネットワーク経由でRPi5のGrafanaにアクセスして表示することとした。<br>
開発中はmicroSDの挿抜回数が多くなりやすいが、設定手順をAnsibleで自動化し、作業ミスや手順漏れに伴うOS再書込みを削減した。

## 参考
### コントローラー参考資料
https://diysolarforum.com/threads/charge-controllers-that-have-low-temp-protection.66378/

https://www.helios-ne.com/jp/60a-mppt-charge-controller-12-24-36-48v-auto-negative-grounded-model.html

https://www.hobbielektronika.hu/forum/getfile.php?id=403514

### BMS参考資料
https://jiabaida-bms.com/pages/download-files

https://github.com/FurTrader/OverkillSolarBMS/tree/master/Comm_Protocol_Documentation

### 通信プロトコルのリバースエンジニアリング参考資料
https://github.com/Olen/solar-monitor/blob/master/REVERSE-ENGNEER.md

https://github.com/snichol67/solar-bt-monitor
