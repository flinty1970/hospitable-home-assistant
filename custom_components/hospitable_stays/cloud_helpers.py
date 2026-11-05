"""Load optional Cloud helpers only when Home Assistant Cloud is configured."""

from hass_nabucasa import NabuCasaBaseError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


def cloud_active(hass: HomeAssistant) -> bool:
    """Allow polling without importing Cloud's optional dependency tree."""
    if "cloud" not in hass.data:
        return False
    from homeassistant.components import cloud

    return cloud.async_active_subscription(hass)


def cloud_connected(hass: HomeAssistant) -> bool:
    if "cloud" not in hass.data:
        return False
    from homeassistant.components import cloud

    return cloud.async_is_connected(hass)


async def get_hook(hass: HomeAssistant, hook_id: str) -> str:
    if not cloud_active(hass) or not cloud_connected(hass):
        raise HomeAssistantError("Home Assistant Cloud is unavailable")
    from homeassistant.components import cloud

    try:
        return await cloud.async_get_or_create_cloudhook(hass, hook_id)
    except NabuCasaBaseError:
        raise HomeAssistantError("Could not create the Cloud hook") from None


async def delete_hook(hass: HomeAssistant, hook_id: str) -> None:
    from homeassistant.components import cloud

    try:
        await cloud.async_delete_cloudhook(hass, hook_id)
    except NabuCasaBaseError:
        raise HomeAssistantError("Could not delete the Cloud hook") from None
