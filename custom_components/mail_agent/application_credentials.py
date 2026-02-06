"""Application credentials platform for Mail Agent."""
from homeassistant.components.application_credentials import AuthorizationServer
from homeassistant.core import HomeAssistant


async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer:
    """Return authorization server."""
    return AuthorizationServer(
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
    )


async def async_get_description_placeholder(hass: HomeAssistant) -> dict[str, str]:
    """Return description placeholder for the credentials dialog."""
    return {
        "more_info_url": "https://developers.google.com/gmail/api/quickstart/python"
    }
