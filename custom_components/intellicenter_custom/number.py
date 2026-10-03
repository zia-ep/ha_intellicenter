"""Pentair Intellicenter numbers."""

import logging

from homeassistant.components.number import (
    DEFAULT_MAX_VALUE,
    DEFAULT_MIN_VALUE,
    DEFAULT_STEP,
    NumberEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, REVOLUTIONS_PER_MINUTE
from homeassistant.core import HomeAssistant

from . import PoolEntity
from .const import DOMAIN
from .pyintellicenter import (
    BODY_ATTR,
    BODY_TYPE,
    CHEM_TYPE,
    CIRCUIT_ATTR,
    PARENT_ATTR,
    PMPCIRC_TYPE,
    PRIM_ATTR,
    SEC_ATTR,
    SELECT_ATTR,
    ModelController,
    PoolObject,
)

_LOGGER = logging.getLogger(__name__)

# lowest speed offered for a pump circuit, so a heater on the same plumbing
# keeps enough flow (the pump itself accepts down to its MIN, e.g. 450)
PUMP_SPEED_FLOOR = 1000
PUMP_SPEED_STEP = 50

# -------------------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Load pool numbers based on a config entry."""
    controller: ModelController = hass.data[DOMAIN][entry.entry_id].controller
    numbers = []

    obj: PoolObject
    for obj in controller.model.objectList:
        if (
            obj.objtype == CHEM_TYPE
            and obj.subtype == "ICHLOR"
            and PRIM_ATTR in obj.attributes
        ):
            bodies = controller.model.getByType(BODY_TYPE)
            intellichlor_bodies = obj[BODY_ATTR].split(" ")

            _LOGGER.debug(f"Intellichlor bodies found: {intellichlor_bodies}")

            body: PoolObject
            for body in bodies:
                # Only create controls for bodies that have ICHLOR support
                if body.objnam not in intellichlor_bodies:
                    _LOGGER.debug(
                        f"Skipping Intellichlor control for body '{body.objnam}' - not in configured list: {intellichlor_bodies}"
                    )
                    continue

                intellichlor_index = intellichlor_bodies.index(body.objnam)
                attribute_key = None
                if intellichlor_index == 0:
                    attribute_key = PRIM_ATTR
                elif intellichlor_index == 1:
                    attribute_key = SEC_ATTR
                if attribute_key is not None:
                    numbers.append(
                        PoolNumber(
                            entry,
                            controller,
                            obj,
                            unit_of_measurement=PERCENTAGE,
                            attribute_key=attribute_key,
                            name=f"+ Output % ({body.sname})",
                        )
                    )
        elif obj.objtype == PMPCIRC_TYPE and obj[SELECT_ATTR] == "RPM":
            pump = controller.model[obj[PARENT_ATTR]]
            circuit = controller.model[obj[CIRCUIT_ATTR]]
            if pump is None or circuit is None:
                _LOGGER.debug(f"Skipping pump speed for '{obj.objnam}' - pump or circuit unknown")
                continue
            numbers.append(PoolPumpSpeedNumber(entry, controller, obj, pump, circuit))

    async_add_entities(numbers)


# -------------------------------------------------------------------------------------


class PoolNumber(PoolEntity, NumberEntity):
    """Representation of a pool number entity."""

    def __init__(
        self,
        entry: ConfigEntry,
        controller: ModelController,
        poolObject: PoolObject,
        min_value: float = DEFAULT_MIN_VALUE,
        max_value: float = DEFAULT_MAX_VALUE,
        step: float = DEFAULT_STEP,
        **kwargs,
    ):
        """Initialize."""
        super().__init__(entry, controller, poolObject, **kwargs)
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        self._attr_icon = "mdi:gauge"

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self._poolObject[self._attribute_key]

    def set_native_value(self, value: float) -> None:
        """Update the current value."""
        changes = {self._attribute_key: str(int(value))}
        self.requestChanges(changes)


# -------------------------------------------------------------------------------------


class PoolPumpSpeedNumber(PoolNumber):
    """RPM a pump runs at when a given circuit is on (a PMPCIRC object)."""

    def __init__(
        self,
        entry: ConfigEntry,
        controller: ModelController,
        poolObject: PoolObject,
        pump: PoolObject,
        circuit: PoolObject,
    ):
        """Initialize."""
        super().__init__(
            entry,
            controller,
            poolObject,
            min_value=max(PUMP_SPEED_FLOOR, _to_int(pump["MIN"], 0)),
            max_value=_to_int(pump["MAX"], 3450),
            step=PUMP_SPEED_STEP,
            unit_of_measurement=REVOLUTIONS_PER_MINUTE,
            attribute_key="SPEED",
            name=f"{circuit.sname} pump speed",
        )
        self._attr_icon = "mdi:pump"

    @property
    def native_value(self) -> int | None:
        """Return the current speed setting."""
        return _to_int(self._poolObject["SPEED"], None)


def _to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
