"""Constants for the SwitchBot RGBICWW Ceiling Light integration."""

from switchbot import SwitchbotModel

DOMAIN = "switchbot_ceiling"
MANUFACTURER = "SwitchBot"
MODEL = SwitchbotModel.RGBICWW_CEILING_LIGHT

CONF_KEY_ID = "key_id"
CONF_ENCRYPTION_KEY = "encryption_key"

MIN_KELVIN = 2700
MAX_KELVIN = 6500

# Segment effect styles of the color ring (SwitchBot app, LightColorUtils).
SEGMENT_STYLES = {
    "flow": 50,
    "rebound": 52,
    "breath": 53,
    "cover": 55,
    "pile": 57,
    "wave": 61,
    "flash": 62,
    "comet": 63,
}
SEGMENT_EFFECT_PREFIX = "segment_"
MAX_SEGMENT_COLORS = 10
DEFAULT_SEGMENT_COLORS = "FF0000,00FF00,0000FF"
DEFAULT_SPEED = 50

# Fade times (seconds) for switching on/off via the device timer.
DEFAULT_FADE = 0
MAX_FADE = 3600

# Timer actions per sub-light (same encoding as the sub-light selector).
ACTION_KEEP = 0
ACTION_ON = 1
ACTION_OFF = 2
