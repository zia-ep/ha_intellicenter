"""Pentair IntelliCenter Integration."""

import asyncio
import logging
from typing import Any, Optional

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.water_heater import DOMAIN as WATER_HEATER_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, EVENT_HOMEASSISTANT_STOP, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, dispatcher
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType


from .const import (
    CONF_FORCE_RECONNECT_INTERVAL,
    CONF_RECONNECT_INTERVAL,
    DEFAULT_FORCE_RECONNECT_INTERVAL,
    DEFAULT_RECONNECT_INTERVAL,
    DOMAIN,
)
from .pyintellicenter import (
    ACT_ATTR,
    BODY_ATTR,
    BODY_TYPE,
    CHEM_TYPE,
    CIRCGRP_TYPE,
    CIRCUIT_ATTR,
    CIRCUIT_TYPE,
    FEATR_ATTR,
    GPM_ATTR,
    HEATER_ATTR,
    HEATER_TYPE,
    HTMODE_ATTR,
    LISTORD_ATTR,
    LOTMP_ATTR,
    LSTTMP_ATTR,
    MODE_ATTR,
    PUMP_TYPE,
    PWR_ATTR,
    RPM_ATTR,
    SCHED_TYPE,
    SENSE_TYPE,
    SNAME_ATTR,
    SOURCE_ATTR,
    STATUS_ATTR,
    SUBTYP_ATTR,
    SYSTEM_TYPE,
    USE_ATTR,
    VACFLO_ATTR,
    VOL_ATTR,
    ConnectionHandler,
    ModelController,
    PoolModel,
    PoolObject,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

# here is the list of platforms we support
PLATFORMS = [
    LIGHT_DOMAIN,
    SENSOR_DOMAIN,
    SWITCH_DOMAIN,
    BINARY_SENSOR_DOMAIN,
    WATER_HEATER_DOMAIN,
    NUMBER_DOMAIN,
]

# -------------------------------------------------------------------------------------


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Pentair IntelliCenter Integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IntelliCenter integration from a config entry."""

    attributes_map = {
        BODY_TYPE: {
            SNAME_ATTR,
            HEATER_ATTR,
            HTMODE_ATTR,
            LOTMP_ATTR,
            LSTTMP_ATTR,
            STATUS_ATTR,
            VOL_ATTR,
        },
        CIRCUIT_TYPE: {SNAME_ATTR, STATUS_ATTR, USE_ATTR, SUBTYP_ATTR, FEATR_ATTR},
        CIRCGRP_TYPE: {CIRCUIT_ATTR},
        CHEM_TYPE: {},
        HEATER_TYPE: {SNAME_ATTR, BODY_ATTR, LISTORD_ATTR},
        PUMP_TYPE: {SNAME_ATTR, STATUS_ATTR, PWR_ATTR, RPM_ATTR, GPM_ATTR},
        SENSE_TYPE: {SNAME_ATTR, SOURCE_ATTR},
        SCHED_TYPE: {SNAME_ATTR, ACT_ATTR, VACFLO_ATTR},
        SYSTEM_TYPE: {MODE_ATTR, VACFLO_ATTR},
    }
    model = PoolModel(attributes_map)

    controller = ModelController(entry.data[CONF_HOST], model, loop=hass.loop)

    class Handler(ConnectionHandler):
        def __init__(
            self,
            controller,
            entry: ConfigEntry,
            hass: HomeAssistant,
            timeBetweenReconnects=entry.options.get(
                CONF_RECONNECT_INTERVAL,
                entry.data.get(CONF_RECONNECT_INTERVAL, DEFAULT_RECONNECT_INTERVAL),
            ),
            force_reconnect_interval=entry.options.get(
                CONF_FORCE_RECONNECT_INTERVAL,
                entry.data.get(
                    CONF_FORCE_RECONNECT_INTERVAL, DEFAULT_FORCE_RECONNECT_INTERVAL
                ),
            ),
        ):
            """Initialize the handler."""
            super().__init__(controller, timeBetweenReconnects)
            self.controller = controller
            self._entry = entry
            self._hass = hass
            self.UPDATE_SIGNAL = DOMAIN + "_UPDATE_" + entry.entry_id
            self.CONNECTION_SIGNAL = DOMAIN + "_CONNECTION_" + entry.entry_id
            _LOGGER.info(
                "Initializing ConnectionHandler with improved connection management v1.0"
            )
            self._force_reconnect_interval = force_reconnect_interval
            self._last_successful_connection = None
            self._periodic_reconnect_task = None

        def started(self, controller):
            """Handle the first time the controller is started."""
            _LOGGER.info(f"connected to system: '{controller.systemInfo.propName}'")

            for object in controller.model:
                _LOGGER.debug(f"   loaded {object}")

            async def setup_platforms():
                """Set up platforms."""
                await self._hass.config_entries.async_forward_entry_setups(
                    self._entry, PLATFORMS
                )

            self._hass.async_create_task(setup_platforms())

        @callback
        def reconnected(self, controller):
            """Handle reconnection from the Pentair system."""
            _LOGGER.info(f"reconnected to system: '{controller.systemInfo.propName}'")
            dispatcher.async_dispatcher_send(self._hass, self.CONNECTION_SIGNAL, True)

        @callback
        def disconnected(self, controller, exc):
            """Handle updates from the Pentair system."""
            _LOGGER.info(
                f"disconnected from system: '{controller.systemInfo.propName}'"
            )
            dispatcher.async_dispatcher_send(self._hass, self.CONNECTION_SIGNAL, False)

        @callback
        def updated(self, controller, updates: dict[str, PoolObject]):
            """Handle updates from the Pentair system."""
            _LOGGER.debug(f"received update for {len(updates)} pool objects")
            dispatcher.async_dispatcher_send(self._hass, self.UPDATE_SIGNAL, updates)

    try:
        handler = Handler(
            controller,
            entry=entry,
            hass=hass,
            timeBetweenReconnects=30,  # reconnect interval 30 seconds
            force_reconnect_interval=3600,  # force reconnect every hour
        )

        await handler.start()

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = handler

        async def on_hass_stop(event):
            """Stop push updates when hass stops."""
            handler.stop()

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, on_hass_stop)

        return True
    except ConnectionRefusedError as err:
        raise ConfigEntryNotReady from err


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload IntelliCenter config entry."""

    # Unload entities for this entry/device.

    all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
            ]
        )
    )

    # Cleanup
    handler = hass.data[DOMAIN].pop(entry.entry_id, None)

    _LOGGER.info(f"unloading integration {entry.entry_id}")
    if handler:
        handler.stop()

    # if it was the last instance of this integration, clear up the DOMAIN entry
    if not hass.data[DOMAIN]:
        del hass.data[DOMAIN]

    return True


# -------------------------------------------------------------------------------------


class PoolEntity(Entity):
    """Representation of an Pool entity linked to an pool object."""

    def __init__(
        self,
        entry: ConfigEntry,
        controller: ModelController,
        poolObject: PoolObject,
        attribute_key=STATUS_ATTR,
        name=None,
        enabled_by_default=True,
        extraStateAttributes=set(),
        icon: str = None,
        unit_of_measurement: str = None,
    ):
        """Initialize a Pool entity."""
        self._entry_id = entry.entry_id
        self._controller = controller
        self._poolObject = poolObject
        self._attr_available = True
        self._extra_state_attributes = extraStateAttributes
        self._attr_name = name
        self._attribute_key = attribute_key
        self._attr_entity_registry_enabled_default = enabled_by_default
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_icon = icon
        self._attr_should_poll = False

        _LOGGER.debug(f"mapping {poolObject}")

    async def async_added_to_hass(self):
        """Entity is added to Home Assistant."""
        self.async_on_remove(
            dispatcher.async_dispatcher_connect(
                self.hass, DOMAIN + "_UPDATE_" + self._entry_id, self._update_callback
            )
        )

        self.async_on_remove(
            dispatcher.async_dispatcher_connect(
                self.hass,
                DOMAIN + "_CONNECTION_" + self._entry_id,
                self._connection_callback,
            )
        )

    async def async_will_remove_from_hass(self) -> None:
        """Entity is removed from Home Assistant."""
        _LOGGER.debug(f"removing entity: {self.unique_id}")

    @property
    def name(self):
        """Return the name of the entity."""

        if self._attr_name is None:
            # default is to return the name of the underlying pool object
            return self._poolObject.sname
        elif self._attr_name.startswith("+"):
            # name is a suffix
            return self._poolObject.sname + self._attr_name[1:]
        else:
            return self._attr_name

    @property
    def unique_id(self):
        """Return a unique ID."""
        my_id = self._entry_id + self._poolObject.objnam
        if self._attribute_key != STATUS_ATTR:
            my_id += self._attribute_key
        return my_id

    @property
    def device_info(self):
        """Return the device info."""

        systemInfo = self._controller.systemInfo

        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "manufacturer": "Pentair",
            "model": "IntelliCenter",
            "name": systemInfo.propName,
            "sw_version": systemInfo.swVersion,
        }

    @property
    def extra_state_attributes(self) -> Optional[dict[str, Any]]:
        """Return the state attributes of the entity."""

        object = self._poolObject

        objectType = object.objtype
        if object.subtype:
            objectType += f"/{object.subtype}"

        attributes = {"OBJNAM": object.objnam, "OBJTYPE": objectType}

        if object.status:
            attributes["Status"] = object.status

        for attribute in self._extra_state_attributes:
            if object[attribute]:
                attributes[attribute] = object[attribute]

        return attributes

    def requestChanges(self, changes: dict) -> None:
        """Request changes as key:value pairs to the associated Pool object."""
        # since we don't care about waiting for the response we set waitForResponse to False
        # whatever changes were requested will be reflected as an update if successful
        # (also I found out there is no event loop in that thread for a Future would fail)
        self._controller.requestChanges(
            self._poolObject.objnam, changes, waitForResponse=False
        )

    def isUpdated(self, updates: dict[str, dict[str, str]]) -> bool:
        """Return true if the entity is updated by the updates from Intellicenter."""

        return self._attribute_key in updates.get(self._poolObject.objnam, {})

    @callback
    def _update_callback(self, updates: dict[str, dict[str, str]]):
        """Update the entity if its underlying pool object has changed."""

        if self.isUpdated(updates):
            self._attr_available = True
            _LOGGER.debug(f"updating {self} from {updates}")
            self.async_write_ha_state()

    @callback
    def _connection_callback(self, is_connected):
        """Mark the entity as unavailable after being disconnected from the server."""
        if is_connected:
            self._poolObject = self._controller.model[self._poolObject.objnam]
            if not self._poolObject:
                # this is for the rare case where the object the entity is mapped to
                # had been removed from the Pentair system while we were disconnected
                return
        self._attr_available = is_connected
        self.async_write_ha_state()

    def pentairTemperatureSettings(self):
        """Return the temperature units from the Pentair system."""
        return (
            UnitOfTemperature.CELSIUS
            if self._controller.systemInfo.usesMetric
            else UnitOfTemperature.FAHRENHEIT
        )
