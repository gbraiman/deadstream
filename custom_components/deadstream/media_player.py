"""Deadstream media player entity."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
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
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Deadstream media player."""
    coordinator: DeadstreamCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DeadstreamMediaPlayer(coordinator, entry)])


class DeadstreamMediaPlayer(CoordinatorEntity[DeadstreamCoordinator], MediaPlayerEntity):
    """Deadstream virtual media player that streams to a target player."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_media_content_type = MediaType.MUSIC
    _attr_supported_features = SUPPORTED_FEATURES

    def __init__(self, coordinator: DeadstreamCoordinator, entry: ConfigEntry) -> None:
        """Initialize the media player."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_player"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Deadstream",
            "manufacturer": "archive.org",
            "model": "Grateful Dead Time Machine",
            "entry_type": "service",
        }
        self._volume: float = 0.5

    @property
    def name(self) -> str:
        """Return entity name."""
        return "Deadstream"

    @property
    def state(self) -> MediaPlayerState:
        """Return current playback state."""
        if not self.coordinator.available_shows:
            return MediaPlayerState.IDLE
        if self.coordinator.is_playing:
            return MediaPlayerState.PLAYING
        if self.coordinator.current_tracks:
            return MediaPlayerState.PAUSED
        return MediaPlayerState.IDLE

    @property
    def media_title(self) -> str | None:
        """Return current track title."""
        track = self.coordinator.current_track
        if track:
            return track.title
        show = self.coordinator.current_show
        if show:
            return show.title
        return None

    @property
    def media_artist(self) -> str | None:
        """Return artist name (venue/date for GD)."""
        show = self.coordinator.current_show
        if show:
            return show.location or "Grateful Dead"
        return "Grateful Dead"

    @property
    def media_album_name(self) -> str | None:
        """Return show date as album name."""
        show = self.coordinator.current_show
        if show:
            return show.display_date
        return None

    @property
    def media_track(self) -> int | None:
        """Return current track number."""
        if self.coordinator.current_tracks:
            return self.coordinator.current_track_index + 1
        return None

    @property
    def volume_level(self) -> float:
        """Return current volume level (0..1)."""
        return self._volume

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
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

    async def async_media_play(self) -> None:
        """Start or resume playback."""
        if not self.coordinator.current_tracks:
            loaded = await self.coordinator.async_load_current_show()
            if not loaded:
                _LOGGER.warning("No tracks to play")
                return

        self.coordinator.is_playing = True
        await self._send_to_target_player()
        self.async_write_ha_state()

    async def async_media_pause(self) -> None:
        """Pause playback."""
        self.coordinator.is_playing = False
        target = self.coordinator.target_player
        if target and self.hass.states.get(target):
            await self.hass.services.async_call(
                "media_player", "media_pause", {"entity_id": target}
            )
        self.async_write_ha_state()

    async def async_media_stop(self) -> None:
        """Stop playback."""
        self.coordinator.is_playing = False
        self.coordinator.current_tracks = []
        self.coordinator.current_track_index = 0
        target = self.coordinator.target_player
        if target and self.hass.states.get(target):
            await self.hass.services.async_call(
                "media_player", "media_stop", {"entity_id": target}
            )
        self.async_write_ha_state()

    async def async_media_next_track(self) -> None:
        """Skip to next track."""
        if self.coordinator.next_track():
            if self.coordinator.is_playing:
                await self._send_to_target_player()
        else:
            _LOGGER.debug("Already at last track")
        self.async_write_ha_state()

    async def async_media_previous_track(self) -> None:
        """Go back to previous track."""
        if self.coordinator.prev_track():
            if self.coordinator.is_playing:
                await self._send_to_target_player()
        self.async_write_ha_state()

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level."""
        self._volume = volume
        target = self.coordinator.target_player
        if target and self.hass.states.get(target):
            await self.hass.services.async_call(
                "media_player",
                "volume_set",
                {"entity_id": target, "volume_level": volume},
            )
        self.async_write_ha_state()

    async def async_play_media(
        self, media_type: str, media_id: str, **kwargs: Any
    ) -> None:
        """Play a specific media item by identifier."""
        # media_id can be an archive.org identifier
        show = next(
            (s for s in self.coordinator.available_shows if s.identifier == media_id),
            None,
        )
        if show:
            idx = self.coordinator.available_shows.index(show)
            self.coordinator.current_show_index = idx
        loaded = await self.coordinator.async_load_current_show()
        if loaded:
            self.coordinator.is_playing = True
            await self._send_to_target_player()
        self.async_write_ha_state()

    async def async_browse_media(
        self,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Browse available shows."""
        if media_content_id is None:
            # Root: list available shows for current date
            coordinator = self.coordinator
            shows = coordinator.available_shows
            children = [
                BrowseMedia(
                    title=f"{show.display_date} - {show.location}",
                    media_class="music",
                    media_content_id=show.identifier,
                    media_content_type=MediaType.MUSIC,
                    can_play=True,
                    can_expand=False,
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

        # Show tracks for a specific identifier
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

    async def _send_to_target_player(self) -> None:
        """Send current track URL to the configured target media player."""
        track = self.coordinator.current_track
        if not track:
            return

        target = self.coordinator.target_player
        if not target:
            _LOGGER.warning(
                "No target player configured. Set one in Deadstream options."
            )
            return

        if not self.hass.states.get(target):
            _LOGGER.warning("Target player %s not found", target)
            return

        _LOGGER.debug("Sending %s to %s", track.url, target)
        await self.hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": target,
                "media_content_id": track.url,
                "media_content_type": MediaType.MUSIC,
            },
        )
