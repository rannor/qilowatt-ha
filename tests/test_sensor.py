"""WORKMODE sensors (the Mode sensor's command snapshot is KKP-fork only)."""

from unittest.mock import patch

from qilowatt import WorkModeCommand

from custom_components.qilowatt.const import DATA_CLIENT, DOMAIN
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


def _command(**fields):
    return WorkModeCommand.from_dict({"Mode": "normal", "_source": "optimizer", **fields})


async def test_command_received_before_sensors_subscribe_is_not_lost(hass, config_entry, no_mqtt):
    """At startup the broker sends WORKMODE before the sensor platform is set up."""


    real_forward = hass.config_entries.async_forward_entry_setups

    async def forward_after_command(entry, platforms):
        client = hass.data[DOMAIN][entry.entry_id][DATA_CLIENT]
        # Arrives on the MQTT thread; handled on the loop before platforms load
        await hass.async_add_executor_job(
            client._on_command_received, _command(Mode="sell", PowerLimit=5000)
        )
        await hass.async_block_till_done()
        await real_forward(entry, platforms)

    hass.config_entries.async_forward_entry_setups = forward_after_command
    try:
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    finally:
        hass.config_entries.async_forward_entry_setups = real_forward

    assert hass.states.get("sensor.qw_mode").state == "sell"
    assert hass.states.get("sensor.qw_powerlimit").state == "5000"

    # Later commands still update the sensors
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    await hass.async_add_executor_job(client._on_command_received, _command(Mode="buy"))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.qw_mode").state == "buy"


async def test_startup_command_carries_snapshot(hass, config_entry, no_mqtt):
    """KKP: the command kept from before subscribe also fills the Mode snapshot."""

    real_forward = hass.config_entries.async_forward_entry_setups

    async def forward_after_command(entry, platforms):
        client = hass.data[DOMAIN][entry.entry_id][DATA_CLIENT]
        await hass.async_add_executor_job(
            client._on_command_received,
            _command(Mode="frrup", _source="qilowatt", PowerLimit=900, BatterySoc=40),
        )
        await hass.async_block_till_done()
        await real_forward(entry, platforms)

    hass.config_entries.async_forward_entry_setups = forward_after_command
    try:
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    finally:
        hass.config_entries.async_forward_entry_setups = real_forward

    state = hass.states.get("sensor.qw_mode")
    assert state.state == "frrup"
    assert state.attributes["source"] == "qilowatt"
    assert state.attributes["power_limit"] == 900
    assert state.attributes["battery_soc"] == 40
