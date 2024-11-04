from IMqttDevice import IMqttDevice
import msgpack
import urllib3

class MqttDevice_LiTime_MPPT(IMqttDevice):
    def onMqttMessage(self,mqtt_client, obj, msg) -> None:
        mqtt_data_unpack = msgpack.unpackb(msg.payload,timestamp=3)
        print("on_message_LiTime_MPPT:",mqtt_data_unpack)
        influx_common = {
            "tags": {
                "category": "Charger",                                      # device_category
                "bus": mqtt_data_unpack["bus"]["t"],                        # bus_type
                "device": mqtt_data_unpack["bus"]["n"],                     # device_name
                "address": mqtt_data_unpack["bus"]["a"],                    # device_address
            },
            "time": mqtt_data_unpack["utc"],                                # Timestamp(UTC)
        }
        influx_measurement_Bor = influx_common | {
            "measurement": "Bor",
            "fields": {
                "alarm": mqtt_data_unpack["st"]["al"],                      # alarm
            },
        }
        influx_measurement_last = influx_common | {
            "measurement": "last",
            "fields": {
                "device_model": mqtt_data_unpack["dev"]["m"],               # device_model
                "device_revision_x100": mqtt_data_unpack["dev"]["r"],       # device_revision_x100
                "system_max_voltage": mqtt_data_unpack["syv"]["x"],         # system_max_voltage
                "system_min_voltage": mqtt_data_unpack["syv"]["n"],         # system_min_voltage
                "rated_charging_current": mqtt_data_unpack["rac"]["c"],     # rated_charging_current
                "rated_discharging_current": mqtt_data_unpack["rac"]["d"],  # rated_discharging_current
                "load_status": mqtt_data_unpack["st"]["ld"],                # load_status
                "charge_status": mqtt_data_unpack["st"]["ch"],              # charge_status
                "total_days": mqtt_data_unpack["ta"]["dy"],                 # total_days
                "total_charge_amount": mqtt_data_unpack["ta"]["c"],         # total_charge_amount
                "total_discharge_amount": mqtt_data_unpack["ta"]["d"],      # total_discharge_amount
            },
        }
        influx_measurement_mean_min_max = influx_common | {
            "fields": {
                "state_of_charge": mqtt_data_unpack["bt"]["soc"],           # state_of_charge
                "battery_voltage_x10": mqtt_data_unpack["bt"]["v"],         # battery_voltage_x10
                "battery_current_x100": mqtt_data_unpack["bt"]["c"],        # battery_current_x100
                "battery_power": mqtt_data_unpack["bt"]["p"],               # battery_power
                "controller_temperature_celsius": mqtt_data_unpack["tp"]["ct"], # controller_temperature_celsius
                "battery_temperature_celsius": mqtt_data_unpack["tp"]["bt"], # battery_temperature_celsius
                "load_voltage_x10": mqtt_data_unpack["ld"]["v"],            # load_voltage_x10
                "load_current_x100": mqtt_data_unpack["ld"]["c"],           # load_current_x100
                "load_power": mqtt_data_unpack["ld"]["p"],                  # load_power
                "pv_voltage_x10": mqtt_data_unpack["pv"]["v"],              # pv_voltage_x10
                "max_charge_power": mqtt_data_unpack["ds"]["mp"],           # max_charge_power
                "charge_amount": mqtt_data_unpack["ds"]["c"],               # charge_amount
                "discharge_amount": mqtt_data_unpack["ds"]["d"],            # discharge_amount
            },
        }

        try:
            self.influx_write_api.write(bucket=self.influx_bucket, record=influx_measurement_Bor)
            self.influx_write_api.write(bucket=self.influx_bucket, record=influx_measurement_last)
            influx_measurement_mean_min_max["measurement"] = "mean"
            self.influx_write_api.write(bucket=self.influx_bucket, record=influx_measurement_mean_min_max)
            influx_measurement_mean_min_max["measurement"] = "min"
            self.influx_write_api.write(bucket=self.influx_bucket, record=influx_measurement_mean_min_max)
            influx_measurement_mean_min_max["measurement"] = "max"
            self.influx_write_api.write(bucket=self.influx_bucket, record=influx_measurement_mean_min_max)
        except urllib3.exceptions.TimeoutError as e:
            print(e)

