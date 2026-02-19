"""Archive.org API client for Deadstream."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import aiohttp

from .const import (
    ARCHIVE_DOWNLOAD_URL,
    ARCHIVE_METADATA_URL,
    ARCHIVE_SEARCH_URL,
    LOSSLESS_FORMATS,
    LOSSY_FORMATS,
)

_LOGGER = logging.getLogger(__name__)

SEARCH_FIELDS = ["identifier", "date", "title", "venue", "coverage", "subject", "taper"]
SEARCH_SORTS = ["date asc"]


@dataclass
class Track:
    name: str
    title: str
    url: str
    duration: float = 0.0
    track_num: int = 0
    format: str = ""


@dataclass
class Show:
    identifier: str
    date: str
    title: str
    venue: str
    coverage: str
    taper: str
    collection: str
    tracks: list[Track] = field(default_factory=list)

    @property
    def display_date(self) -> str:
        try:
            d = date.fromisoformat(self.date[:10])
            return d.strftime("%B %-d, %Y")
        except (ValueError, AttributeError):
            return self.date

    @property
    def location(self) -> str:
        parts = [p for p in [self.venue, self.coverage] if p]
        return ", ".join(parts)


class ArchiveClient:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._shows_cache: dict[str, list[Show]] = {}
        self._metadata_cache: dict[str, list[Track]] = {}

    async def search_shows(
        self,
        collections: list[str],
        year: int | None = None,
        month: int | None = None,
        day: int | None = None,
        favored_taper: str = "",
    ) -> list[Show]:
        query_parts = [
            f"collection:({' OR '.join(collections)})",
            "mediatype:etree",
        ]
        if year:
            if month:
                if day:
                    query_parts.append(f'date:"{year:04d}-{month:02d}-{day:02d}"')
                else:
                    query_parts.append(f"date:[{year:04d}-{month:02d}-01 TO {year:04d}-{month:02d}-31]")
            else:
                query_parts.append(f"date:[{year:04d}-01-01 TO {year:04d}-12-31]")

        params = {
            "q": " AND ".join(query_parts),
            "fields": ",".join(SEARCH_FIELDS),
            "sorts": ",".join(SEARCH_SORTS),
            "count": "100",
        }

        try:
            async with self._session.get(ARCHIVE_SEARCH_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                data = await resp.json()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error searching archive.org: %s", err)
            return []

        shows = []
        for item in data.get("items", []):
            show = Show(
                identifier=item.get("identifier", ""),
                date=item.get("date", ""),
                title=item.get("title", "Unknown Show"),
                venue=item.get("venue", ""),
                coverage=item.get("coverage", ""),
                taper=item.get("taper", ""),
                collection=item.get("subject", collections[0]),
            )
            if show.identifier:
                shows.append(show)

        if favored_taper:
            shows.sort(key=lambda s: 0 if favored_taper.lower() in s.taper.lower() else 1)

        return shows

    async def get_show_tracks(self, identifier: str, play_lossless: bool = False) -> list[Track]:
        if identifier in self._metadata_cache:
            return self._metadata_cache[identifier]

        try:
            async with self._session.get(ARCHIVE_METADATA_URL.format(identifier), timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                data = await resp.json()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error fetching metadata for %s: %s", identifier, err)
            return []

        preferred_formats = LOSSLESS_FORMATS + LOSSY_FORMATS if play_lossless else LOSSY_FORMATS + LOSSLESS_FORMATS
        audio_by_stem: dict[str, dict[str, Any]] = {}

        for f in data.get("files", []):
            fmt = f.get("format", "")
            if fmt not in preferred_formats:
                continue
            name = f.get("name", "")
            stem = re.sub(r"\.[^.]+$", "", name)
            audio_by_stem.setdefault(stem, {})[fmt] = f

        tracks = []
        for track_num, (stem, formats) in enumerate(sorted(audio_by_stem.items()), 1):
            chosen_file = next((formats[fmt] for fmt in preferred_formats if fmt in formats), None)
            if not chosen_file:
                continue
            name = chosen_file.get("name", "")
            try:
                duration = float(chosen_file.get("length", 0))
            except (ValueError, TypeError):
                duration = 0.0
            tracks.append(Track(
                name=name,
                title=chosen_file.get("title", "") or stem,
                url=ARCHIVE_DOWNLOAD_URL.format(identifier, name),
                duration=duration,
                track_num=track_num,
                format=chosen_file.get("format", ""),
            ))

        self._metadata_cache[identifier] = tracks
        return tracks

    def clear_cache(self) -> None:
        self._shows_cache.clear()
        self._metadata_cache.clear()
