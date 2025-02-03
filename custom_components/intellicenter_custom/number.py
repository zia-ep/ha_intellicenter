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
