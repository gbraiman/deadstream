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
    MAX_SHOWS_PER_SEARCH,
)

_LOGGER = logging.getLogger(__name__)

SEARCH_FIELDS = ["identifier", "date", "title", "venue", "coverage", "taper", "collection"]
TAPER_SEARCH_FIELDS = [*SEARCH_FIELDS, "downloads"]
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
    downloads: int = 0
    tracks: list[Track] = field(default_factory=list)

    @property
    def display_date(self) -> str:
        try:
            d = date.fromisoformat(self.date[:10])
            return d.strftime("%B %-d, %Y")
        except (ValueError, AttributeError):
            return self.date

    @property
    def year(self) -> int | None:
        try:
            return date.fromisoformat(self.date[:10]).year
        except (ValueError, AttributeError):
            return None

    @property
    def location(self) -> str:
        parts = [p for p in [self.venue, self.coverage] if p]
        return ", ".join(parts)

    @property
    def taper_label(self) -> str:
        """Human-readable label for taper select."""
        label = self.taper or self.identifier
        if self.downloads:
            dl = f"{self.downloads:,}"
            return f"{label} ({dl} plays)"
        return label


class ArchiveClient:
    """Async client for the archive.org API."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._metadata_cache: dict[str, list[Track]] = {}

    # ------------------------------------------------------------------
    # Cross-year search: one representative show per (date, collection)
    # ------------------------------------------------------------------
    async def search_today_in_history(
        self,
        collections: list[str],
        month: int,
        day: int,
        favored_taper: str = "",
    ) -> list[Show]:
        """Return one show per (year, collection) that has a recording on month/day.

        Queries each collection separately so every result is definitively tagged
        with the correct band — avoids OR-query attribution ambiguity in Solr.
        Deduplicates by (date, collection) so multi-band dates each get their own
        entry in the Show selector.
        """
        by_key: dict[tuple[str, str], Show] = {}
        for collection in collections:
            shows = await self._search_collection_on_date(
                collection, month, day, favored_taper
            )
            for show in shows:
                key = (show.date[:10], show.collection)
                if key not in by_key:
                    by_key[key] = show
                elif favored_taper and favored_taper.lower() in show.taper.lower():
                    by_key[key] = show
        return sorted(by_key.values(), key=lambda s: s.date[:10])

    async def _search_collection_on_date(
        self,
        collection: str,
        month: int,
        day: int,
        favored_taper: str = "",
    ) -> list[Show]:
        """Fetch all recordings in one collection for a given month/day across all years."""
        current_year = date.today().year
        date_clauses = " OR ".join(
            f'date:"{y:04d}-{month:02d}-{day:02d}"'
            for y in range(1965, current_year + 1)
        )
        query = f"collection:{collection} AND mediatype:(etree OR audio) AND ({date_clauses})"
        params = {
            "q": query,
            "fields": ",".join(SEARCH_FIELDS),
            "sorts": "date asc",
            "count": "500",
        }
        _LOGGER.debug("archive search [%s %02d/%02d]: %s", collection, month, day, query)
        items = await self._fetch_items(params)

        # If nothing came back, retry without the mediatype filter — some collections
        # (e.g. newer bands) may use a mediatype not covered by etree/audio.
        if not items:
            fallback_query = f"collection:{collection} AND ({date_clauses})"
            _LOGGER.debug(
                "archive search [%s %02d/%02d]: no results with mediatype filter, retrying without",
                collection, month, day,
            )
            items = await self._fetch_items({**params, "q": fallback_query})

        shows = self._parse_items(items, [collection], favored_taper)
        _LOGGER.info("archive search [%s %02d/%02d]: %d raw items → %d shows", collection, month, day, len(items), len(shows))
        return shows

    # ------------------------------------------------------------------
    # Per-date taper search: all recordings for one specific date
    # ------------------------------------------------------------------
    async def search_tapers_for_date(
        self,
        collections: list[str],
        year: int,
        month: int,
        day: int,
        favored_taper: str = "",
    ) -> list[Show]:
        """Return every recording of a specific date, sorted best-first.

        'Best' = most archive.org downloads (proxy for quality/popularity).
        The favored taper, if set, is always moved to position 0.
        """
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        query = (
            f"collection:({' OR '.join(collections)}) AND mediatype:(etree OR audio)"
            f' AND date:"{date_str}"'
        )
        params = {
            "q": query,
            "fields": ",".join(TAPER_SEARCH_FIELDS),
            "sorts": "downloads desc",
            "count": "50",
        }

        _LOGGER.debug("taper search [%s %04d-%02d-%02d]: %s", collections, year, month, day, query)
        items = await self._fetch_items(params)

        if not items:
            fallback_query = (
                f"collection:({' OR '.join(collections)})"
                f' AND date:"{date_str}"'
            )
            _LOGGER.debug(
                "taper search [%04d-%02d-%02d]: no results with mediatype filter, retrying without",
                year, month, day,
            )
            items = await self._fetch_items({**params, "q": fallback_query})

        shows = self._parse_items(items, collections, favored_taper, include_downloads=True)

        # Deduplicate by identifier
        seen: set[str] = set()
        result: list[Show] = []
        for s in shows:
            if s.identifier not in seen:
                seen.add(s.identifier)
                result.append(s)
        _LOGGER.info("taper search [%04d-%02d-%02d]: %d tapers found", year, month, day, len(result))
        return result

    # ------------------------------------------------------------------
    # Legacy search (used by random show)
    # ------------------------------------------------------------------
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
            "mediatype:(etree OR audio)",
        ]
        if year:
            if month:
                if day:
                    query_parts.append(f'date:"{year:04d}-{month:02d}-{day:02d}"')
                else:
                    query_parts.append(
                        f"date:[{year:04d}-{month:02d}-01 TO {year:04d}-{month:02d}-31]"
                    )
            else:
                query_parts.append(f"date:[{year:04d}-01-01 TO {year:04d}-12-31]")

        params = {
            "q": " AND ".join(query_parts),
            "fields": ",".join(SEARCH_FIELDS),
            "sorts": ",".join(SEARCH_SORTS),
            "count": str(MAX_SHOWS_PER_SEARCH * 4),
        }

        items = await self._fetch_items(params)
        shows = self._parse_items(items, collections, favored_taper)

        seen: set[str] = set()
        deduped: list[Show] = []
        for s in shows:
            if s.identifier not in seen:
                seen.add(s.identifier)
                deduped.append(s)
        return deduped[:MAX_SHOWS_PER_SEARCH]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _fetch_items(self, params: dict) -> list[dict]:
        try:
            async with self._session.get(
                ARCHIVE_SEARCH_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error searching archive.org: %s", err)
            return []
        return data.get("items", [])

    def _parse_items(
        self,
        items: list[dict],
        collections: list[str],
        favored_taper: str,
        include_downloads: bool = False,
    ) -> list[Show]:
        shows: list[Show] = []
        collection_lookup = {c.lower(): c for c in collections}

        def _first_text(value: Any) -> str:
            if isinstance(value, list):
                value = value[0] if value else ""
            return str(value or "")

        for item in items:
            identifier = _first_text(item.get("identifier", ""))
            if not identifier:
                continue
            downloads = 0
            if include_downloads:
                try:
                    downloads = int(item.get("downloads", 0))
                except (ValueError, TypeError):
                    downloads = 0
            # The archive.org "collection" field is a list of every collection the
            # item belongs to (e.g. ["GratefulDead", "etree", "audio"]).  Pick the
            # first element that matches one of our configured collections; fall back
            # to collections[0] if none match (shouldn't happen but keeps us safe).
            raw_coll = item.get("collection", [])
            if isinstance(raw_coll, list):
                collection = next(
                    (
                        collection_lookup.get(str(c).lower(), "")
                        for c in raw_coll
                        if str(c).lower() in collection_lookup
                    ),
                    collections[0],
                )
            else:
                collection = collection_lookup.get(str(raw_coll).lower(), collections[0])

            taper = _first_text(item.get("taper", ""))

            shows.append(Show(
                identifier=identifier,
                date=_first_text(item.get("date", "")),
                title=_first_text(item.get("title", "Unknown Show")) or "Unknown Show",
                venue=_first_text(item.get("venue", "")),
                coverage=_first_text(item.get("coverage", "")),
                taper=taper,
                collection=collection,
                downloads=downloads,
            ))

        if favored_taper:
            shows.sort(key=lambda s: 0 if favored_taper.lower() in s.taper.lower() else 1)

        return shows

    # ------------------------------------------------------------------
    # Track metadata
    # ------------------------------------------------------------------
    async def get_show_tracks(self, identifier: str, play_lossless: bool = False) -> list[Track]:
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
        preferred = LOSSLESS_FORMATS + LOSSY_FORMATS if play_lossless else LOSSY_FORMATS + LOSSLESS_FORMATS

        audio_by_stem: dict[str, dict[str, Any]] = {}
        for f in files:
            fmt = f.get("format", "")
            if fmt not in preferred:
                continue
            name = f.get("name", "")
            stem = re.sub(r"\.[^.]+$", "", name)
            audio_by_stem.setdefault(stem, {})[fmt] = f

        tracks: list[Track] = []
        for track_num, (stem, formats) in enumerate(sorted(audio_by_stem.items()), start=1):
            chosen = next((formats[f] for f in preferred if f in formats), None)
            if not chosen:
                continue
            name = chosen.get("name", "")
            try:
                duration = float(chosen.get("length", 0))
            except (ValueError, TypeError):
                duration = 0.0
            tracks.append(Track(
                name=name,
                title=chosen.get("title", "") or stem,
                url=ARCHIVE_DOWNLOAD_URL.format(identifier, name),
                duration=duration,
                track_num=track_num,
                format=chosen.get("format", ""),
            ))

        self._metadata_cache[identifier] = tracks
        return tracks

    def clear_cache(self) -> None:
        self._metadata_cache.clear()
