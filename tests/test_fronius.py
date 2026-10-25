"""Fronius + BYD adapter (fork-only): registry, sign conventions, availability."""

from custom_components.qilowatt.inverter import get_inverter_class
from custom_components.qilowatt.inverter.fronius import FroniusInverter

STATES = {
    "sensor.smart_meter_ts_65a_3_real_power_phase_1": "-1000",
    "sensor.smart_meter_ts_65a_3_real_power_phase_2": "200",
    "sensor.smart_meter_ts_65a_3_real_power_phase_3": "0",
    "sensor.smart_meter_ts_65a_3_voltage_phase_1": "231.5",
    "sensor.smart_meter_ts_65a_3_voltage_phase_2": "230.0",
    "sensor.smart_meter_ts_65a_3_voltage_phase_3": "229.0",
    "sensor.smart_meter_ts_65a_3_frequency_phase_average": "50.01",
    "sensor.kakupesa_4_total_energy": "123456",
    "sensor.fronius_mppt_module_0_dc_power": "1500",
    "sensor.fronius_mppt_module_1_dc_power": "500",
    "sensor.byd_battery_box_premium_hv_state_of_charge": "64.7",
    "sensor.solarnet_power_battery": "800",
    "sensor.qilowatt_load_power_calculated": "900",
    "sensor.kakupesa_4_inverter_state": "Running",
}


def _set(hass, states):
    for entity_id, state in states.items():
        hass.states.async_set(entity_id, state)


async def test_fronius_registered():
    assert get_inverter_class("Fronius") is FroniusInverter


async def test_fronius_readings(hass, config_entry):
    _set(hass, STATES)
    inv = FroniusInverter(hass, config_entry)
    assert inv.is_available()

    energy = inv.get_energy_data()
    # Smart meter sign passed through unchanged (matches what Qilowatt expects).
    assert energy.Power == [-1000.0, 200.0, 0.0]
    assert energy.Voltage[0] == 231.5
    assert energy.Total == 123456.0

    metrics = inv.get_metrics_data()
    assert metrics.PvPower == [1500.0, 500.0]
    assert metrics.BatterySOC == [64]
    assert metrics.BatteryPower == [-800.0]
    assert metrics.LoadPower == [900.0]
    assert metrics.InverterStatus == 2
    assert metrics.GridExportLimit == 2000.0


async def test_fronius_unavailable_when_soc_missing(hass, config_entry):
    _set(hass, STATES)
    hass.states.async_set("sensor.byd_battery_box_premium_hv_state_of_charge", "unavailable")
    assert not FroniusInverter(hass, config_entry).is_available()
