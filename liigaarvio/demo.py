"""Explicitly opt-in synthetic fixtures. Never used as a live-data fallback."""
from __future__ import annotations
import math
import random
from datetime import date, datetime, timedelta

from .domain import Game, day_start_utc, helsinki, parse_games, season_for, utc_now
from .provider import Dataset


def make_demo(today: date | None = None) -> list[Game]:
    today = today or helsinki(utc_now()).date()
    season = season_for(today)
    rng = random.Random(87321)
    names = ["Koti A", "Vieras B", "Joukkue C", "Joukkue D", "Joukkue E", "Joukkue F"]
    records = []
    counter = 1

    def sample(mean):
        value, product = 0, 1.0
        while product > math.exp(-mean):
            product *= rng.random()
            value += 1
        return value - 1

    def add(day, h, a, played=True):
        nonlocal counter
        start = day_start_utc(day) + timedelta(hours=18, minutes=30)
        hg, ag = sample(3.4 if h == "Koti A" else 2.7), sample(2.3)
        extra = played and hg == ag
        if extra:
            if rng.random() < 0.5:
                hg += 1
            else:
                ag += 1
        records.append({"id": counter, "season": season_for(day), "start": start.isoformat(),
                        "serie": "RUNKOSARJA", "started": played, "ended": played,
                        "homeTeam": {"teamName": h, "goals": hg if played else None},
                        "awayTeam": {"teamName": a, "goals": ag if played else None},
                        "finishedType": "ENDED_DURING_OVERTIME" if extra else "ENDED_DURING_REGULAR_GAME_TIME",
                        "gameTime": 3674 if extra else 3600})
        counter += 1
    # Prior season background, always earlier than the current season.
    for i in range(32):
        d = date(season - 1, 1, 5) + timedelta(days=i * 3)
        h = names[i % 6]
        a = names[(i * 3 + 1) % 6]
        if h == a:
            a = names[(names.index(h) + 1) % 6]
        add(d, h, a)
    lower = date(season - 1, 7, 1)
    for days_back in range(30, 0, -1):
        d = today - timedelta(days=days_back)
        if d < lower:
            continue
        for j in range(3):
            i = days_back + j
            h = names[(i + j) % 6]
            a = names[(i + j + 3) % 6]
            add(d, h, a)
    for offset in (0, 1, 3):
        d = today + timedelta(days=offset)
        add(d, names[0], names[1], False)
        add(d, names[2], names[3], False)
        add(d, names[4], names[5], False)
    output = []
    for s in {r["season"] for r in records}:
        games, _ = parse_games([r for r in records if r["season"] == s], s, "demo:synthetic")
        output.extend(games)
    return sorted(output, key=lambda g: g.start)


class DemoProvider:
    demo = True

    def __init__(self, today: date | None = None):
        self.today = today or helsinki(utc_now()).date()
        self.games = make_demo(self.today)

    def day(self, day: date, force: bool = False) -> dict:
        days = sorted({g.day for g in self.games})
        previous = [d for d in days if d < day]
        following = [d for d in days if d > day]
        nav = {}
        if previous:
            nav["previousGameDate"] = previous[-1].isoformat()
        if following:
            nav["nextGameDate"] = following[0].isoformat()
        return {"date": day.isoformat(), "today": self.today.isoformat(), "demo": True,
                "games": [g.public() for g in self.games if g.day == day],
                "navigation": nav, "sources": [],
                "warnings": ["DEMO: kaikki joukkueet, tulokset ja otteluohjelma ovat keksittyä testidataa."]}

    def season(self, season: int, through: date, force: bool = False) -> Dataset:
        return Dataset([g for g in self.games if g.season == season], [],
                       ["DEMO – ei oikeita Liiga-tilastoja."])
