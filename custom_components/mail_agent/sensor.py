# Fil: custom_components/mail_agent/sensor.py | Version: 0.18.0 | Datum: 2025-12-18
"""Sensors för Mail Agent med Restore-stöd."""
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import dt as dt_util
from .const import DOMAIN, SIGNAL_MAIL_AGENT_UPDATE

async def async_setup_entry(hass, entry, async_add_entities):
    """Setup sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    scanner = data["scanner"]

    entities = [
        MailAgentLastScanSensor(scanner, entry),
        MailAgentProcessedSensor(scanner, entry),
        MailAgentLastEventSensor(scanner, entry),
    ]
    async_add_entities(entities)


class MailAgentBaseSensor(SensorEntity):
    """Bas för sensors."""
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, scanner, entry):
        self._scanner = scanner
        self._entry = entry
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Hjalmar",
        }

    async def async_added_to_hass(self):
        """Registrera callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_MAIL_AGENT_UPDATE}_{self._entry.entry_id}",
                self._update_callback
            )
        )

    @callback
    def _update_callback(self):
        self.async_write_ha_state()


class MailAgentLastScanSensor(MailAgentBaseSensor, RestoreEntity):
    """Visar när senaste lyckade sökning gjordes."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_name = "Last Scan"

    @property
    def unique_id(self):
        return f"{self._entry.entry_id}_last_scan"

    @property
    def native_value(self):
        return self._scanner.last_scan_success

    async def async_added_to_hass(self):
        """Återställ senaste värde vid omstart."""
        await super().async_added_to_hass() # Viktigt för både BaseSensor och RestoreSensor
        last_state = await self.async_get_last_sensor_data()
        if last_state and last_state.native_value:
            # Försök parsa datumsträngen tillbaka till datetime
            try:
                dt_val = dt_util.parse_datetime(str(last_state.native_value))
                if dt_val:
                    self._scanner.restore_last_scan(dt_val)
            except Exception:
                pass


class MailAgentProcessedSensor(MailAgentBaseSensor, RestoreEntity):
    """Räknare för antal mail."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_name = "Emails Processed"
    _attr_icon = "mdi:email-check-outline"

    @property
    def unique_id(self):
        return f"{self._entry.entry_id}_emails_processed"

    @property
    def native_value(self):
        return self._scanner.emails_processed_count

    async def async_added_to_hass(self):
        """Återställ senaste värde vid omstart."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_sensor_data()
        if last_state and last_state.native_value:
            try:
                val = int(last_state.native_value)
                self._scanner.restore_email_count(val)
            except ValueError:
                pass


class MailAgentLastEventSensor(MailAgentBaseSensor, RestoreEntity):
    """Visar info om senaste händelsen."""

    _attr_name = "Last Event Summary"
    _attr_icon = "mdi:text-box-search-outline"

    @property
    def unique_id(self):
        return f"{self._entry.entry_id}_last_event_summary"

    @property
    def native_value(self):
        return self._scanner.last_event_summary

    async def async_added_to_hass(self):
        """Återställ senaste värde vid omstart."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_sensor_data()
        if last_state and last_state.native_value:
            self._scanner.restore_last_event(str(last_state.native_value))