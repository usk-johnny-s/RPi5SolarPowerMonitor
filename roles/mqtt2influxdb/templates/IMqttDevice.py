from abc import ABC, abstractmethod
import paho.mqtt.client as mqtt
from influxdb_client.client import write_api

class IMqttDeviceInternalException(Exception):
    pass

class IMqttDevice(ABC):
    @abstractmethod
    def onMqttMessage(self,mqtt_client, obj, msg) -> None:
        raise NotImplementedError()

    def __init__(self, mqtt_topic: str, influx_tag_type: str,influx_write_api: write_api, influx_bucket: str) -> None:
        self.mqtt_topic = mqtt_topic
        self.influx_tag_type = influx_tag_type
        self.influx_write_api = influx_write_api
        self.influx_bucket = influx_bucket

    def onMqttConnect(self, mqtt_client: mqtt.Client) -> None:
        mqtt_client.message_callback_add(self.mqtt_topic, self.onMqttMessage)
        mqtt_client.subscribe(self.mqtt_topic)
