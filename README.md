# Deadstream for Home Assistant

[![HACS Badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/gbraiman/deadstream.svg)](https://github.com/gbraiman/deadstream/releases)
[![Validate](https://github.com/gbraiman/deadstream/actions/workflows/validate.yml/badge.svg)](https://github.com/gbraiman/deadstream/actions/workflows/validate.yml)

A Home Assistant integration that streams live concert recordings from [archive.org](https://archive.org) to any HA-compatible media player — Sonos, Chromecast, VLC, and more.

Supports the **Grateful Dead**, **Phish**, **Goose**, **Phil Lesh & Friends**, **Jerry Garcia Band**, **Bob Weir**, and related acts. Browse by date across all years, pick a taper, and press Play.

---

## Features

- **Multi-band** — browse Grateful Dead, Phish, Goose, and more simultaneously; band labels distinguish shows when multiple are active
- **Date-based browsing** — pick any month and day; the Show list fills with every recording across all years for all active bands
- **Taper selection** — choose between different recordings of the same show, sorted by popularity
- **Auto-advance** — plays the full setlist track by track automatically
- **True pause/resume** — pause and resume from the exact moment, not the start of the track
- **Seek / progress bar** — scrub to any position via the HA media control card
- **Cover art** — album artwork pulled from archive.org for every show
- **Default speaker** — set a speaker at setup so pressing Play is always predictable
- **Favored taper** — rank your preferred taper first in results
- **Lossless audio** — optionally prefer FLAC/SHN over MP3
- **Random show** — discover a new concert with one button press
- **Today in History** — instantly load every recording of today's date from all years
- **Media browser** — browse shows from the HA media browser UI
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
   - **Bands** — which archive.org collections to include (a toggle switch is created for each one)
   - **Default Speaker** — the media player to stream to when Deadstream loads
   - **Prefer Lossless Audio** — FLAC/SHN when available
   - **Favored Taper** — e.g. `miller` to rank that taper first

Band toggles only appear for the bands you select here. To add or remove bands, open the integration's **Options** and re-save — HA will reload the switches automatically.

---

## Entities Created

| Entity | Type | Description |
|--------|------|-------------|
| `media_player.deadstream` | Media Player | Main player — play/pause/seek/skip/volume |
| `select.deadstream_month` | Select | Concert month |
| `select.deadstream_day` | Select | Concert day |
| `select.deadstream_show` | Select | Which year/band show to play |
| `select.deadstream_taper` | Select | Which recording (taper) to use |
| `select.deadstream_target_player` | Select | Override the active output speaker |
| `switch.deadstream_*` | Switch | Per-band toggle (one per configured band) |
| `button.deadstream_today_in_history` | Button | Load all recordings of today's date |
| `button.deadstream_load_show` | Button | Manually pre-load the selected show |
| `button.deadstream_next_show` | Button | Next show in the list |
| `button.deadstream_prev_show` | Button | Previous show in the list |
| `button.deadstream_random_show` | Button | Jump to a random concert |
| `sensor.deadstream_venue` | Sensor | Current venue & city |
| `sensor.deadstream_current_track` | Sensor | Currently playing track title |
| `sensor.deadstream_next_track` | Sensor | Next track title |
| `sensor.deadstream_shows_available` | Sensor | Number of recordings for selected date |
| `sensor.deadstream_taper` | Sensor | Taper of current recording |

---

## Dashboard Card

```yaml
type: vertical-stack
cards:
  - type: entities
    title: Deadstream
    entities:
      - entity: select.deadstream_month
      - entity: select.deadstream_day
      - entity: select.deadstream_show
      - entity: select.deadstream_taper
      - entity: select.deadstream_target_player
  - type: horizontal-stack
    cards:
      - type: button
        entity: button.deadstream_today_in_history
        name: Today
        icon: mdi:history
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
      - entity: sensor.deadstream_next_track
      - entity: sensor.deadstream_taper
      - entity: sensor.deadstream_shows_available
  - type: entities
    title: Bands
    entities:
      - entity: switch.deadstream_grateful_dead
      - entity: switch.deadstream_phish
      - entity: switch.deadstream_goose
```

---

## How It Works

1. Pick a **month and day** — the Show list fills with every recording across all years for all active bands
2. Select a **show** — labeled `1977 — Barton Hall, Cornell` or `1995 Phish — Red Rocks` when multiple bands are active
3. Select a **taper** — sorted by archive.org download count (most-played first)
4. Press **Play** — tracks are loaded automatically and streamed to your speaker; the full setlist plays through without any interaction

The integration streams archive.org URLs directly to your target player. Volume, transport, and queue all happen on the target device; Deadstream handles show browsing and track sequencing.

---

## Supported Collections

| Collection ID | Display Name |
|--------------|--------------|
| `GratefulDead` | Grateful Dead |
| `Phish` | Phish |
| `Goose` | Goose |
| `PhilLesh` | Phil Lesh & Friends |
| `JerryGarciaBand` | Jerry Garcia Band |
| `BobWeir` | Bob Weir |
| `OtherOnes` | The Other Ones |
| `TheOtherOnes` | The Other Ones (alt) |

---

## Services

| Service | Description |
|---------|-------------|
| `deadstream.play_date` | Jump to a specific month/day |
| `deadstream.next_show` | Next show for the current date |
| `deadstream.prev_show` | Previous show for the current date |
| `deadstream.random_show` | Load a random concert |
| `deadstream.today_in_history` | Load today's month/day across all years |

### Example — automation for a specific date

```yaml
service: deadstream.play_date
data:
  month: 5
  day: 8
```

### Example — voice-triggered random show

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

---

## Contributing

Pull requests welcome. Please open an issue first for major changes.

---

## License

MIT License. Concert recordings are streamed via archive.org's open API. All recordings belong to their respective tapers who have shared them freely.
