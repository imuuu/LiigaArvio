"""Application orchestration; live data and demonstration data remain separate."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from .domain import DataError, Game, day_start_utc, helsinki, parse_datetime, season_for, utc_now
from .model import backtest, predict
from .provider import Dataset, LiigaProvider, _unique_sources


def fixture_from_public(row: dict) -> Game:
    return Game(str(row["id"]), row["season"], parse_datetime(row["start"]),
                row["home"], row["away"], row["home_key"], row["away_key"],
                row["started"], row["ended"], row["home_goals"], row["away_goals"],
                row["home_60"], row["away_60"], row["finish"], row["regulation_method"],
                row["tournament"], row["data_url"])


class Service:
    def __init__(self, provider=None):
        self.provider = provider or LiigaProvider()

    def config(self) -> dict:
        return {"today": helsinki(utc_now()).date().isoformat(), "timezone": "Europe/Helsinki",
                "demo": self.provider.demo, "version": "1.0.0", "competition": "Liiga · runkosarja"}

    def day(self, day: date, force: bool = False) -> dict:
        return self.provider.day(day, force)

    def _datasets(self, season: int, through: date, force: bool) -> tuple[Dataset, Dataset]:
        # A missing previous season must not hide valid current-season data.
        # A missing CURRENT season must not silently produce a prior-only forecast.
        with ThreadPoolExecutor(max_workers=2) as pool:
            current_job = pool.submit(self.provider.season, season, through, force)
            prior_job = pool.submit(self.provider.season, season - 1, date(season - 1, 6, 30), force)
            current = current_job.result()
            try:
                previous = prior_job.result()
            except DataError as exc:
                previous = Dataset([], [], ["Edellisen kauden aineisto ei ole saatavilla. " + str(exc)])
        return current, previous

    def prediction(self, day: date, game_key: str, model: str = "balanced", force: bool = False) -> dict:
        listing = self.day(day, force)
        row = next((row for row in listing["games"] if row["key"] == game_key), None)
        if row is None:
            raise DataError("Valittua ottelua ei löydy pyydetyn päivän otteluohjelmasta.")
        fixture = fixture_from_public(row)
        through = min(day - timedelta(days=1), helsinki(utc_now()).date())
        current, previous = self._datasets(fixture.season, through, force)
        result = predict(fixture, current.games + previous.games, model)
        result["sources"] = _unique_sources(listing["sources"] + current.sources + previous.sources)
        result["source_warnings"] = listing["warnings"] + current.warnings + previous.warnings
        result["demo"] = self.provider.demo
        result["stale"] = any(s["stale"] for s in result["sources"])
        return result

    def history_test(self, day: date, model: str = "balanced", limit: int = 100) -> dict:
        now = utc_now()
        through = min(day, helsinki(now).date())
        season = season_for(day)
        current, previous = self._datasets(season, through, False)
        # A past calendar selection must not see games after that day.
        as_of = min(now, day_start_utc(day + timedelta(days=1)))
        result = backtest(current.games + previous.games, season, model, now=as_of, limit=limit)
        result["sources"] = _unique_sources(current.sources + previous.sources)
        result["warnings"] = current.warnings + previous.warnings
        result["demo"] = self.provider.demo
        result["stale"] = any(s["stale"] for s in result["sources"])
        return result
