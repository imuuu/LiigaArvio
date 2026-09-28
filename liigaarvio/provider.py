"""Liiga JSON adapter with bounded requests, validated cache and provenance.

Primary data: https://liiga.fi/api/v2/games
The date endpoint is also used to recover a full history when a season endpoint
returns only a day. There is no Google scraping, third-party odds feed or API key.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .domain import (DataError, Game, REGULAR, day_start_utc, game_records, helsinki,
                     parse_datetime, parse_games, season_for, utc_now)

ALLOWED_HOSTS = {"liiga.fi", "www.liiga.fi"}
MAX_BYTES = 16 * 1024 * 1024


class SourceUnavailable(DataError):
    pass


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        if target.scheme != "https" or target.hostname not in ALLOWED_HOSTS:
            raise SourceUnavailable("Lähde ohjasi pois sallitusta Liiga-osoitteesta.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass
class Fetch:
    data: Any
    url: str
    fetched_at: str
    cached: bool = False
    stale: bool = False
    error: str = ""

    def public(self) -> dict:
        return {"url": self.url, "fetched_at": self.fetched_at,
                "cached": self.cached, "stale": self.stale, "error": self.error}


@dataclass
class Dataset:
    games: list[Game]
    sources: list[dict]
    warnings: list[str]


def default_cache_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "LiigaArvio" / "cache"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "liigaarvio"


def _unique_sources(sources: list[dict]) -> list[dict]:
    by_url = {}
    for source in sources:
        by_url[source["url"]] = source
    return list(by_url.values())


class JsonClient:
    def __init__(self, cache_dir: Path | None = None, timeout: float = 12.0):
        self.cache_dir = cache_dir or default_cache_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self._semaphore = threading.BoundedSemaphore(3)
        self.last_activity = "Valmis"

    def _lock_for(self, key: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def _network(self, url: str) -> Any:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            raise SourceUnavailable("Vain Liigan HTTPS-osoitteet on sallittu.")
        opener = urllib.request.build_opener(
            SafeRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        request = urllib.request.Request(url, headers={
            "User-Agent": "LiigaArvio/1.0 (local personal statistics viewer)",
            "Accept": "application/json", "Accept-Encoding": "identity",
        })
        for attempt in range(2):
            try:
                with self._semaphore:
                    self.last_activity = "Haetaan " + parsed.path
                    with opener.open(request, timeout=self.timeout) as response:
                        body = response.read(MAX_BYTES + 1)
                        if len(body) > MAX_BYTES:
                            raise SourceUnavailable("Lähdevastaus ylitti 16 megatavun rajan.")
                        try:
                            payload = json.loads(body.decode("utf-8-sig"))
                        except (UnicodeError, json.JSONDecodeError) as exc:
                            raise SourceUnavailable("Lähde palautti muuta kuin JSON-dataa (esimerkiksi HTML-estosivun).") from exc
                        # Do not overwrite good cached data with a JSON error page.
                        if not game_records(payload) and payload != [] and not (
                            isinstance(payload, dict) and payload.get("games") == []
                        ):
                            raise SourceUnavailable("Liigan vastausrakenne on muuttunut tai ottelutiedot puuttuvat.")
                        return payload
            except urllib.error.HTTPError as exc:
                if exc.code in {408, 429, 500, 502, 503, 504} and attempt == 0:
                    try:
                        delay = float(exc.headers.get("Retry-After", "1.5"))
                    except (TypeError, ValueError):
                        delay = 1.5
                    # Do not retry earlier than a long server-requested wait.
                    if delay > 15:
                        raise SourceUnavailable(f"Liiga rajoitti pyyntöjä (HTTP {exc.code}). Yritä myöhemmin.") from exc
                    time.sleep(max(1.0, delay))
                    continue
                raise SourceUnavailable(f"Liiga vastasi HTTP {exc.code}. Lähde voi olla tilapäisesti poissa tai estää yhteyden.") from exc
            except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
                reason = getattr(exc, "reason", exc)
                raise SourceUnavailable(f"Verkkoyhteys Liigaan epäonnistui: {reason}") from exc
        raise SourceUnavailable("Lähteen hakeminen epäonnistui.")

    def get(self, url: str, force: bool = False, ttl: int = 300) -> Fetch:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        path = self.cache_dir / f"{key}.json"
        with self._lock_for(key):
            saved = None
            try:
                candidate = json.loads(path.read_text(encoding="utf-8"))
                if candidate.get("url") == url and "data" in candidate:
                    parse_datetime(candidate["fetched_at"])
                    saved = candidate
            except (OSError, ValueError, KeyError, TypeError):
                pass
            if saved:
                age = (utc_now() - parse_datetime(saved["fetched_at"])).total_seconds()
                # Refresh button also has a small request throttle.
                if 0 <= age < (30 if force else ttl):
                    return Fetch(saved["data"], url, saved["fetched_at"], cached=True)
            try:
                data = self._network(url)
                stamp = utc_now().isoformat()
                cache = {"url": url, "fetched_at": stamp, "data": data}
                try:
                    temp = path.with_suffix(".tmp")
                    temp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                    temp.replace(path)
                except OSError:
                    # The app can still work without persistent caching.
                    pass
                self.last_activity = "Valmis"
                return Fetch(data, url, stamp)
            except SourceUnavailable as exc:
                self.last_activity = str(exc)
                if saved:
                    return Fetch(saved["data"], url, saved["fetched_at"], cached=True,
                                 stale=True, error=str(exc))
                raise


class LiigaProvider:
    demo = False

    def __init__(self, client: JsonClient | None = None):
        self.client = client or JsonClient()
        self._seasons: dict[tuple[int, date], tuple[float, Dataset]] = {}
        self._season_lock = threading.RLock()

    @staticmethod
    def _url(path: str, **params) -> str:
        return "https://liiga.fi/api/" + path + "?" + urllib.parse.urlencode(params)

    def day(self, day: date, force: bool = False) -> dict:
        url = self._url("v2/games", tournament=REGULAR, date=day.isoformat())
        response = self.client.get(url, force=force)
        games, warnings = parse_games(response.data, season_for(day), url)
        matching = [g for g in games if g.day == day]
        if games and not matching:
            raise DataError("Lähde ei palauttanut pyydetyn päivän pelejä. Väärän päivän tietoja ei näytetä.")
        data = response.data if isinstance(response.data, dict) else {}
        navigation = {}
        for key, direction in (("previousGameDate", -1), ("nextGameDate", 1)):
            try:
                value = date.fromisoformat(str(data.get(key, ""))[:10])
                if (value - day).days * direction > 0:
                    navigation[key] = value.isoformat()
            except ValueError:
                pass
        if warnings:
            warnings.insert(0, "Kaikkia lähteen otteluita ei pystytty lukemaan. Päivän lista voi olla puutteellinen.")
        if response.stale:
            warnings.insert(0, "Verkkohaku epäonnistui. Näytetään aiemmin haettu otteluohjelma; se voi olla vanhentunut.")
        return {"date": day.isoformat(), "games": [g.public() for g in matching],
                "sources": [response.public()], "warnings": warnings,
                "navigation": navigation, "demo": False,
                "today": helsinki(utc_now()).date().isoformat()}

    def season(self, season: int, through: date, force: bool = False) -> Dataset:
        through = min(through, date(season, 6, 30))
        key = (season, through)
        with self._season_lock:
            cached = self._seasons.get(key)
            if cached and time.monotonic() - cached[0] < (30 if force else 300):
                ds = cached[1]
                return Dataset(ds.games, [{**s, "cached": True} for s in ds.sources], ds.warnings)
            ds = self._load_season(season, through, force)
            self._seasons[key] = (time.monotonic(), ds)
            return ds

    def _load_season(self, season: int, through: date, force: bool) -> Dataset:
        errors = []
        # API versions can vary: v2/games may return a whole season or a single day.
        for path in ("v2/games", "v2/schedule", "v1/games"):
            url = self._url(path, tournament=REGULAR, season=season)
            try:
                response = self.client.get(url, force=force, ttl=3600 if season < season_for(helsinki(utc_now()).date()) else 300)
                if isinstance(response.data, dict) and any(
                    key in response.data for key in ("previousGameDate", "nextGameDate")
                ):
                    # Never mistake a day-limited response for the full season.
                    errors.append(f"{path}: päiväkohtainen vastaus, ei koko kausi")
                    continue
                games, warnings = parse_games(response.data, season, url)
                if game_records(response.data) and not games:
                    raise DataError("Lähde ei palauttanut pyydettyä kautta/runkosarjaa.")
                if not games:
                    # A genuinely empty season is useful for offseason/new-season views.
                    return Dataset([], [response.public()], warnings)
                sources = [response.public()]
                # Some schedule endpoints return fixtures without up-to-date scores.
                # Refresh old undecided game days using the known day endpoint.
                old_limit = utc_now() - timedelta(hours=6)
                missing_days = sorted({g.day for g in games if g.day <= through and g.start < old_limit
                                       and (not g.ended or g.home_goals is None or g.away_goals is None)})
                if len(missing_days) > 180:
                    raise DataError("Lähteessä on liikaa puuttuvia tulospäiviä.")
                by_key = {g.key: g for g in games}
                for missing_day in missing_days:
                    self.client.last_activity = f"Täydennetään tuloksia: {missing_day.isoformat()}"
                    day_url = self._url("v2/games", tournament=REGULAR, date=missing_day.isoformat())
                    update = self.client.get(day_url, force=force, ttl=86400 if missing_day < helsinki(utc_now()).date() - timedelta(days=2) else 300)
                    updated_games, problems = parse_games(update.data, season, day_url)
                    if any(g.day != missing_day for g in updated_games):
                        raise DataError("Tulosten täydennys palautti väärän päivän.")
                    by_key.update({g.key: g for g in updated_games})
                    sources.append(update.public())
                    warnings.extend(problems)
                result = Dataset(sorted(by_key.values(), key=lambda g: g.start), _unique_sources(sources), warnings)
                if any(s["stale"] for s in result.sources):
                    result.warnings.insert(0, "Osa kauden aineistosta on vanhasta välimuistista; viimeisin haku epäonnistui.")
                return result
            except (DataError, SourceUnavailable) as exc:
                errors.append(f"{path}: {exc}")
        # Bounded recovery: walk the API's previous game-date chain. Every day's
        # response is cached; an interrupted chain is never called complete.
        try:
            return self._walk_history(season, through, force)
        except DataError as exc:
            raise SourceUnavailable("Kauden otteluhistoriaa ei saatu kokonaisena. " +
                                    " | ".join(errors[:3]) + f" | Päivähistoria: {exc}") from exc

    def _walk_history(self, season: int, through: date, force: bool) -> Dataset:
        lower = date(season - 1, 7, 1)
        current = through
        games = {}
        sources, warnings = [], []
        seen = set()
        for step in range(190):
            if current < lower:
                return Dataset(sorted(games.values(), key=lambda g: g.start), _unique_sources(sources), warnings)
            if current in seen:
                raise DataError("Lähteen päivähistoria jäi silmukkaan.")
            seen.add(current)
            self.client.last_activity = f"Haetaan historiaa: {step + 1} ottelupäivää"
            url = self._url("v2/games", tournament=REGULAR, date=current.isoformat())
            response = self.client.get(url, force=force, ttl=86400 if current < helsinki(utc_now()).date() - timedelta(days=2) else 300)
            if not isinstance(response.data, dict) or "previousGameDate" not in response.data:
                raise DataError("Lähteeltä puuttuu aiempien ottelupäivien ketju.")
            rows, rejected = parse_games(response.data, season, url)
            if any(g.day != current for g in rows):
                raise DataError("Päivähistoria palautti väärän päivän otteluita.")
            games.update({g.key: g for g in rows})
            sources.append(response.public())
            warnings.extend(rejected)
            prev = response.data.get("previousGameDate")
            if not prev:
                if any(s["stale"] for s in sources):
                    warnings.insert(0, "Osa historiasta tulee vanhentuneesta välimuistista.")
                return Dataset(sorted(games.values(), key=lambda g: g.start), _unique_sources(sources), warnings)
            try:
                prior_day = date.fromisoformat(str(prev)[:10])
            except ValueError as exc:
                raise DataError("Virheellinen edellisen ottelupäivän arvo.") from exc
            if prior_day >= current:
                # Off-season API may wrap into the future. Do not call it complete.
                raise DataError("Lähteen historiaketju kääntyi tulevaisuuteen.")
            current = prior_day
        raise DataError("Ottelupäivien turvallinen enimmäismäärä ylittyi.")
