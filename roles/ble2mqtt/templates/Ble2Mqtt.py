import asyncio
import subprocess
import time
import signal
import functools
from bleak.exc import BleakError
from BleDevice_LiTime_MPPT import BleDevice_LiTime_MPPT
from BleDevice_JBD_BMS import BleDevice_JBD_BMS
import paho.mqtt.client as mqtt
from IBleDevice import IBleDevice,BleWatchdog,IBleDeviceInternalException

task_run = True
ble_devices = []

async def main_mqtt():
    global task_run,ble_devices
    broker = 'localhost'
    port = 1883
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_reconnect_blind_period = 5 * 1000000000
    mqtt_connect_start_time = time.time_ns()
    mqtt_client.connect_async(broker, port)
    mqtt_client.loop_start()
    try:
        while task_run:
            if not mqtt_client.is_connected():
                if time.time_ns() - mqtt_connect_start_time > mqtt_reconnect_blind_period:
                    mqtt_connect_start_time = time.time_ns()
                    mqtt_client.connect_async(broker, port)
            for device in ble_devices:
                if not task_run:
                    break
                try:
                    await device.doStepMqtt(mqtt_client)
                except IBleDeviceInternalException as e:
#                    print(e)
                    pass
            await asyncio.sleep(1.0/128)
    except asyncio.CancelledError:
        return "Mqtt Task Cancelled."

async def main_ble():
    global task_run,ble_devices
    try:
        while task_run:
            for device in ble_devices:
                if not task_run:
                    break
                try:
                    await device.doStepBle()
                except BleakError as e:
                    print(e)
                except IBleDeviceInternalException as e:
                    print(e)
            await asyncio.sleep(1.0/128)
    except asyncio.CancelledError:
        return "Ble Task Cancelled."

async def main_watchdog_ble():
    global task_run
    try:
        BleWatchdog.setTrigger(1.5 * 1000000000)
        while task_run:
            async with BleWatchdog.getLock():
                if (BleWatchdog.isTrigger()):
                    msg = BleWatchdog.getLastMsg()
                    print("LastMsg:",msg)
                    IBleDevice.ble_power_cycle()
                    BleWatchdog.clear()
            await asyncio.sleep(1.0/128)
    except asyncio.CancelledError:
        return "Watchdog Ble Task Cancelled."

async def handler_task_cancel(signo, loop):
    global task_run
    print('caught {0}'.format(signo.name))
    task_run = False
    msg = BleWatchdog.getLastMsg()
    print("LastMsg:",msg)
    for task in asyncio.tasks.all_tasks(loop):
        print("task:", task)
        if task is asyncio.tasks.current_task(loop):
            print("->current")
            continue
        print("->cancel")
        task.cancel()

# 8 9 10 12 15 16 18 20 24 25 27 30 32 36 40 45 47 48 50 54
interval_ns = 27 * 1000000000
ble_devices.append(BleDevice_JBD_BMS("{{ble_batttery_1}}", "0000ff01-0000-1000-8000-00805f9b34fb", "0000ff02-0000-1000-8000-00805f9b34fb",interval_ns,"{{mqtt_batttery_1}}"))
ble_devices.append(BleDevice_JBD_BMS("{{ble_batttery_2}}", "0000ff01-0000-1000-8000-00805f9b34fb", "0000ff02-0000-1000-8000-00805f9b34fb",interval_ns,"{{mqtt_batttery_2}}"))
ble_devices.append(BleDevice_LiTime_MPPT("{{ble_controller_1}}", "0000ffe1-0000-1000-8000-00805f9b34fb", "0000ffe1-0000-1000-8000-00805f9b34fb",interval_ns,"{{mqtt_controller_1}}"))

loop = asyncio.get_event_loop()

for signo in [signal.SIGINT, signal.SIGTERM]:
    func = functools.partial(asyncio.ensure_future, handler_task_cancel(signo, loop))
    loop.add_signal_handler(signo, func)

gather = asyncio.gather( main_mqtt(), main_ble(), main_watchdog_ble() )
loop.run_until_complete(gather)
