"""Validated Liiga records. No invented results and no silent missing-goal = 0."""
from __future__ import annotations

import calendar
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

UTC = timezone.utc
REGULAR = "runkosarja"


class DataError(ValueError):
    """A source is unavailable, incomplete or has an unsupported format."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise DataError("Ottelulta puuttuu kelvollinen alkamisaika.")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataError("Ottelun aikaleiman muotoa ei tunnistettu.") from exc
    if result.tzinfo is None:
        raise DataError("Ottelun aikaleimasta puuttuu aikavyöhyke.")
    return result.astimezone(UTC)


def helsinki(value: datetime) -> datetime:
    """Use the OS timezone database, or EU DST rules on Windows without tzdata.

    Fallback is restricted to 2000–2100 and uses last Sundays of March/October,
    with transitions at 01:00 UTC. No downloads or pip installation are required.
    """
    if value.tzinfo is None:
        raise ValueError("An aware datetime is required")
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            return value.astimezone(ZoneInfo("Europe/Helsinki"))
        except ZoneInfoNotFoundError:
            pass
    except ImportError:
        pass
    value = value.astimezone(UTC)
    if not 2000 <= value.year <= 2100:
        raise DataError("Ilman aikavyöhyketietokantaa tuetaan vuosia 2000–2100.")
    boundaries = []
    for month in (3, 10):
        last = date(value.year, month, calendar.monthrange(value.year, month)[1])
        sunday = last - timedelta(days=(last.weekday() + 1) % 7)
        boundaries.append(datetime(sunday.year, month, sunday.day, 1, tzinfo=UTC))
    hours = 3 if boundaries[0] <= value < boundaries[1] else 2
    return value.astimezone(timezone(timedelta(hours=hours)))


def day_start_utc(day: date) -> datetime:
    naive = datetime.combine(day, datetime.min.time())
    for hours in (2, 3):
        candidate = (naive - timedelta(hours=hours)).replace(tzinfo=UTC)
        if helsinki(candidate).replace(tzinfo=None) == naive:
            return candidate
    raise DataError("Suomen päivän alkua ei pystytty laskemaan.")


def season_for(day: date) -> int:
    # Liiga season identifiers use the ending year. July starts the next season.
    return day.year + (1 if day.month >= 7 else 0)


def season_label(season: int) -> str:
    return f"{season - 1}–{str(season)[-2:]}"


def team_key(name: str) -> str:
    key = unicodedata.normalize("NFC", name).strip().casefold()
    aliases = {"hifk helsinki": "hifk", "ifk": "hifk", "k-espoo": "kiekko-espoo"}
    return aliases.get(key, key)


def checked_int(value: Any, label: str, maximum: int = 100000000) -> int:
    if isinstance(value, bool) or value is None:
        raise DataError(f"Virheellinen {label}.")
    if isinstance(value, float) and not value.is_integer():
        raise DataError(f"Virheellinen {label}.")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise DataError(f"Virheellinen {label}.") from exc
    if number < 0 or number > maximum:
        raise DataError(f"Virheellinen {label}.")
    return number


def as_bool(value: Any) -> bool:
    return value is True or value == 1 or (isinstance(value, str) and value.lower() == "true")


@dataclass(frozen=True)
class Game:
    id: str
    season: int
    start: datetime
    home: str
    away: str
    home_key: str
    away_key: str
    started: bool
    ended: bool
    home_goals: int | None
    away_goals: int | None
    home_60: int | None
    away_60: int | None
    finish: str
    regulation_method: str
    tournament: str = REGULAR
    data_url: str = ""

    @property
    def key(self) -> str:
        return f"{self.season}-{self.id}"

    @property
    def day(self) -> date:
        return helsinki(self.start).date()

    @property
    def usable(self) -> bool:
        return self.ended and self.home_60 is not None and self.away_60 is not None

    def public(self) -> dict:
        return {
            "key": self.key, "id": self.id, "season": self.season,
            "season_label": season_label(self.season), "date": self.day.isoformat(),
            "start": self.start.isoformat(), "time": helsinki(self.start).strftime("%H:%M"),
            "home": self.home, "away": self.away,
            "home_key": self.home_key, "away_key": self.away_key,
            "started": self.started, "ended": self.ended,
            "home_goals": self.home_goals, "away_goals": self.away_goals,
            "home_60": self.home_60, "away_60": self.away_60,
            "finish": self.finish, "regulation_method": self.regulation_method,
            "tournament": self.tournament, "data_url": self.data_url,
            "url": f"https://liiga.fi/fi/ottelu/{self.season}/{self.id}/tilastot",
        }


def game_records(payload: Any, depth: int = 0) -> list[dict]:
    """Find embedded game records in list, {games: [...]}, or dated schedules.

    Fail closed elsewhere; no text scraping and no guessing scores from strings.
    """
    if depth > 8:
        raise DataError("Otteluvastauksen sisäkkäisyys ylittää sallitun rajan.")
    if isinstance(payload, list):
        result = []
        for item in payload:
            result.extend(game_records(item, depth + 1))
        return result
    if not isinstance(payload, dict):
        return []
    if "homeTeam" in payload and "awayTeam" in payload:
        return [payload]
    result = []
    for value in payload.values():
        if isinstance(value, (list, dict)):
            result.extend(game_records(value, depth + 1))
    return result


def parse_game(record: dict, expected_season: int, source_url: str = "") -> Game | None:
    """Return None for explicitly different competitions/seasons, not for bad data."""
    serie = record.get("serie") or record.get("tournament") or REGULAR
    if isinstance(serie, dict):
        serie = serie.get("name") or serie.get("id") or "unknown"
    serie = str(serie).lower()
    if serie not in {REGULAR, "regular", "regular_season", "regular season"}:
        return None
    season = checked_int(record.get("season", expected_season), "kausi", 2101)
    if season != expected_season:
        return None
    start = parse_datetime(record.get("start"))
    if season_for(helsinki(start).date()) != expected_season:
        raise DataError("Ottelun päivä ja kausitunniste ovat ristiriidassa.")
    gid = str(checked_int(record.get("id"), "ottelutunniste"))
    sides = []
    for side in ("homeTeam", "awayTeam"):
        data = record.get(side)
        if not isinstance(data, dict):
            raise DataError("Joukkuetiedot puuttuvat.")
        name = data.get("teamName") or data.get("name")
        if not name:
            tid = data.get("teamId")
            if isinstance(tid, str) and ":" in tid:
                name = tid.split(":", 1)[1]
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise DataError("Joukkueen nimi puuttuu tai on virheellinen.")
        goals = data.get("goals")
        sides.append((name.strip(), checked_int(goals, "maalimäärä", 40) if goals is not None else None))
    home, hg = sides[0]
    away, ag = sides[1]
    if team_key(home) == team_key(away):
        raise DataError("Ottelulla ei voi olla samaa koti- ja vierasjoukkuetta.")
    ended = as_bool(record.get("ended"))
    started = as_bool(record.get("started")) or ended
    finish = str(record.get("finishedType") or "").upper()
    raw_time = record.get("gameTime")
    game_time = checked_int(raw_time, "peliaika", 50000) if raw_time is not None else None
    rh = ra = None
    method = "Ei päättynyt / ei varmennettua 60 minuutin tulosta"
    cancelled = any(token in finish for token in ("CANCEL", "POSTPON", "ABANDON", "FORFEIT"))
    if ended and hg is not None and ag is not None and not cancelled:
        is_regular = finish in {"ENDED_DURING_REGULAR_GAME_TIME", "REGULAR", "REGULATION"}
        is_extra = any(token in finish for token in ("OVERTIME", "SHOOTOUT", "WINNING_SHOT", "PENALTY_SHOT"))
        # Unknown explicit result types are never guessed. Time is a fallback only
        # when the provider supplies no result type at all.
        if not finish and game_time is not None:
            is_regular = game_time == 3600
            is_extra = game_time > 3600
        if is_regular and hg != ag:
            rh, ra = hg, ag
            method = "Varsinaisen peliajan lopputulos"
        elif is_extra and abs(hg - ag) == 1:
            rh = ra = min(hg, ag)
            method = "JA/VL: ratkaisumaali poistettu voittajalta"
    return Game(gid, season, start, home, away, team_key(home), team_key(away),
                started, ended, hg, ag, rh, ra, finish, method, REGULAR, source_url)


def parse_games(payload: Any, season: int, source_url: str = "") -> tuple[list[Game], list[str]]:
    if not isinstance(payload, (list, dict)):
        raise DataError("Palvelin ei palauttanut JSON-ottelulistaa.")
    records = game_records(payload)
    if not records:
        explicit_empty = payload == [] or (isinstance(payload, dict) and payload.get("games") == [])
        if not explicit_empty:
            raise DataError("Liigan JSON-rakennetta ei tunnistettu. Tilastoja ei arvata.")
    games = {}
    rejected = []
    for record in records:
        try:
            game = parse_game(record, season, source_url)
        except DataError as exc:
            rejected.append(f"Ottelu {record.get('id', '?')}: {exc}")
            continue
        if game is not None:
            old = games.get(game.key)
            if old is not None and old != game:
                raise DataError(f"Lähde palautti ristiriitaiset tiedot ottelulle {game.key}.")
            games[game.key] = game
    if records and not games and rejected:
        raise DataError("Yhtään ottelua ei voitu lukea: " + rejected[0])
    return sorted(games.values(), key=lambda g: (g.start, g.key)), rejected
