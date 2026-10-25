# custom_components/qilowatt/inverter/fronius.py
"""Fronius + BYD inverter adapter for Qilowatt integration (KKP HA).

Entity sources (all validated against SolarWeb/Fronius realtime data):

Grid (EnergyData):
  Power per phase:   sensor.smart_meter_ts_65a_3_real_power_phase_[1/2/3]
                     Sign: negative = exporting that phase, positive = importing
                     Passed to Qilowatt unchanged (verified correct in Qilowatt)
  Voltage per phase: sensor.smart_meter_ts_65a_3_voltage_phase_[1/2/3]
  Current per phase: sensor.smart_meter_ts_65a_3_current_phase_[1/2/3]
  Frequency:         sensor.smart_meter_ts_65a_3_frequency_phase_average
  Total energy (Wh): sensor.kakupesa_4_total_energy

PV (MetricsData):
  Power:   sensor.fronius_mppt_module_[0/1]_dc_power  (two real strings; sum = SolarWeb PV)
  Voltage: sensor.fronius_mppt_module_[0/1]_dc_voltage
  Current: sensor.fronius_mppt_module_[0/1]_dc_current
  (mppt2 = unused, mppt3 = battery DC channel — not PV)

Battery (MetricsData):
  SOC:         sensor.byd_battery_box_premium_hv_state_of_charge (%)
  Power:       sensor.solarnet_power_battery  (positive = discharging ✓)
  Current:     sensor.fronius_mppt_module_3_dc_current  (positive = discharging ✓)
  Voltage:     sensor.fronius_mppt_module_3_dc_voltage  (= BYD DC bus)
  Temperature: sensor.byd_battery_box_premium_hv_temperature

Load (MetricsData):
  sensor.qilowatt_load_power_calculated  (always positive ✓)

Inverter:
  Status: sensor.kakupesa_4_inverter_state  ("Running" = status 2)
  Temperature: not available → 0.0
"""

import logging

from homeassistant.core import HomeAssistant
from qilowatt import EnergyData, MetricsData

from .base_inverter import BaseInverter

_LOGGER = logging.getLogger(__name__)


class FroniusInverter(BaseInverter):
    """Inverter adapter for Fronius Primo GEN24 + BYD Box via HA fronius/sunspec integrations."""

    # Report the inverter unavailable (publish nothing) instead of sending
    # zeros while grid voltage or battery SOC is missing — see BaseInverter.
    AVAILABILITY_ENTITIES = (
        "sensor.smart_meter_ts_65a_3_voltage_phase_1",
        "sensor.byd_battery_box_premium_hv_state_of_charge",
    )

    def __init__(self, hass: HomeAssistant, config_entry, device_id=None):
        super().__init__(hass, config_entry, device_id)

    def find_entity_state(self, entity_id: str):
        """Entities are referenced by full entity_id; used by is_available()."""
        return self.hass.states.get(entity_id)

    def _get_float(self, entity_id: str, default: float = 0.0) -> float:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable", "", None):
            return default
        try:
            return float(state.state)
        except (ValueError, TypeError):
            _LOGGER.warning("Could not convert %s ('%s') to float", entity_id, state.state)
            return default

    def _get_int(self, entity_id: str, default: int = 0) -> int:
        return int(self._get_float(entity_id, default))

    def get_energy_data(self) -> EnergyData:
        """Grid-side energy data from the Smart Meter TS 65A-3.

        Smart meter sign convention: negative = exporting, positive = importing.
        Sent to Qilowatt as-is; export/import shows correctly there.
        """
        power = [
            self._get_float("sensor.smart_meter_ts_65a_3_real_power_phase_1"),
            self._get_float("sensor.smart_meter_ts_65a_3_real_power_phase_2"),
            self._get_float("sensor.smart_meter_ts_65a_3_real_power_phase_3"),
        ]
        voltage = [
            self._get_float("sensor.smart_meter_ts_65a_3_voltage_phase_1"),
            self._get_float("sensor.smart_meter_ts_65a_3_voltage_phase_2"),
            self._get_float("sensor.smart_meter_ts_65a_3_voltage_phase_3"),
        ]
        current = [
            self._get_float("sensor.smart_meter_ts_65a_3_current_phase_1"),
            self._get_float("sensor.smart_meter_ts_65a_3_current_phase_2"),
            self._get_float("sensor.smart_meter_ts_65a_3_current_phase_3"),
        ]
        frequency = self._get_float("sensor.smart_meter_ts_65a_3_frequency_phase_average", default=50.0)
        total_wh = self._get_float("sensor.kakupesa_4_total_energy")

        return EnergyData(
            Power=power,
            Voltage=voltage,
            Current=current,
            Frequency=frequency,
            Today=0.0,
            Total=total_wh,
        )

    def get_metrics_data(self) -> MetricsData:
        """PV, battery and load metrics."""

        # --- PV: two real strings (mppt0 = PV1, mppt1 = PV2) ---
        pv_power = [
            self._get_float("sensor.fronius_mppt_module_0_dc_power"),
            self._get_float("sensor.fronius_mppt_module_1_dc_power"),
        ]
        pv_voltage = [
            self._get_float("sensor.fronius_mppt_module_0_dc_voltage"),
            self._get_float("sensor.fronius_mppt_module_1_dc_voltage"),
        ]
        pv_current = [
            self._get_float("sensor.fronius_mppt_module_0_dc_current"),
            self._get_float("sensor.fronius_mppt_module_1_dc_current"),
        ]

        # --- Battery: mppt3 = BYD DC channel ---
        # solarnet_power_battery: positive = discharging ✓
        # mppt3_current: positive = discharging ✓
        # mppt3_voltage: BYD DC bus voltage ✓
        battery_soc = self._get_int("sensor.byd_battery_box_premium_hv_state_of_charge")
        battery_power = [-self._get_float("sensor.solarnet_power_battery")]
        battery_current = [-self._get_float("sensor.fronius_mppt_module_3_dc_current")]
        battery_voltage = [self._get_float("sensor.fronius_mppt_module_3_dc_voltage")]
        battery_temperature = [self._get_float("sensor.byd_battery_box_premium_hv_temperature")]

        # --- Load ---
        load_power = [self._get_float("sensor.qilowatt_load_power_calculated")]
        load_current = [0.0, 0.0, 0.0]

        # --- Inverter ---
        inv_state = self.hass.states.get("sensor.kakupesa_4_inverter_state")
        inverter_status = 2 if (inv_state and inv_state.state == "Running") else 0

        # Grid export limit: current PV production as proxy
        grid_export_limit = sum(pv_power)

        return MetricsData(
            PvPower=pv_power,
            PvVoltage=pv_voltage,
            PvCurrent=pv_current,
            BatterySOC=[battery_soc],
            BatteryPower=battery_power,
            BatteryCurrent=battery_current,
            BatteryVoltage=battery_voltage,
            BatteryTemperature=battery_temperature,
            LoadPower=load_power,
            LoadCurrent=load_current,
            AlarmCodes=[0, 0, 0, 0, 0, 0],
            InverterStatus=inverter_status,
            InverterTemperature=0.0,
            GridExportLimit=grid_export_limit,
        )
