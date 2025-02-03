"""Pentair Intellicenter numbers."""

import logging

from homeassistant.components.number import (
    DEFAULT_MAX_VALUE,
    DEFAULT_MIN_VALUE,
    DEFAULT_STEP,
    NumberEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant

from . import PoolEntity
from .const import DOMAIN
from .pyintellicenter import (
    BODY_ATTR,
    BODY_TYPE,
    CHEM_TYPE,
    PRIM_ATTR,
    SEC_ATTR,
    ModelController,
    PoolObject,
)

_LOGGER = logging.getLogger(__name__)

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
            # Get the list of bodies configured for this Intellichlor
            intellichlor_bodies = obj[BODY_ATTR].split(" ")
            _LOGGER.debug(f"Intellichlor bodies configured: {intellichlor_bodies}")

            # Only process bodies that are explicitly configured
            for body_id in intellichlor_bodies:
                body = controller.model.getByID(body_id)
                if not body:
                    _LOGGER.warning(
                        f"Configured Intellichlor body '{body_id}' not found in system"
                    )
                    continue

                # Determine if this is primary or secondary
                intellichlor_index = intellichlor_bodies.index(body_id)
                attribute_key = PRIM_ATTR if intellichlor_index == 0 else SEC_ATTR

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
