"""WORKMODE sensors: the Mode sensor carries an atomic command snapshot (KKP fork)."""

from unittest.mock import patch

from qilowatt import WorkModeCommand

from custom_components.qilowatt.sensor import WORKMODE_SENSORS, WorkModeSensor


def _sensor(hass, config_entry, key):
    desc = next(d for d in WORKMODE_SENSORS if d.key == key)
    return WorkModeSensor(hass, "QW123", desc, config_entry)


async def test_mode_sensor_carries_command_snapshot(hass, config_entry):
    sensor = _sensor(hass, config_entry, "Mode")
    cmd = WorkModeCommand.from_dict(
        {"Mode": "frrdown", "_source": "qilowatt", "PowerLimit": 1500, "BatterySoc": 80}
    )
    with patch.object(sensor, "async_write_ha_state") as write:
        await sensor._handle_workmode_update(cmd)
    write.assert_called_once()
    assert sensor.native_value == "frrdown"
    assert sensor.extra_state_attributes == {
        "source": "qilowatt",
        "power_limit": 1500,
        "battery_soc": 80,
    }


async def test_missing_fields_are_none(hass, config_entry):
    sensor = _sensor(hass, config_entry, "Mode")
    with patch.object(sensor, "async_write_ha_state"):
        await sensor._handle_workmode_update(WorkModeCommand.from_dict({"Mode": "normal"}))
    assert sensor.extra_state_attributes == {
        "source": None,
        "power_limit": None,
        "battery_soc": None,
    }


async def test_other_sensors_have_no_snapshot(hass, config_entry):
    sensor = _sensor(hass, config_entry, "PowerLimit")
    with patch.object(sensor, "async_write_ha_state"):
        await sensor._handle_workmode_update(
            WorkModeCommand.from_dict({"Mode": "frrup", "_source": "kratt", "PowerLimit": 900})
        )
    assert sensor.native_value == 900
    assert not sensor.extra_state_attributes
