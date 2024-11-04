from abc import ABC, abstractmethod
import asyncio
import subprocess
import time
from typing import Optional
from bleak.backends.characteristic import BleakGATTCharacteristic
import paho.mqtt.client as mqtt

class IBleDeviceInternalException(Exception):
    pass

class BleWatchdog:
    _lock = asyncio.Lock()
    _last_ns = None
    _last_msg = None
    _trigger_ns = 100 * 1000000000
    _trigger_ns_default = 100 * 1000000000

    def __init__(self,trigger_ns: Optional[int]=None,msg: Optional[str]=None) -> None:
        if trigger_ns is None:
            BleWatchdog._trigger_ns = BleWatchdog._trigger_ns_default
        else:
            BleWatchdog._trigger_ns = trigger_ns
        BleWatchdog._last_msg = msg

    async def __aenter__(self):
        async with BleWatchdog._lock:
            BleWatchdog._last_ns = time.time_ns()

    async def __aexit__(self, exc_type, exc, tb):
        async with BleWatchdog._lock:
            BleWatchdog._last_ns = None
            BleWatchdog._last_msg = None
        return False

    @staticmethod
    def setTrigger(trigger_ns :int) -> None:
        BleWatchdog._trigger_ns_default = trigger_ns

    @staticmethod
    def getLock() -> asyncio.Lock:
        return BleWatchdog._lock

    @staticmethod
    def isTrigger() -> bool:
        if (BleWatchdog._last_ns is None):
            return False
        return (time.time_ns() - BleWatchdog._last_ns) > BleWatchdog._trigger_ns

    @staticmethod
    def getLastMsg() -> Optional[str]:
        return BleWatchdog._last_msg

    @staticmethod
    def clear() -> None:
        BleWatchdog._last_ns = None
        BleWatchdog._last_msg = None

class IBleDevice(ABC):
    _ble_scan_lock = asyncio.Lock()
    _ble_watchdog = BleWatchdog()

    @staticmethod
    def getBleScanLock() -> asyncio.Lock:
        return IBleDevice._ble_scan_lock

    @staticmethod
    async def ble_power_cycle():
        print("ble_power_off:")
        res = subprocess.run(["/usr/bin/btmgmt","-i","hci0","power","off"])
        await asyncio.sleep(1.0)
        print("ble_power_on:")
        res = subprocess.run(["/usr/bin/btmgmt","-i","hci0","power","on"])

    @abstractmethod
    def getMqttLock(self) -> asyncio.Lock:
        raise NotImplementedError()

    @abstractmethod
    async def doStepBle(self) -> None:
        raise NotImplementedError()

    def __init__(self, ble_device_name: str, ble_characteristic_rx: str, ble_characteristic_tx: str,interval_ns :int, mqtt_topic: str) -> None:
        self.ble_device_name = ble_device_name
        self.ble_characteristic_rx = ble_characteristic_rx
        self.ble_characteristic_tx = ble_characteristic_tx
        self.interval_ns = interval_ns
        self.mqtt_topic = mqtt_topic
        self.last_access_time = None
        self.last_publish_access_time = None
        self.ble_rx_packet = bytearray()
        self.mqtt_data_msgpacked = None
        self.mqtt_result = None
        self.ble_connect_error_count = 0
        self.ble_connect_error_limit = 16
        self.ble_communication_error_count = 0
        self.ble_communication_error_limit = 8

    def ble_connect_error(self) -> bool:
        self.ble_connect_error_count = min(self.ble_connect_error_count + 1,512)
        ret = self.ble_connect_error_count >= self.ble_connect_error_limit
        if ret:
            self.ble_connect_error_limit = min(self.ble_connect_error_limit << 1,512)
        return ret

    def ble_connect_success(self):
        self.ble_connect_error_count = 0
        self.ble_connect_error_limit = max(self.ble_connect_error_limit >> 1,8)

    def ble_communication_error(self) -> bool:
        self.ble_communication_error_count = min(self.ble_communication_error_count + 1,512)
        ret = self.ble_communication_error_count >= self.ble_communication_error_limit
        if ret:
            self.ble_communication_error_limit = min(self.ble_communication_error_limit << 1,512)

    def ble_communication_success(self):
        self.ble_communication_error_count = 0
        self.ble_communication_error_limit = max(self.ble_communication_error_limit >> 1,4)

    def ble_notification_handler(self, characteristic: BleakGATTCharacteristic, packet: bytearray):
        self.ble_rx_packet.extend(packet)
        return

    async def doStepMqtt(self, mqtt_client: mqtt.Client) -> None:
        async with self.getMqttLock():
            if self.last_access_time is None:
                return
            if self.last_publish_access_time is not None:
                if self.last_access_time == self.last_publish_access_time:
                    return
            # MQTT Publish
            if not mqtt_client.is_connected():
                raise IBleDeviceInternalException("MQTT not connected.")
            print("Publish:",self.ble_device_name)
            self.mqtt_result = mqtt_client.publish(self.mqtt_topic, self.mqtt_data_msgpacked)
            self.last_publish_access_time = self.last_access_time
