"""Deadstream media player entity."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime as dt
from typing import Any

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_SETLIST,
    ATTR_SHOW_DATE,
    ATTR_TAPE_ID,
    ATTR_TAPER,
    ATTR_TOTAL_TRACKS,
    ATTR_TRACK_NUMBER,
    ATTR_VENUE,
    DOMAIN,
)
from .coordinator import DeadstreamCoordinator

_LOGGER = logging.getLogger(__name__)

SUPPORTED_FEATURES = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.BROWSE_MEDIA
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.SEEK
)

# States a target player can reach when a track ends naturally.
_TRACK_END_STATES = frozenset({
    MediaPlayerState.IDLE,
    MediaPlayerState.OFF,
    MediaPlayerState.STANDBY,
    "stopped",
})


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Deadstream media player."""
    coordinator: DeadstreamCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DeadstreamMediaPlayer(coordinator, entry)])


class DeadstreamMediaPlayer(CoordinatorEntity[DeadstreamCoordinator], MediaPlayerEntity):
    """Deadstream virtual media player — streams archive.org concerts to target players."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_media_content_type = MediaType.MUSIC
    _attr_supported_features = SUPPORTED_FEATURES

    def __init__(self, coordinator: DeadstreamCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_player"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Deadstream",
            "manufacturer": "archive.org",
            "model": "Concert Time Machine",
            "entry_type": "service",
        }
        self._volume: float = 0.5
        self._track_listener_unsub = None
        self._active_track_url: str | None = None

    @property
    def name(self) -> str:
        return "Deadstream"

    @property
    def state(self) -> MediaPlayerState:
        if not self.coordinator.available_shows:
            return MediaPlayerState.IDLE
        if self.coordinator.is_playing:
            return MediaPlayerState.PLAYING
        if self.coordinator.current_tracks:
            return MediaPlayerState.PAUSED
        return MediaPlayerState.IDLE

    @property
    def media_title(self) -> str | None:
        track = self.coordinator.current_track
        if track:
            return track.title
        show = self.coordinator.current_show
        return show.title if show else None

    @property
    def media_artist(self) -> str | None:
        show = self.coordinator.current_show
        return show.location if show else None

    @property
    def media_album_name(self) -> str | None:
        show = self.coordinator.current_show
        return show.display_date if show else None

    @property
    def media_track(self) -> int | None:
        if self.coordinator.current_tracks:
            return self.coordinator.current_track_index + 1
        return None

    @property
    def volume_level(self) -> float:
        return self._volume

    @property
    def media_image_url(self) -> str | None:
        show = self.coordinator.current_show
        if show:
            # Use the collection-level image (band photo) rather than the
            # item-level image which is typically the spectral waveform.
            return f"https://archive.org/services/img/{show.collection}"
        return None

    @property
    def media_position(self) -> float | None:
        """Forward playback position from the active target player."""
        target = self.coordinator.target_player
        if target:
            state = self.hass.states.get(target)
            if state:
                return state.attributes.get("media_position")
        return None

    @property
    def media_position_updated_at(self) -> dt | None:
        """Forward the position timestamp from the active target player."""
        target = self.coordinator.target_player
        if target:
            state = self.hass.states.get(target)
            if state:
                return state.attributes.get("media_position_updated_at")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        show = self.coordinator.current_show
        if show:
            attrs[ATTR_VENUE] = show.venue
            attrs[ATTR_SHOW_DATE] = show.date
            attrs[ATTR_TAPE_ID] = show.identifier
            attrs[ATTR_TAPER] = show.taper
            attrs[ATTR_TOTAL_TRACKS] = len(self.coordinator.current_tracks)
        track = self.coordinator.current_track
        if track:
            attrs[ATTR_TRACK_NUMBER] = track.track_num
        if self.coordinator.current_tracks:
            attrs[ATTR_SETLIST] = [t.title for t in self.coordinator.current_tracks]
        return attrs

    # ------------------------------------------------------------------
    # Playback control
    # ------------------------------------------------------------------

    async def async_media_play(self) -> None:
        if not self.coordinator.current_tracks:
            # Nothing loaded yet — fetch tracks and stream the first one.
            if not await self.coordinator.async_load_current_show():
                _LOGGER.warning("No tracks to play")
                return

        track = self.coordinator.current_track
        if not track:
            _LOGGER.warning("No track selected to play")
            return

        self.coordinator.is_playing = True
        if self._active_track_url == track.url:
            # Same track was already loaded on the target player, so resume.
            await self._call_all_targets("media_play", {})
            self._register_track_listener()
        else:
            # New show/taper selection: replace whatever is on the target player.
            await self._send_to_target_players(fresh_start=True)
        self.async_write_ha_state()

    async def async_media_pause(self) -> None:
        self._cancel_track_listener()
        self.coordinator.is_playing = False
        await self._call_all_targets("media_pause", {})
        self.async_write_ha_state()

    async def async_media_stop(self) -> None:
        self._cancel_track_listener()
        self._active_track_url = None
        self.coordinator.is_playing = False
        self.coordinator.current_tracks = []
        self.coordinator.current_track_index = 0
        await self._call_all_targets("media_stop", {})
        self.async_write_ha_state()

    async def async_media_next_track(self) -> None:
        if self.coordinator.next_track():
            self.coordinator.is_playing = True
            await self._send_to_target_players()
        self.async_write_ha_state()

    async def async_media_previous_track(self) -> None:
        if self.coordinator.prev_track():
            self.coordinator.is_playing = True
            await self._send_to_target_players()
        self.async_write_ha_state()

    async def async_set_volume_level(self, volume: float) -> None:
        self._volume = volume
        await self._call_all_targets("volume_set", {"volume_level": volume})
        self.async_write_ha_state()

    async def async_media_seek(self, position: float) -> None:
        """Seek to a position on the target player."""
        await self._call_all_targets("media_seek", {"seek_position": position})

    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        """Play a specific show by archive.org identifier."""
        show = next(
            (s for s in self.coordinator.available_shows if s.identifier == media_id),
            None,
        )
        if show:
            self.coordinator.current_show_index = self.coordinator.available_shows.index(show)
        if await self.coordinator.async_load_current_show():
            self.coordinator.is_playing = True
            await self._send_to_target_players(fresh_start=True)
        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # Media browsing
    # ------------------------------------------------------------------

    async def async_browse_media(
        self,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        if media_content_id is None:
            shows = self.coordinator.available_shows
            children = [
                BrowseMedia(
                    title=f"{show.display_date} — {show.location}",
                    media_class="music",
                    media_content_id=show.identifier,
                    media_content_type=MediaType.MUSIC,
                    can_play=True,
                    can_expand=True,
                    thumbnail=None,
                )
                for show in shows
            ]
            return BrowseMedia(
                title="Deadstream Shows",
                media_class="directory",
                media_content_id="root",
                media_content_type="directory",
                can_play=False,
                can_expand=True,
                children=children,
            )

        tracks = await self.coordinator.client.get_show_tracks(
            media_content_id, self.coordinator.play_lossless
        )
        children = [
            BrowseMedia(
                title=f"{t.track_num}. {t.title}",
                media_class="music",
                media_content_id=t.url,
                media_content_type=MediaType.MUSIC,
                can_play=True,
                can_expand=False,
                thumbnail=None,
            )
            for t in tracks
        ]
        return BrowseMedia(
            title=media_content_id,
            media_class="music",
            media_content_id=media_content_id,
            media_content_type=MediaType.MUSIC,
            can_play=True,
            can_expand=True,
            children=children,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def async_will_remove_from_hass(self) -> None:
        """Clean up track-end listener when entity is removed."""
        self._cancel_track_listener()

    def _cancel_track_listener(self) -> None:
        """Unsubscribe from target player state changes."""
        if self._track_listener_unsub:
            self._track_listener_unsub()
            self._track_listener_unsub = None

    def _register_track_listener(self) -> None:
        """Listen for target player going idle so we can auto-advance."""
        self._cancel_track_listener()
        targets = [eid for eid in self.coordinator.target_players if self.hass.states.get(eid)]
        if not targets:
            return
        self._track_listener_unsub = async_track_state_change_event(
            self.hass, targets, self._handle_target_state_change
        )

    @callback
    def _handle_target_state_change(self, event: Any) -> None:
        """Auto-advance to the next track when the target player finishes."""
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if not old_state or not new_state:
            return
        # Fire when the target transitions to an end state from playing or paused.
        # Some players (e.g. Sonos) go PLAYING → PAUSED → IDLE when a track ends
        # naturally, so we catch both old states here.
        # coordinator.is_playing guards against this firing on an intentional pause.
        if (
            old_state.state not in _TRACK_END_STATES
            and old_state.state not in ("unknown", "unavailable")
            and new_state.state in _TRACK_END_STATES
            and self.coordinator.is_playing
        ):
            self.hass.async_create_task(self._auto_advance())

    async def _auto_advance(self) -> None:
        """Advance to the next track, or stop at end of setlist.

        A short sleep guards against false positives: when play_media loads a
        new URL the target player briefly goes idle before buffering starts,
        which would otherwise look like a natural track end.
        """
        self._cancel_track_listener()
        await asyncio.sleep(2)
        if not self.coordinator.is_playing:
            return
        # If the target already recovered to playing, it wasn't a real track end.
        for eid in self.coordinator.target_players:
            s = self.hass.states.get(eid)
            if s and s.state == MediaPlayerState.PLAYING:
                self._register_track_listener()
                return
        if self.coordinator.next_track():
            await self._send_to_target_players()
            self.async_write_ha_state()
        else:
            self.coordinator.is_playing = False
            self.async_write_ha_state()

    async def _send_to_target_players(self, fresh_start: bool = False) -> None:
        """Stream the current track URL to every configured target player.

        fresh_start=True: stop the target first so it doesn't resume a
        previously paused track when we swap to a different show.
        """
        track = self.coordinator.current_track
        if not track:
            return
        targets = [
            eid for eid in self.coordinator.target_players
            if self.hass.states.get(eid)
        ]
        if not targets:
            _LOGGER.warning(
                "No target player selected. Use the Target Player selector to choose a destination."
            )
            return
        if fresh_start:
            # Stop the target first so it doesn't resume a previously paused track.
            await self.hass.services.async_call(
                "media_player", "media_stop", {"entity_id": targets}
            )
        _LOGGER.debug("Sending %s to %s", track.url, targets)
        await self.hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": targets,
                "media_content_id": track.url,
                "media_content_type": MediaType.MUSIC,
            },
        )
        self._active_track_url = track.url
        # Register listener so the next track plays automatically when this one ends.
        self._register_track_listener()

    async def _call_all_targets(self, service: str, extra: dict) -> None:
        """Call a media_player service on all active target players."""
        targets = [
            eid for eid in self.coordinator.target_players
            if self.hass.states.get(eid)
        ]
        if not targets:
            return
        await self.hass.services.async_call(
            "media_player",
            service,
            {"entity_id": targets, **extra},
        )
