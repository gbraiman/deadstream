"""Constants for the Deadstream integration."""

DOMAIN = "deadstream"

# Config entry keys
CONF_COLLECTIONS = "collections"
CONF_TARGET_PLAYER = "target_player"
CONF_PLAY_LOSSLESS = "play_lossless"
CONF_FAVORED_TAPER = "favored_taper"

# Defaults
DEFAULT_COLLECTIONS = ["GratefulDead"]
DEFAULT_PLAY_LOSSLESS = False
DEFAULT_FAVORED_TAPER = ""

# Archive.org API
ARCHIVE_SEARCH_URL = "https://archive.org/services/search/v1/scrape"
ARCHIVE_METADATA_URL = "https://archive.org/metadata/{}"
ARCHIVE_DOWNLOAD_URL = "https://archive.org/download/{}/{}"

# Audio format preferences
LOSSLESS_FORMATS = ["Flac", "Shorten", "Ogg Vorbis"]
LOSSY_FORMATS = ["VBR MP3", "MP3"]

# Entity attribute keys
ATTR_VENUE = "venue"
ATTR_SHOW_DATE = "show_date"
ATTR_TAPE_ID = "tape_id"
ATTR_TRACK_NUMBER = "track_number"
ATTR_TOTAL_TRACKS = "total_tracks"
ATTR_SETLIST = "setlist"
ATTR_TAPER = "taper"
ATTR_COLLECTION = "collection"

# Service names
SERVICE_PLAY_DATE = "play_date"
SERVICE_NEXT_SHOW = "next_show"
SERVICE_PREV_SHOW = "prev_show"
SERVICE_RANDOM_SHOW = "random_show"

# Update interval (seconds)
UPDATE_INTERVAL = 30

# Available collections on archive.org
AVAILABLE_COLLECTIONS = [
    "GratefulDead",
    "PhilLesh",
    "BobWeir",
    "JerryGarciaBand",
    "OtherOnes",
    "TheOtherOnes",
]
