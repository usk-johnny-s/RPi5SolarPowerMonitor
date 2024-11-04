from IBleDevice import IBleDeviceInternalException,IBleDevice,BleWatchdog
import time
import asyncio
import struct
import datetime
import traceback
from typing import Optional
from bleak import BleakScanner,BleakClient
from bleak.exc import BleakError
from bleak.backends.characteristic import BleakGATTCharacteristic
from JbdBms_Util import *
import msgpack

class BleDevice_JBD_BMS(IBleDevice):
    _mqtt_lock = asyncio.Lock()
    _client = None

    def getMqttLock(self) -> asyncio.Lock:
        return self._mqtt_lock

    async def ble_jbd_tx_rx(self, client: BleakClient, characteristic: BleakGATTCharacteristic, tx_start: int,tx_cmd: int ,tx_data: bytes,tx_stop: Optional[int], rx_len_expect: int, timeout_ns:int) -> bytes:
        self.ble_rx_packet = bytearray()
        tx_packet = jbd_packet_pack(tx_start, tx_cmd, tx_data, tx_stop)
#        print("ble_tx:",tx_packet.hex())
        await client.write_gatt_char(characteristic, tx_packet, response=False)
        start_ns = time.time_ns()
        while (True):
            if ((time.time_ns()-start_ns) >= timeout_ns):
                return None # JBD rx timed out.
            await asyncio.sleep(1.0/512)
            if (len(self.ble_rx_packet) == 0):
                continue
            (rx_start,rx_cmd,raw_data,rx_stop) = jdb_packet_unpack(self.ble_rx_packet)
            if (rx_start is None):
                continue # Not valid packet
            if (not (((tx_start == 0XFFAA) and (rx_start == 0xFFAA)) or ((tx_start == 0xDDA5 or tx_start == 0xDD5A) and rx_start == 0xDD))):
                continue # Not match start and addr
            if (not (rx_cmd == tx_cmd)):
                continue # Not match cmd
            break
#        print("ble_rx_time_ns",(time.time_ns()-start_ns))
#        print("ble_rx:",self.ble_rx_packet.hex())
        self.ble_rx_packet = bytearray()
        if (rx_start == 0xFFAA):
            rx_data = raw_data
            rx_len = len(rx_data)
            if ((rx_len != rx_len_expect) and (rx_len_expect != -1)):
                return None # Not match data length
        if (rx_start == 0xDD):
            rx_stat = raw_data[0]
            if (rx_stat != 0):
                return None # Got error response
            rx_len = raw_data[1]
            rx_data = raw_data[2:]
            if (rx_len != len(rx_data)):
                return None # Not match data length
            if ((rx_len != rx_len_expect) and (rx_len_expect != -1)):
                return None # Not match data length
        return rx_data

    def jbd_ble_obfuscate_pwd(self, rand: int, pwd: bytes, mac: bytes) -> bytes:
        obfuscated = bytes()
        for ix in range(len(pwd)):
            d1 = pwd[ix]
            if (ix < len(mac)):
                d2 = mac[ix]
            else:
                d2 = 0x00
            obfuscated += (((d1 ^ d2) + rand ) & 0xff).to_bytes(1)
        return obfuscated

    async def doStepBle(self) -> None:
        timeout_ns = 1.0 * 1000000000
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
                    async with BleWatchdog(15.5*1000000000,"Connect"):
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
            ble_mac = bytes.fromhex(self._client.address.replace(':', ' '))
            await asyncio.sleep(1.0/512)
            try:
                async with BleWatchdog(10.5*1000000000,"SetMTU"):
                    # BlueZ MTU workaround : https://github.com/hbldh/bleak/blob/develop/examples/mtu_size.py
                    if self._client._backend.__class__.__name__ == "BleakClientBlueZDBus":
                        await self._client._backend._acquire_mtu()
                async with BleWatchdog(10.5*1000000000,"StartNotify"):
                    await self._client.start_notify(self.ble_characteristic_rx, self.ble_notification_handler)
                # Phase 1 : Send Pwd0
                async with BleWatchdog(1.5*1000000000,"Phase1:Send Pwd0"):
                    rx_data = await self.ble_jbd_tx_rx(self._client, self.ble_characteristic_tx, 0xFFAA, 0x15, bytes(b"{{ble_batttery_pwd}}"), None, 0x01, timeout_ns)
                if (rx_data is None):
                    # Retry
                    async with BleWatchdog(1.5*1000000000,"Phase1r:Send Pwd0"):
                        rx_data = await self.ble_jbd_tx_rx(self._client, self.ble_characteristic_tx, 0xFFAA, 0x15, bytes(b"{{ble_batttery_pwd}}"), None, 0x01, timeout_ns)
                    if (rx_data is None):
                        raise IBleDeviceInternalException("No response at Phase 1.")
                if (int.from_bytes(rx_data) != 0x00):
                    raise IBleDeviceInternalException("Failed at Phase 1.")
                # Phase 2-1 : Get rand
                async with BleWatchdog(1.5*1000000000,"Phase2-1:Get rand"):
                    rx_data = await self.ble_jbd_tx_rx(self._client, self.ble_characteristic_tx, 0xFFAA, 0x17, bytes(), None, 0x01, timeout_ns)
                if (rx_data is None):
                    raise IBleDeviceInternalException("No response at Phase 2-1.")
                # Phase 2-2 : Send Pwd1
                rand = int.from_bytes(rx_data)
                pwd = b"000000"
                obfuscate_pwd = self.jbd_ble_obfuscate_pwd(rand, pwd, ble_mac)
                async with BleWatchdog(1.5*1000000000,"Phase2-2:Send Pwd1"):
                    rx_data = await self.ble_jbd_tx_rx(self._client, self.ble_characteristic_tx, 0xFFAA, 0x18, obfuscate_pwd, None, 0x01, timeout_ns)
                if (rx_data is None):
                    raise IBleDeviceInternalException("No response at Phase 2-2.")
                if (int.from_bytes(rx_data) != 0x00):
                    raise IBleDeviceInternalException("Failed at Phase 2-2.")
                # Phase 3-1 : Get rand
                async with BleWatchdog(1.5*1000000000,"Phase3-1:Ger rand"):
                    rx_data = await self.ble_jbd_tx_rx(self._client, self.ble_characteristic_tx, 0xFFAA, 0x17, bytes(), None, 0x01, timeout_ns)
                if (rx_data is None):
                    raise IBleDeviceInternalException("No response at Phase 3-1.")
                # Phase 3-2 : Send Pwd2
                rand = int.from_bytes(rx_data)
                pwd = b"JBDbtpwd!@#2023"
                obfuscate_pwd = self.jbd_ble_obfuscate_pwd(rand, pwd, ble_mac)
                async with BleWatchdog(1.5*1000000000,"Phase3-2:Send Pwd2"):
                    rx_data = await self.ble_jbd_tx_rx(self._client, self.ble_characteristic_tx, 0xFFAA, 0x1D, obfuscate_pwd, None, 0x01, timeout_ns)
                if (rx_data is None):
                    raise IBleDeviceInternalException("No response at Phase 3-2.")
                if (int.from_bytes(rx_data) != 0x00):
                    raise IBleDeviceInternalException("Failed at Phase 3-2.")
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
            return
        print("Gathering:",self.ble_device_name,",address=",self._client.address)
        ble_mac = bytes.fromhex(self._client.address.replace(':', ' '))
        try:
            # Read 1 : Hardware Version
            async with BleWatchdog(1.5*1000000000,"Read1:HardwareVersion"):
                rx_data = await self.ble_jbd_tx_rx(self._client, self.ble_characteristic_tx, 0xDDA5, 0x05, bytes(), 0x77, -1, timeout_ns)
            if (rx_data is None):
                raise IBleDeviceInternalException("No response at Read 1.")
            rx_len = len(rx_data)
            if (rx_len <= 0):
                raise IBleDeviceInternalException("Not enough response length at Read 1.")
            hardware_version = rx_data.decode("utf-8")
            # Read 2 :Basic Status
            async with BleWatchdog(1.5*1000000000,"Read2:BasicStatus"):
                rx_data = await self.ble_jbd_tx_rx(self._client, self.ble_characteristic_tx, 0xDDA5, 0x03, bytes(), 0x77, -1, timeout_ns)
            if (rx_data is None):
                raise IBleDeviceInternalException("No response at Read 2.")
            rx_len = len(rx_data)
            if (rx_len < 23):
                raise IBleDeviceInternalException("Not enough response length at Read 2.")
            else:
                (total_voltage_x100,current_x100,remain_capacity_x100,nominal_capacity_x100,cycles,production_date,equilibrium,equilibrium_high,protection_status,software_version,state_of_charge,fet_control,num_of_battery_strings,num_of_ntc) = struct.unpack("!HhHHHHHHHBBBBB",rx_data[:23])
                rx_len_expect = num_of_ntc*2 + 23
                if (rx_len != rx_len_expect):
                    raise IBleDeviceInternalException("Not match response length at Read 2.")
                else:
                    ntc = []
                    for i in range(0,num_of_ntc):
                        ntc.append(struct.unpack("!H",rx_data[i*2+23:i*2+25])[0])
            # Read 3 : Cell Voltage
            async with BleWatchdog(1.5*1000000000,"Read3:CellVoltage"):
                rx_data = await self.ble_jbd_tx_rx(self._client, self.ble_characteristic_tx, 0xDDA5, 0x04, bytes(), 0x77, -1, timeout_ns)
            if (rx_data is None):
                raise IBleDeviceInternalException("No response at Read 3.")
            rx_len = len(rx_data)
            rx_len_expect = num_of_battery_strings*2
            if (rx_len != rx_len_expect):
                raise IBleDeviceInternalException("Not match response length at Read 3.")
            else:
                cell_voltage_x1000 = []
                for i in range(0,num_of_battery_strings):
                    cell_voltage_x1000.append(struct.unpack("!H",rx_data[i*2+0:i*2+2])[0])
            timestamp_utc = datetime.datetime.now(datetime.UTC)
            # Gatherd status
            mqtt_data_unpack = {
                "bus": {                                    ## bus info
                    "t":    "ble",                          # bus_type
                    "n":    self.ble_device_name,           # device_name
                    "a":    self._client.address,           # device_address
                },
                "dev": {                                    ## device info
                    "hv":   hardware_version,               # hardware_version
                    "sv":   software_version,               # software_version
                    "pd":   production_date,                # production_date
                },
                "bm": {                                     ## battery management
                    "tv":   total_voltage_x100,             # total_voltage_x100
                    "c":    current_x100,                   # current_x100
                    "nc":   nominal_capacity_x100,          # nominal_capacity_x100
                    "rc":   remain_capacity_x100,           # remain_capacity_x100
                    "soc":  state_of_charge,                # state_of_charge
                    "cyc":  cycles,                         # cycles
                    "eq":   equilibrium,                    # equilibrium
                    "eqh":  equilibrium_high,               # equilibrium_high
                    "ps":   protection_status,              # protection_status
                    "fet":  fet_control,                    # fet_control
                },
                "tp": {                                     ## temperature
                    "n":    num_of_ntc,                     # num_of_ntc
                    "t":    ntc,                            # Array:(Celsius + 2731)
                },
                "bc": {                                     ## battery cell
                    "n":    num_of_battery_strings,         # num_of_battery_strings
                    "v":    cell_voltage_x1000,             # Array:(cell_voltage_x1000)
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
        print("GateringEnd:")
        return
