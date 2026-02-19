# Deadstream

Stream Grateful Dead concerts from [archive.org](https://archive.org/details/GratefulDead) directly to your Sonos, Chromecast, or any other Home Assistant media player.

## Features

- Browse thousands of live recordings by **year, month, and day**
- Multiple recordings per date with taper info
- Stream to **Sonos, Chromecast, generic media players**
- Prefers your **favored taper** automatically
- Supports both **lossless (FLAC/SHN) and MP3** streams
- **Random show** button for discovering new concerts
- Full **media browser** integration

## Quick Start

1. Install via HACS
2. Go to **Settings → Devices & Services → Add Integration → Deadstream**
3. Select your target media player (Sonos, etc.)
4. Use the Year/Month/Day selectors to pick a date
5. Press **Load Show** then **Play**

## Dashboard

Add the following entities to a Lovelace card for a complete UI:

- `select.deadstream_year`
- `select.deadstream_month`
- `select.deadstream_day`
- `select.deadstream_show`
- `button.deadstream_load_show`
- `button.deadstream_random_show`
- `media_player.deadstream`
- `sensor.deadstream_venue`
- `sensor.deadstream_current_track`
