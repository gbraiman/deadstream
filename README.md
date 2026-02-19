# Deadstream for Home Assistant

[![HACS Badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/gbraiman/deadstream.svg)](https://github.com/gbraiman/deadstream/releases)
[![Validate](https://github.com/gbraiman/deadstream/actions/workflows/validate.yml/badge.svg)](https://github.com/gbraiman/deadstream/actions/workflows/validate.yml)

A Home Assistant integration that streams Grateful Dead concert recordings from [archive.org](https://archive.org/details/GratefulDead) to Sonos, Chromecast, and any other HA-compatible media player.

Inspired by the [deadstream Raspberry Pi hardware project](https://github.com/eichblatt/deadstream), this integration brings the same time-machine concert browsing experience into Home Assistant — no dedicated hardware required.

---

## Features

- **Date-based browsing** — select any year (1965–1995), month, and day using dropdown selectors
- **Multiple recordings per date** — choose between different tapers and sources
- **Streams to any HA media player** — Sonos, Chromecast, generic HTTP players
- **Favored taper support** — automatically rank your preferred taper first
- **Lossless audio** — optionally prefer FLAC/SHN over MP3
- **Random show** — discover a new concert with one button press
- **Media browser** — browse shows directly from the HA media browser UI
- **Fully HACS installable** — no YAML, no SSH

---

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Go to **Integrations**
3. Click the three-dot menu → **Custom repositories**
4. Add `https://github.com/gbraiman/deadstream` as an **Integration**
5. Search for **Deadstream** and install it
6. Restart Home Assistant

### Manual

1. Download the latest release
2. Copy `custom_components/deadstream/` to your HA `custom_components/` directory
3. Restart Home Assistant

---

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Deadstream**
3. Configure:
   - **Target Media Player** — your Sonos speaker, Chromecast, etc.
   - **Collections** — which archive.org collections to include
   - **Prefer Lossless Audio** — FLAC/SHN when available
   - **Favored Taper** — e.g. `miller` to rank that taper first

---

## Entities Created

| Entity | Type | Description |
|--------|------|-------------|
| `media_player.deadstream` | Media Player | Main player — use for play/pause/skip |
| `select.deadstream_year` | Select | Concert year (1965–1995) |
| `select.deadstream_month` | Select | Concert month |
| `select.deadstream_day` | Select | Concert day |
| `select.deadstream_show` | Select | Which recording to use for this date |
| `button.deadstream_load_show` | Button | Load tracks for the selected show |
| `button.deadstream_next_show` | Button | Next recording for current date |
| `button.deadstream_prev_show` | Button | Previous recording for current date |
| `button.deadstream_random_show` | Button | Jump to a random concert |
| `sensor.deadstream_venue` | Sensor | Current venue & city |
| `sensor.deadstream_current_track` | Sensor | Currently playing track title |
| `sensor.deadstream_shows_available` | Sensor | Number of recordings for selected date |
| `sensor.deadstream_taper` | Sensor | Taper of current recording |

---

## Dashboard Card

Paste into Lovelace's raw YAML editor for a complete controller:

```yaml
type: vertical-stack
cards:
  - type: entities
    title: Deadstream — Grateful Dead Time Machine
    entities:
      - entity: select.deadstream_year
      - entity: select.deadstream_month
      - entity: select.deadstream_day
      - entity: select.deadstream_show
  - type: horizontal-stack
    cards:
      - type: button
        entity: button.deadstream_load_show
        name: Load Show
        icon: mdi:playlist-play
      - type: button
        entity: button.deadstream_random_show
        name: Random
        icon: mdi:shuffle-variant
      - type: button
        entity: button.deadstream_prev_show
        name: Prev
        icon: mdi:skip-previous-circle
      - type: button
        entity: button.deadstream_next_show
        name: Next
        icon: mdi:skip-next-circle
  - type: media-control
    entity: media_player.deadstream
  - type: entities
    entities:
      - entity: sensor.deadstream_venue
      - entity: sensor.deadstream_current_track
      - entity: sensor.deadstream_taper
      - entity: sensor.deadstream_shows_available
```
---

## How It Works

1. You select a year, month, and day using the select entities
2. Deadstream queries the archive.org API for concert recordings on that date
3. You choose which recording (taper) to use via the Show selector
4. Press Load Show to fetch the track list
5. Press Play on the media player — Deadstream sends the stream URL directly to your target Sonos/Chromecast

The integration acts as a smart source that feeds archive.org stream URLs to your existing media players. Playback, volume, and queue management all happen on the target device.

---

## Services

| Service | Description |
|---------|-------------|
| `deadstream.play_date` | Jump to a specific date and play |
| `deadstream.next_show` | Next recording for current date |
| `deadstream.prev_show` | Previous recording for current date |
| `deadstream.random_show` | Load a random concert |

Example — automation for a date
```yaml
service: deadstream.play_date
data:
  year: 1977
  month: 5
  day: 8
```
Example — automation triggered by voice
```yaml
alias: Play a random Dead show
trigger:
  - platform: conversation
    command: "play a random dead show"
action:
  - service: deadstream.random_show
  - service: media_player.media_play
    target:
      entity_id: media_player.deadstream
```
## Supported Collections

| Collection | Description |
|------------|-------------|
| `GratefulDead` | Main Grateful Dead archive |
| `PhilLesh` | Phil Lesh & Friends |
| `BobWeir` | Bob Weir solo/Ratdog |
| `JerryGarciaBand` | Jerry Garcia Band |
| `OtherOnes` | The Other Ones |


---

## Contributing
Pull requests welcome. Please open an issue first for major changes.

---

## License
MIT License. Concert recordings are streamed via archive.org's open API. All recordings belong to their respective tapers who have shared them freely.
