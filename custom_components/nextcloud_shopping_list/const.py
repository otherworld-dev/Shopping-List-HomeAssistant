"""Constants for the Nextcloud Shopping List integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "nextcloud_shopping_list"

CONF_SERVER: Final = "server"
CONF_LOGIN_NAME: Final = "login_name"
CONF_APP_PASSWORD: Final = "app_password"
CONF_HIDDEN_LISTS: Final = "hidden_lists"
CONF_VIA_LABEL: Final = "via_label"

DEFAULT_VIA_LABEL: Final = "Home Assistant"

SCAN_INTERVAL: Final = timedelta(seconds=30)

# Server features this integration needs, from the app's capabilities
REQUIRED_FEATURES: Final = ("text-input", "via-label")
# The first server release with both of them
REQUIRED_SERVER_VERSION: Final = "1.13.0"

VIA_HEADER: Final = "X-Shopping-List-Via"
# Nextcloud names the app password after the user agent of the login request
USER_AGENT: Final = "Home Assistant Shopping List"

API_BASE: Final = "/ocs/v2.php/apps/shopping_list/api/v1"
CAPABILITIES_PATH: Final = "/ocs/v2.php/cloud/capabilities"
