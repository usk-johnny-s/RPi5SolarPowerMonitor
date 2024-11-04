from IBleDevice import IBleDeviceInternalException,IBleDevice,BleWatchdog
import time
import asyncio
import struct
import datetime
import traceback
from bleak import BleakScanner,BleakClient
from bleak.exc import BleakError
from bleak.backends.characteristic import BleakGATTCharacteristic
from Modbus_Util import *
import msgpack

class BleDevice_LiTime_MPPT(IBleDevice):
    _mqtt_lock = asyncio.Lock()
    _client = None

    def getMqttLock(self) -> asyncio.Lock:
        return self._mqtt_lock

    async def ble_modbus_tx_rx(self, client: BleakClient, characteristic: BleakGATTCharacteristic, tx_addr: int,tx_cmd: int ,tx_data: bytes, rx_len_expect: int, timeout_ns:int) -> bytes:
        self.ble_rx_packet = bytearray()
        tx_packet = modbus_packet_pack(tx_addr, tx_cmd, tx_data)
#        print("ble_tx:",tx_packet.hex())
        await client.write_gatt_char(characteristic, tx_packet, response=False)
        start_ns = time.time_ns()
        while (True):
            if ((time.time_ns()-start_ns) >= timeout_ns):
                return None # Modbus rx timed out.
            await asyncio.sleep(1.0/512)
            if (len(self.ble_rx_packet) == 0):
                continue
            (rx_addr,rx_cmd,raw_data) = modbus_packet_unpack(self.ble_rx_packet)
            if (rx_addr is None):
                continue # Not valid packet
            if (not (tx_addr == rx_addr)):
                continue # Not match addr
            if (not ((tx_cmd & 0x7f) == (rx_cmd & 0x7f))):
                continue # Not match cmd
            break
#        print("ble_rx_time_ns",(time.time_ns()-start_ns))
#        print("ble_rx:",self.ble_rx_packet.hex())
        self.ble_rx_packet = bytearray()
        if ((rx_cmd & 0x80) != 0):
            return None # Got error response
        if (rx_cmd == 0x03):
            rx_data = raw_data[1:]
            if (len(rx_data) != raw_data[0]):
                return None # Not match data length
        else:
            rx_data = raw_data
        if ((len(rx_data) != rx_len_expect) and (rx_len_expect != -1)):
            return None # Not match data length
        return rx_data

    async def doStepBle(self) -> None:
        if self.last_access_time is not None:
            if (time.time_ns() - self.last_access_time) < self.interval_ns:
                return
        if not self._client or not self._client.is_connected:
            async with IBleDevice.getBleScanLock():
                scan_sec = 15.0
                print("Scanning:",self.ble_device_name)
                ble_device = await BleakScanner.find_device_by_name(self.ble_device_name,scan_sec)
                if not ble_device:
                    raise IBleDeviceInternalException("BtleDevice not found.")
                print("Found:",ble_device.name,",address=",ble_device.address)
                try:
                    async with BleWatchdog(15.5*1000000000, "Connect"):
                        self._client = BleakClient(address_or_ble_device=ble_device,timeout=15)
                        await self._client.connect()
                    print("Connected")
                except BaseException:
                    async with BleWatchdog.getLock():
                        msg = BleWatchdog.getLastMsg()
                        print("LastMsg:",msg)
                        BleWatchdog.clear()
                        print("Exception:->Abort Connecting")
                        traceback.print_exc()
                        if self.ble_connect_error():
                            IBleDevice.ble_power_cycle()
                            return
                    return
            await asyncio.sleep(1.0/512)
            try:
                async with BleWatchdog(10.5*1000000000,"SetMTU"):
                    # BlueZ MTU workaround : https://github.com/hbldh/bleak/blob/develop/examples/mtu_size.py
                    if self._client._backend.__class__.__name__ == "BleakClientBlueZDBus":
                        await self._client._backend._acquire_mtu()
                async with BleWatchdog(10.5*1000000000,"StartNotify"):
                    await self._client.start_notify(self.ble_characteristic_rx, self.ble_notification_handler)
            except BaseException:
                async with BleWatchdog.getLock():
                    msg = BleWatchdog.getLastMsg()
                    print("LastMsg:",msg)
                    BleWatchdog.clear()
                print("Exception:is_connected=", self._client.is_connected)
                traceback.print_exc()
                if self.ble_connect_error():
                    IBleDevice.ble_power_cycle()
                    return
                if self._client.is_connected:
                    print("Disconnect:")
                    async with BleWatchdog(15.5*1000000000,"Disconnect"):
                        self._client.disconnect()
                    print("Disconnected:")
                return
            self.ble_connect_success()
            return
        print("Gathering:",self.ble_device_name,",address=",self._client.address)
        timeout_ns = 1.0 * 1000000000
        try:
            # Read 1 : Device Model Revision
            async with BleWatchdog(1.5*1000000000,"Read1:Device Model Revision"):
                rx_data = await self.ble_modbus_tx_rx(self._client, self.ble_characteristic_tx, 0x01, 0x03, bytes.fromhex("000A 000B"), 0x16, timeout_ns)
            if (rx_data is None):
                raise IBleDeviceInternalException("No response at Read 1.")
            (rated_charging_current,rated_discharging_current,system_max_voltage,system_min_voltage,device_model,device_revision_x100) = struct.unpack("!BBBB16sH",rx_data)
            # Read 2 : Current Status
            async with BleWatchdog(1.5*1000000000,"Read2:Current Status"):
                rx_data = await self.ble_modbus_tx_rx(self._client, self.ble_characteristic_tx, 0x01, 0x03, bytes.fromhex("0101 0013"), 0x26, timeout_ns)
            if (rx_data is None):
                raise IBleDeviceInternalException("No response at Read 2.")
            (state_of_charge,battery_voltage_x10,battery_current_x100,battery_power,controller_temperature_celsius,battery_temperature_celsius,load_voltage_x10,load_current_x100,load_power,pv_voltage_x10,max_charge_power,charge_amount,discharge_amount,load_status,charge_status,alarm,total_days,total_charge_amount,total_discharge_amount) = struct.unpack("!HHHHBBHHHHHHHBBHHLL",rx_data)
            timestamp_utc = datetime.datetime.now(datetime.UTC)
            # Gatherd status
            mqtt_data_unpack = {
                "bus": {                                    ## bus info
                    "t":    "ble",                          # bus_type
                    "n":    self.ble_device_name,           # device_name
                    "a":    self._client.address,           # device_address
                },
                "rac": {                                    ## rated current
                    "c":    rated_charging_current,         # rated_charging_current
                    "d":    rated_discharging_current,      # rated_discharging_current
                },
                "syv": {                                    ## system voltage
                    "x":    system_max_voltage,             # system_max_voltage
                    "n":    system_min_voltage,             # system_min_voltage
                },
                "dev": {                                    ## device info
                    "m":    device_model.decode("utf-8"),   # device_model
                    "r":    device_revision_x100,           # device_revision_x100
                },
                "bt": {                                     ## battery
                    "soc":  state_of_charge,                # state_of_charge
                    "v":    battery_voltage_x10,            # battery_voltage_x10
                    "c":    battery_current_x100,           # battery_current_x100
                    "p":    battery_power,                  # battery_power
                },
                "tp": {                                     ## temperature
                    "ct":   controller_temperature_celsius, # controller_temperature_celsius
                    "bt":   battery_temperature_celsius,    # battery_temperature_celsius
                },
                "ld": {                                     ## load
                    "v":    load_voltage_x10,               # load_voltage_x10
                    "c":    load_current_x100,              # load_current_x100
                    "p":    load_power,                     # load_power
                },
                "pv": {                                     ## pv
                    "v":    pv_voltage_x10,                 # pv_voltage_x10
                },
                "st": {                                     ## status
                    "ld":   load_status,                    # load_status
                    "ch":   charge_status,                  # charge_status
                    "al":   alarm,                          # alarm
                },
                "ds": {                                     ## daily summary
                    "mp":   max_charge_power,               # max_charge_power
                    "c":    charge_amount,                  # charge_amount
                    "d":    discharge_amount,               # discharge_amount
                }, 
                "ta": {                                     ## total summary
                    "dy":   total_days,                     # total_days
                    "c":    total_charge_amount,            # total_charge_amount
                    "d":    total_discharge_amount,         # total_discharge_amount
                },
                "utc":      timestamp_utc,                  # Timestamp(UTC)
            }
            print("GatherdStatus:",mqtt_data_unpack)
            async with self.getMqttLock():
                self.mqtt_data_msgpacked = msgpack.packb(mqtt_data_unpack,datetime=True)
                if self.last_access_time is None:
                    self.last_access_time = time.time_ns()
                else:
                    now_ns = time.time_ns()
                    while (now_ns - self.last_access_time) > self.interval_ns:
                        self.last_access_time += self.interval_ns
        except BaseException:
            async with BleWatchdog.getLock():
                msg = BleWatchdog.getLastMsg()
                print("LastMsg:",msg)
                BleWatchdog.clear()
                print("Exception:is_connected=", self._client.is_connected)
                traceback.print_exc()
                if self.ble_communication_error():
                    if self._client.is_connected:
                        print("Disconnect:")
                        async with BleWatchdog(15.5*1000000000,"Disconnect"):
                            self._client.disconnect()
                        print("Disconnected:")
                        return
            return
        self.ble_communication_success()
        print("GateringEnd:")
        return
