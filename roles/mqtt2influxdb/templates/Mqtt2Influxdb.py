import asyncio
import time
import signal
import functools
from MqttDevice_LiTime_MPPT import MqttDevice_LiTime_MPPT
from MqttDevice_JBD_BMS import MqttDevice_JBD_BMS
import paho.mqtt.client as mqtt
import msgpack

import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS
import os

task_run = True
mqtt_devices = []

def on_connect(mqtt_client, obj, flags, rc, prop):
    global mqtt_devices
    print("rc: " + str(rc))
    print("mqtt_client.subscribe")
    for device in mqtt_devices:
        device.onMqttConnect(mqtt_client)

async def main():
    global task_run,mqtt_devices

    influx_url="http://localhost:8086"
    influx_bucket = "day"
    influx_org = "local"
    # INFLUX_TOKEN is an environment variable you created for your database WRITE token
    influx_token = os.getenv('INFLUX_TOKEN')
    influx_client = influxdb_client.InfluxDBClient(url=influx_url, token=influx_token, org=influx_org)
    # Write script
    influx_write_api = influx_client.write_api(write_options=SYNCHRONOUS)

    mqtt_devices.append(MqttDevice_JBD_BMS("{{mqtt_batttery_1}}", "BMS", influx_write_api, influx_bucket))
    mqtt_devices.append(MqttDevice_JBD_BMS("{{mqtt_batttery_2}}", "BMS", influx_write_api, influx_bucket))
    mqtt_devices.append(MqttDevice_LiTime_MPPT("{{mqtt_controller_1}}", "Charger", influx_write_api, influx_bucket))

    broker = 'localhost'
    port = 1883
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_reconnect_blind_period = 5 * 1000000000
    mqtt_connect_start_time = time.time_ns()
    mqtt_client.on_connect = on_connect
    print("mqtt_client.connect_async")
    mqtt_client.connect_async(broker, port)
    mqtt_client.loop_start()
    try:
        while task_run:
            if not mqtt_client.is_connected():
                if time.time_ns() - mqtt_connect_start_time > mqtt_reconnect_blind_period:
                    mqtt_connect_start_time = time.time_ns()
                    print("mqtt_client.connect_async")
                    mqtt_client.connect_async(broker, port)
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        return "Task Cancelled."

async def handler_task_cancel(signo, loop):
    global task_run
    print('caught {0}'.format(signo.name))
    for task in asyncio.tasks.all_tasks(loop):
        print("task:", task)
        if task is asyncio.tasks.current_task(loop):
            print("->current")
            continue
        print("->cancel")
        task.cancel()
    task_run = False
    asyncio.tasks.current_task(loop).cancel()

loop = asyncio.get_event_loop()

for signo in [signal.SIGINT, signal.SIGTERM]:
    func = functools.partial(asyncio.ensure_future, handler_task_cancel(signo, loop))
    loop.add_signal_handler(signo, func)

loop.run_until_complete(main())