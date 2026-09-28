"""Transparent heuristic goal model; NOT fitted or calibrated on Liiga results.

All training records precede the forecast day's Helsinki midnight. This makes
historical replays free of same-day result leakage. No scraped tipster opinions,
LLM predictions, lineup assumptions or betting odds enter the calculations.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Iterable

from .domain import DataError, Game, day_start_utc, helsinki, season_label, utc_now

MODEL_VERSION = "1.0.0"
PRIOR_GAMES = 8.0
RECENT_MAX_WEIGHT = 0.20
VENUE_MAX_WEIGHT = 0.20
H2H_MAX_WEIGHT = 0.10


def stats(games: Iterable[Game], team: str) -> dict:
    rows = sorted((g for g in games if g.usable and team in (g.home_key, g.away_key)),
                  key=lambda g: g.start)
    gf = ga = gf_final = ga_final = wins = 0
    for g in rows:
        home = g.home_key == team
        scored = g.home_60 if home else g.away_60
        allowed = g.away_60 if home else g.home_60
        final_scored = g.home_goals if home else g.away_goals
        final_allowed = g.away_goals if home else g.home_goals
        assert scored is not None and allowed is not None
        assert final_scored is not None and final_allowed is not None
        gf += scored
        ga += allowed
        gf_final += final_scored
        ga_final += final_allowed
        wins += int(final_scored > final_allowed)
    n = len(rows)
    return {"n": n, "gf": gf, "ga": ga,
            "gf_avg": gf / n if n else None, "ga_avg": ga / n if n else None,
            "gf_final": gf_final, "ga_final": ga_final,
            "gf_final_avg": gf_final / n if n else None,
            "ga_final_avg": ga_final / n if n else None,
            "wins": wins, "losses": n - wins,
            "games": [g.public() for g in reversed(rows)]}


def poisson_pmf(mean: float) -> list[float]:
    if not math.isfinite(mean) or not 0 <= mean <= 40:
        raise ValueError("Goal mean must be finite and in [0, 40]")
    values = [math.exp(-mean)]
    total = values[0]
    for k in range(1, 201):
        if k > mean and 1.0 - total < 1e-13:
            break
        value = values[-1] * mean / k
        values.append(value)
        total += value
    return [p / total for p in values]


def distribution(home_mean: float, away_mean: float) -> dict:
    hp, ap = poisson_pmf(home_mean), poisson_pmf(away_mean)
    regular = []
    final: dict[tuple[int, int], float] = {}
    win_home = draw = win_away = 0.0
    totals: dict[int, float] = {}
    for h, ph in enumerate(hp):
        for a, pa in enumerate(ap):
            probability = ph * pa
            regular.append({"home": h, "away": a, "p": probability})
            totals[h + a] = totals.get(h + a, 0.0) + probability
            if h > a:
                win_home += probability
                final[h, a] = final.get((h, a), 0.0) + probability
            elif h < a:
                win_away += probability
                final[h, a] = final.get((h, a), 0.0) + probability
            else:
                draw += probability
                # Explicit neutral assumption, not an estimated OT skill.
                final[h + 1, a] = final.get((h + 1, a), 0.0) + probability * 0.5
                final[h, a + 1] = final.get((h, a + 1), 0.0) + probability * 0.5
    regular.sort(key=lambda row: (-row["p"], row["home"] + row["away"], row["home"]))
    finals = [{"home": key[0], "away": key[1], "p": p} for key, p in final.items()]
    finals.sort(key=lambda row: (-row["p"], row["home"] + row["away"], row["home"]))
    cumulative = 0.0
    low = high = None
    for total_goals, p in sorted(totals.items()):
        cumulative += p
        if low is None and cumulative >= 0.10:
            low = total_goals
        if high is None and cumulative >= 0.90:
            high = total_goals
    return {
        "regulation": {"home": win_home, "draw": draw, "away": win_away},
        "winner": {"home": win_home + draw / 2, "away": win_away + draw / 2},
        "top_regular": regular[:8], "top_final": finals[:8],
        "expected_total_60": home_mean + away_mean,
        "expected_total_final": home_mean + away_mean + draw,
        "total_range_80": [low, high],
        "totals": [{"goals": n, "p": p} for n, p in sorted(totals.items()) if p >= 1e-6],
        "over": [{"line": line, "p": sum(p for n, p in totals.items() if n > line)}
                 for line in (4.5, 5.5, 6.5)],
        "mass": sum(p for p in final.values()),
        "ot_home_probability": 0.5,
    }


def _team_model(team: str, games: list[Game], previous: list[Game], league_mean: float,
                venue: str, model: str) -> dict:
    own = [g for g in games if team in (g.home_key, g.away_key)]
    season_stats = stats(own, team)
    recent_stats = stats(own[-5:], team)
    venue_stats = stats([g for g in own if (g.home_key == team) == (venue == "home")], team)
    prior_stats = stats(previous, team)
    if prior_stats["n"]:
        prior_gf = (prior_stats["gf"] + 10 * league_mean) / (prior_stats["n"] + 10)
        prior_ga = (prior_stats["ga"] + 10 * league_mean) / (prior_stats["n"] + 10)
        prior_label = "Edellisen kauden joukkuetilasto, tasoitettu sarjakeskiarvoon 10 ottelulla"
    else:
        prior_gf = prior_ga = league_mean
        prior_label = "Sarjan maalikeskiarvo; joukkueen edellisen kauden aineisto puuttuu"
    n = season_stats["n"]
    if model == "simple":
        if not n:
            raise DataError("Perusmalli tarvitsee molemmilta vähintään yhden tämän kauden ottelun.")
        base_gf, base_ga = season_stats["gf_avg"], season_stats["ga_avg"]
        recent_weight = venue_weight = 0.0
    else:
        base_gf = (season_stats["gf"] + PRIOR_GAMES * prior_gf) / (n + PRIOR_GAMES)
        base_ga = (season_stats["ga"] + PRIOR_GAMES * prior_ga) / (n + PRIOR_GAMES)
        recent_weight = RECENT_MAX_WEIGHT * min(recent_stats["n"] / 5, 1)
        venue_weight = VENUE_MAX_WEIGHT * min(venue_stats["n"] / 10, 1)
    form_gf = (1 - recent_weight) * base_gf + recent_weight * (recent_stats["gf_avg"] or 0)
    form_ga = (1 - recent_weight) * base_ga + recent_weight * (recent_stats["ga_avg"] or 0)
    effective_gf = (1 - venue_weight) * form_gf + venue_weight * (venue_stats["gf_avg"] or 0)
    effective_ga = (1 - venue_weight) * form_ga + venue_weight * (venue_stats["ga_avg"] or 0)
    return {
        "season": season_stats, "recent": recent_stats, "venue": venue_stats,
        "previous": prior_stats, "venue_kind": venue,
        "prior_gf": prior_gf, "prior_ga": prior_ga, "prior_label": prior_label,
        "prior_weight": PRIOR_GAMES / (n + PRIOR_GAMES) if model != "simple" else 0,
        "base_gf": base_gf, "base_ga": base_ga,
        "recent_weight": recent_weight, "venue_weight": venue_weight,
        "form_gf": form_gf, "form_ga": form_ga,
        "effective_gf": effective_gf, "effective_ga": effective_ga,
    }


def predict(fixture: Game, all_games: list[Game], model: str = "balanced",
            now: datetime | None = None, include_training: bool = True) -> dict:
    if model not in ("balanced", "simple"):
        raise DataError("Tuntematon laskentamalli.")
    now = now or utc_now()
    cutoff = min(day_start_utc(fixture.day), now)
    eligible = sorted((g for g in all_games if g.usable and g.start < cutoff
                       and g.key != fixture.key), key=lambda g: g.start)
    current = [g for g in eligible if g.season == fixture.season]
    previous = [g for g in eligible if g.season == fixture.season - 1]
    if not current and not previous:
        raise DataError("Arvioon ei ole yhtään varmennettua päättynyttä ottelua.")
    prev_mean = sum(g.home_60 + g.away_60 for g in previous) / (2 * len(previous)) if previous else None
    current_sum = sum(g.home_60 + g.away_60 for g in current)
    league_prior_n = min(30, len(previous))
    if previous:
        league_mean = (current_sum / 2 + league_prior_n * prev_mean) / (len(current) + league_prior_n)
    else:
        league_mean = current_sum / (2 * len(current))
    home = _team_model(fixture.home_key, current, previous, league_mean, "home", model)
    away = _team_model(fixture.away_key, current, previous, league_mean, "away", model)
    pairs = [g for g in current + previous
             if {g.home_key, g.away_key} == {fixture.home_key, fixture.away_key}]
    pairs.sort(key=lambda g: g.start)
    pairs = pairs[-6:]
    pair_stats = stats(pairs, fixture.home_key)
    h2h_weight = H2H_MAX_WEIGHT * min(len(pairs) / 5, 1) if model == "balanced" else 0
    base_home = (home["effective_gf"] + away["effective_ga"]) / 2
    base_away = (away["effective_gf"] + home["effective_ga"]) / 2
    raw_home = (1 - h2h_weight) * base_home + h2h_weight * (pair_stats["gf_avg"] or 0)
    raw_away = (1 - h2h_weight) * base_away + h2h_weight * (pair_stats["ga_avg"] or 0)
    # Guard a degenerate zero sample; upper bound only protects corrupted data.
    home_mean = min(15.0, max(0.05, raw_home))
    away_mean = min(15.0, max(0.05, raw_away))
    probabilities = distribution(home_mean, away_mean)
    warnings = [
        "Malli on yksinkertainen tilastollinen arvio. Painoja ja prosentteja ei ole kalibroitu Liigan historiadatalla.",
        "Kokoonpanot, aloittavat maalivahdit, loukkaantumiset, lepoajat, ylivoima ja kertoimet eivät vaikuta tähän versioon.",
        "Tasatilanteessa jatkoaika-/voittolaukausvoitto jaetaan oletuksena 50/50.",
    ]
    n = min(home["season"]["n"], away["season"]["n"])
    sample = "Vähän tämän kauden aineistoa" if n < 8 else ("Karttuva aineisto" if n < 20 else "Enemmän aineistoa")
    if n < 8:
        warnings.insert(0, "Alkukausi tai pieni otos: yksittäiset ottelut muuttavat keskiarvoja paljon.")
    if fixture.started or fixture.start <= now:
        warnings.insert(0, "Tämä on ennen ottelupäivää käytettävissä olleista tuloksista laskettu arvio, ei live-ennuste.")
    if raw_home != home_mean or raw_away != away_mean:
        warnings.append("Maalikeskiarvoon sovellettiin mallin teknistä rajaa 0,05–15 maalia.")
    omitted = [g for g in all_games if g.season == fixture.season and g.ended and not g.usable
               and g.start < cutoff]
    if omitted:
        warnings.insert(0, f"{len(omitted)} päättyneen ottelun 60 minuutin tulosta ei voitu varmistaa. Ne jätettiin pois.")
    pair_current = sum(g.season == fixture.season for g in pairs)
    trace = {
        "base_home": base_home, "base_away": base_away,
        "h2h_weight": h2h_weight, "h2h_home_avg": pair_stats["gf_avg"],
        "h2h_away_avg": pair_stats["ga_avg"], "h2h_current_count": pair_current,
        "h2h_previous_count": len(pairs) - pair_current,
        "raw_home": raw_home, "raw_away": raw_away,
        "lambda_home": home_mean, "lambda_away": away_mean,
        "league_mean": league_mean, "league_current_games": len(current),
        "league_previous_games": len(previous), "league_prior_games": league_prior_n,
        "league_current_goal_sum": current_sum, "league_previous_mean": prev_mean,
        "prior_games": PRIOR_GAMES, "recent_max_weight": RECENT_MAX_WEIGHT,
        "venue_max_weight": VENUE_MAX_WEIGHT, "h2h_max_weight": H2H_MAX_WEIGHT,
    }
    return {
        "model": model, "model_version": MODEL_VERSION, "fixture": fixture.public(),
        "as_of": cutoff.isoformat(), "as_of_fi": helsinki(cutoff).strftime("%d.%m.%Y %H:%M"),
        "sample": sample, "home": home, "away": away, "h2h": pair_stats,
        "trace": trace, "probabilities": probabilities, "warnings": warnings,
        "training_scope": f"Runkosarja {season_label(fixture.season)}; tausta ja keskinäiset myös {season_label(fixture.season - 1)}",
        "excluded_count": len(omitted), "generated_at": now.isoformat(),
        "training_games": [g.public() for g in current + previous] if include_training else [],
    }


def backtest(all_games: list[Game], season: int, model: str = "balanced",
             now: datetime | None = None, limit: int = 100) -> dict:
    """Walk-forward replay, with current-day games excluded from each forecast.

    No optimization or hyperparameter selection occurs here. This is a local
    descriptive check, not an independent validation or guaranteed win rate.
    """
    now = now or utc_now()
    limit = max(1, min(300, limit))
    fixtures = sorted((g for g in all_games if g.season == season and g.usable
                       and g.start < now), key=lambda g: g.start)[-limit:]
    rows = []
    skipped = 0
    for game in fixtures:
        try:
            prediction = predict(game, all_games, model, now=now, include_training=False)
        except DataError:
            skipped += 1
            continue
        p = prediction["probabilities"]
        top = p["top_final"][0]
        exact = top["home"] == game.home_goals and top["away"] == game.away_goals
        outcome = "home" if game.home_60 > game.away_60 else ("away" if game.home_60 < game.away_60 else "draw")
        brier = sum((p["regulation"][key] - int(key == outcome)) ** 2 for key in ("home", "draw", "away"))
        logloss = -math.log(max(1e-15, p["regulation"][outcome]))
        fav = max(p["winner"], key=p["winner"].get)
        # Exactly equal probabilities have no favourite and must not bias hit rate.
        tied = abs(p["winner"]["home"] - p["winner"]["away"]) < 1e-12
        win = (game.home_goals > game.away_goals) == (fav == "home")
        rows.append({"game": game.public(), "predicted_home": top["home"], "predicted_away": top["away"],
                     "exact": exact, "winner_hit": None if tied else win,
                     "brier": brier, "logloss": logloss,
                     "top3_hit": any(r["home"] == game.home_goals and r["away"] == game.away_goals
                                     for r in p["top_final"][:3])})
    n = len(rows)
    winner_rows = [r for r in rows if r["winner_hit"] is not None]
    return {"n": n, "skipped": skipped, "model": model,
            "exact_rate": sum(r["exact"] for r in rows) / n if n else None,
            "top3_rate": sum(r["top3_hit"] for r in rows) / n if n else None,
            "winner_rate": sum(r["winner_hit"] for r in winner_rows) / len(winner_rows) if winner_rows else None,
            "winner_n": len(winner_rows),
            "brier": sum(r["brier"] for r in rows) / n if n else None,
            "logloss": sum(r["logloss"] for r in rows) / n if n else None,
            "uniform_brier": 2 / 3, "rows": list(reversed(rows))[:30],
            "note": "Jälkilaskenta käyttää vain kunkin ottelupäivän alkua edeltäneitä tuloksia. Lähteen myöhempiä korjauksia ei voi poistaa. Tämä ei ole ennakkoon tallennettu ennusteseuranta eikä riippumaton kalibrointi."}
