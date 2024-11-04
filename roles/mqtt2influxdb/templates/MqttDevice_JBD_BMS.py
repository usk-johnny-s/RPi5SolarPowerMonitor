from IMqttDevice import IMqttDevice
import msgpack
import urllib3

class MqttDevice_JBD_BMS(IMqttDevice):
    def onMqttMessage(self,mqtt_client, obj, msg) -> None:
        mqtt_data_unpack = msgpack.unpackb(msg.payload,timestamp=3)
        print("on_message_JBD_BMS:",mqtt_data_unpack)
        influx_common = {
            "tags": {
                "category": "Battery",                                      # device_category
                "bus": mqtt_data_unpack["bus"]["t"],                        # bus_type
                "device": mqtt_data_unpack["bus"]["n"],                     # device_name
                "address": mqtt_data_unpack["bus"]["a"],                    # device_address
            },
            "time": mqtt_data_unpack["utc"],                                # Timestamp(UTC)
        }
        influx_measurement_b_or = influx_common | {
            "measurement": "Bor",
            "fields": {
                "equilibrium": mqtt_data_unpack["bm"]["eq"],                # equilibrium
                "equilibrium_high": mqtt_data_unpack["bm"]["eqh"],          # equilibrium_high
                "protection_status": mqtt_data_unpack["bm"]["ps"],          # protection_status
                "fet_control": mqtt_data_unpack["bm"]["fet"],               # fet_control
            },
        }
        influx_measurement_last = influx_common | {
            "measurement": "last",
            "fields": {
                "hardware_version": mqtt_data_unpack["dev"]["hv"],          # hardware_version
                "software_version": mqtt_data_unpack["dev"]["sv"],          # software_version
                "production_date": mqtt_data_unpack["dev"]["pd"],           # production_date
                "num_of_ntc": mqtt_data_unpack["tp"]["n"],                  # num_of_ntc
                "num_of_battery_strings": mqtt_data_unpack["bc"]["n"],      # num_of_battery_strings
                "nominal_capacity_x100": mqtt_data_unpack["bm"]["nc"],      # nominal_capacity_x100
                "cycles": mqtt_data_unpack["bm"]["cyc"],                    # cycles
            },
        }
        influx_measurement_mean_min_max = influx_common | {
            "fields": {
                "total_voltage_x100": mqtt_data_unpack["bm"]["tv"],         # total_voltage_x100
                "current_x100": mqtt_data_unpack["bm"]["c"],                # current_x100
                "remain_capacity_x100": mqtt_data_unpack["bm"]["rc"],       # remain_capacity_x100
                "state_of_charge": mqtt_data_unpack["bm"]["soc"],           # state_of_charge
            },
        }
        for i in range(0,len(mqtt_data_unpack["tp"]["t"])):                 # Array:(Celsius + 2731)
            influx_measurement_mean_min_max["fields"]["ntc#{0:02d}".format(i)] = mqtt_data_unpack["tp"]["t"][i]
        for i in range(0,len(mqtt_data_unpack["bc"]["v"])):                 # Array:(cell_voltage_x1000)
            influx_measurement_mean_min_max["fields"]["cell_voltage#{0:02d}_x1000".format(i)] = mqtt_data_unpack["bc"]["v"][i]

        try:
            self.influx_write_api.write(bucket=self.influx_bucket, record=influx_measurement_b_or)
            self.influx_write_api.write(bucket=self.influx_bucket, record=influx_measurement_last)
            influx_measurement_mean_min_max["measurement"] = "mean"
            self.influx_write_api.write(bucket=self.influx_bucket, record=influx_measurement_mean_min_max)
            influx_measurement_mean_min_max["measurement"] = "min"
            self.influx_write_api.write(bucket=self.influx_bucket, record=influx_measurement_mean_min_max)
            influx_measurement_mean_min_max["measurement"] = "max"
            self.influx_write_api.write(bucket=self.influx_bucket, record=influx_measurement_mean_min_max)
        except urllib3.exceptions.TimeoutError as e:
            print(e)
