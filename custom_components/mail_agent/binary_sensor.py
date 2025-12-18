# Fil: custom_components/mail_agent/binary_sensor.py | Version: 0.18.0 | Datum: 2025-12-18
"""Binary sensors för Mail Agent."""
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN, SIGNAL_MAIL_AGENT_UPDATE

async def async_setup_entry(hass, entry, async_add_entities):
    """Setup binary sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    scanner = data["scanner"]

    entities = [
        MailAgentScanningSensor(scanner, entry),
        MailAgentConnectedSensor(scanner, entry),
    ]
    async_add_entities(entities)


class MailAgentBaseBinarySensor(BinarySensorEntity):
    """Bas för binary sensors."""
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


class MailAgentScanningSensor(MailAgentBaseBinarySensor):
    """Sensor som visar om scanning pågår."""

    _attr_unique_id = "mail_agent_scanning" # Prefixas med entry_id av HA om unikt ID sätts korrekt i config, men här manuellt suffix
    _attr_name = "Scanning"
    _attr_icon = "mdi:radar"

    @property
    def unique_id(self):
        return f"{self._entry.entry_id}_scanning"

    @property
    def is_on(self):
        return self._scanner.is_scanning


class MailAgentConnectedSensor(MailAgentBaseBinarySensor):
    """Sensor som visar anslutningsstatus."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_name = "Connected"

    @property
    def unique_id(self):
        return f"{self._entry.entry_id}_connected"

    @property
    def is_on(self):
        return self._scanner.is_connected