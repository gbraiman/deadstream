"""Archive.org API client for Deadstream."""
from __future__ import annotations

import asyncio
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
    """Represents a single audio track."""

    name: str
    title: str
    url: str
    duration: float = 0.0
    track_num: int = 0
    format: str = ""


@dataclass
class Show:
    """Represents a concert recording (tape)."""

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
        """Return formatted date string."""
        try:
            d = date.fromisoformat(self.date[:10])
            return d.strftime("%B %-d, %Y")
        except (ValueError, AttributeError):
            return self.date

    @property
    def location(self) -> str:
        """Return venue and city string."""
        parts = [p for p in [self.venue, self.coverage] if p]
        return ", ".join(parts)


class ArchiveClient:
    """Async client for the archive.org API."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the client."""
        self._session = session
        self._shows_cache: dict[str, list[Show]] = {}  # keyed by "YYYY-MM-DD"
        self._metadata_cache: dict[str, list[Track]] = {}
        self._available_dates_cache: dict[str, list[str]] | None = None

    async def search_shows(
        self,
        collections: list[str],
        year: int | None = None,
        month: int | None = None,
        day: int | None = None,
        favored_taper: str = "",
    ) -> list[Show]:
        """Search archive.org for shows matching the given criteria."""
        query_parts = [
            f"collection:({' OR '.join(collections)})",
            "mediatype:etree",
        ]
        if year:
            if month:
                if day:
                    date_str = f"{year:04d}-{month:02d}-{day:02d}"
                    query_parts.append(f'date:"{date_str}"')
                else:
                    query_parts.append(f"date:[{year:04d}-{month:02d}-01 TO {year:04d}-{month:02d}-31]")
            else:
                query_parts.append(f"date:[{year:04d}-01-01 TO {year:04d}-12-31]")

        query = " AND ".join(query_parts)

        params = {
            "q": query,
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

        items = data.get("items", [])
        shows = []
        for item in items:
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

        # Sort favored taper to top
        if favored_taper:
            shows.sort(key=lambda s: 0 if favored_taper.lower() in s.taper.lower() else 1)

        return shows

    async def get_show_tracks(self, identifier: str, play_lossless: bool = False) -> list[Track]:
        """Fetch and return tracks for a show identifier."""
        if identifier in self._metadata_cache:
            return self._metadata_cache[identifier]

        url = ARCHIVE_METADATA_URL.format(identifier)
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                data = await resp.json()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error fetching metadata for %s: %s", identifier, err)
            return []

        files = data.get("files", [])
        preferred_formats = LOSSLESS_FORMATS + LOSSY_FORMATS if play_lossless else LOSSY_FORMATS + LOSSLESS_FORMATS

        # Group audio files by track name (without extension)
        audio_by_stem: dict[str, dict[str, Any]] = {}
        for f in files:
            fmt = f.get("format", "")
            if fmt not in preferred_formats:
                continue
            name = f.get("name", "")
            stem = re.sub(r"\.[^.]+$", "", name)
            if stem not in audio_by_stem:
                audio_by_stem[stem] = {}
            audio_by_stem[stem][fmt] = f

        tracks = []
        track_num = 1
        for stem, formats in sorted(audio_by_stem.items()):
            # Pick best available format
            chosen_file = None
            for fmt in preferred_formats:
                if fmt in formats:
                    chosen_file = formats[fmt]
                    break
            if not chosen_file:
                continue

            name = chosen_file.get("name", "")
            title = chosen_file.get("title", "") or stem
            fmt = chosen_file.get("format", "")

            try:
                duration = float(chosen_file.get("length", 0))
            except (ValueError, TypeError):
                duration = 0.0

            url = ARCHIVE_DOWNLOAD_URL.format(identifier, name)
            tracks.append(Track(
                name=name,
                title=title,
                url=url,
                duration=duration,
                track_num=track_num,
                format=fmt,
            ))
            track_num += 1

        self._metadata_cache[identifier] = tracks
        return tracks

    async def get_available_years(self, collections: list[str]) -> list[int]:
        """Return list of years that have shows."""
        # GratefulDead ran 1965-1995; expand for other collections
        return list(range(1965, 1996))

    async def get_available_dates_for_year_month(
        self,
        collections: list[str],
        year: int,
        month: int,
    ) -> list[int]:
        """Return list of days in a given month that have shows."""
        shows = await self.search_shows(collections, year=year, month=month)
        days = set()
        for show in shows:
            try:
                d = date.fromisoformat(show.date[:10])
                days.add(d.day)
            except (ValueError, AttributeError):
                pass
        return sorted(days)

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._shows_cache.clear()
        self._metadata_cache.clear()
        self._available_dates_cache = None
