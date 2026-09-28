from __future__ import annotations

import json
import math
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from liigaarvio.demo import DemoProvider, make_demo
from liigaarvio.domain import (DataError, UTC, day_start_utc, helsinki, parse_datetime,
                               parse_game, parse_games, season_for)
from liigaarvio.model import backtest, distribution, poisson_pmf, predict, stats
from liigaarvio.provider import Fetch, JsonClient, LiigaProvider, SourceUnavailable
from liigaarvio.service import Service
from app import LocalServer

NOW = datetime(2026, 9, 27, 10, tzinfo=UTC)


def record(gid=1, day="2026-09-15", home="Koti", away="Vieras", hg=3, ag=1,
           finish="ENDED_DURING_REGULAR_GAME_TIME", ended=True, season=2027):
    return {"id":gid, "season":season, "start":day+"T15:30:00Z", "serie":"RUNKOSARJA",
            "homeTeam":{"teamId":"1:"+home, "teamName":home,"goals":hg},
            "awayTeam":{"teamId":"2:"+away, "teamName":away,"goals":ag},
            "started":ended,"ended":ended,"finishedType":finish,
            "gameTime":3600 if finish == "ENDED_DURING_REGULAR_GAME_TIME" else 3780}


def game(**kwargs):
    row = record(**kwargs)
    return parse_game(row,row['season'],"https://liiga.fi/api/v2/games?test=1")


class DomainTests(unittest.TestCase):
    def test_season_ending_year(self):
        self.assertEqual(season_for(date(2026,9,1)),2027)
        self.assertEqual(season_for(date(2026,2,1)),2026)

    def test_helsinki_summer_and_winter(self):
        self.assertEqual(helsinki(datetime(2026,9,27,10,tzinfo=UTC)).hour,13)
        self.assertEqual(helsinki(datetime(2026,1,27,10,tzinfo=UTC)).hour,12)

    def test_dst_boundaries(self):
        self.assertEqual(helsinki(datetime(2026,3,29,0,59,tzinfo=UTC)).hour,2)
        self.assertEqual(helsinki(datetime(2026,3,29,1,tzinfo=UTC)).hour,4)
        self.assertEqual(helsinki(datetime(2026,10,25,0,59,tzinfo=UTC)).hour,3)
        self.assertEqual(helsinki(datetime(2026,10,25,1,tzinfo=UTC)).hour,3)

    def test_windows_no_tzdata_fallback(self):
        from zoneinfo import ZoneInfoNotFoundError
        with patch('zoneinfo.ZoneInfo',side_effect=ZoneInfoNotFoundError):
            self.assertEqual(helsinki(NOW).hour,13)
            self.assertEqual(day_start_utc(date(2026,3,29)),datetime(2026,3,28,22,tzinfo=UTC))
            self.assertEqual(day_start_utc(date(2026,10,25)),datetime(2026,10,24,21,tzinfo=UTC))

    def test_timezone_required(self):
        with self.assertRaises(DataError): parse_datetime("2026-09-15T15:00:00")

    def test_local_date_not_utc_date(self):
        r=record(); r['start']='2026-09-15T22:00:00Z'
        self.assertEqual(parse_game(r,2027).day,date(2026,9,16))

    def test_regular_result(self):
        g=game(hg=5,ag=2)
        self.assertEqual((g.home_60,g.away_60),(5,2))
        self.assertTrue(g.usable)

    def test_overtime_home(self):
        g=game(hg=3,ag=2,finish="ENDED_DURING_OVERTIME")
        self.assertEqual((g.home_60,g.away_60),(2,2))

    def test_shootout_away(self):
        g=game(hg=0,ag=1,finish="ENDED_DURING_WINNING_SHOT_COMPETITION")
        self.assertEqual((g.home_60,g.away_60),(0,0))

    def test_bad_ot_score_not_guessed(self):
        self.assertFalse(game(hg=6,ag=2,finish="ENDED_DURING_OVERTIME").usable)

    def test_unknown_finish_not_guessed(self):
        self.assertFalse(game(finish="NEW_UNKNOWN_TYPE").usable)

    def test_unknown_finish_time_fallback(self):
        r=record();r['finishedType']=None;r['gameTime']=3600
        self.assertEqual(parse_game(r,2027).home_60,3)

    def test_cancelled_not_training(self):
        self.assertFalse(game(finish="CANCELLED").usable)

    def test_unfinished_not_training(self):
        self.assertFalse(game(ended=False).usable)

    def test_missing_goal_not_zero(self):
        g=game(hg=None)
        self.assertIsNone(g.home_goals)
        self.assertFalse(g.usable)

    def test_zero_is_real_goal_count(self):
        self.assertEqual(game(hg=0,ag=2).home_60,0)

    def test_invalid_goal_rejected(self):
        for value in (-1,True,4.5,99):
            with self.subTest(value=value), self.assertRaises(DataError): game(hg=value)

    def test_other_tournament_and_season_excluded(self):
        r=record();r['serie']='PLAYOFFS';self.assertIsNone(parse_game(r,2027))
        self.assertIsNone(parse_game(record(),2026))

    def test_date_season_mismatch(self):
        with self.assertRaises(DataError): game(day='2025-09-15')

    def test_wrapped_payload(self):
        rows, warnings=parse_games({'dates':[{'games':[record()]}]},2027)
        self.assertEqual(len(rows),1);self.assertEqual(warnings,[])

    def test_empty_and_unrecognized_payload(self):
        self.assertEqual(parse_games({'games':[]},2027),([],[]))
        with self.assertRaises(DataError): parse_games({'message':'oops'},2027)

    def test_duplicate_dedup_and_conflict(self):
        self.assertEqual(len(parse_games([record(),record()],2027)[0]),1)
        with self.assertRaises(DataError): parse_games([record(),record(hg=5)],2027)

    def test_missing_team_is_not_fabricated(self):
        r=record();r['homeTeam']={}
        with self.assertRaises(DataError):parse_game(r,2027)


class MathTests(unittest.TestCase):
    def setUp(self):
        self.games=[game(gid=1,home='Koti',away='C',hg=4,ag=1),
                    game(gid=2,day='2026-09-16',home='C',away='Koti',hg=2,ag=1),
                    game(gid=3,day='2026-09-17',home='Vieras',away='D',hg=3,ag=2),
                    game(gid=4,day='2026-09-18',home='D',away='Vieras',hg=4,ag=0)]
        self.fixture=game(gid=10,day='2026-09-27',ended=False,hg=None,ag=None)

    def test_simple_arithmetic_exact(self):
        r=predict(self.fixture,self.games,'simple',NOW)
        self.assertAlmostEqual(r['trace']['lambda_home'],2.75)
        self.assertAlmostEqual(r['trace']['lambda_away'],1.5)
        self.assertEqual(r['home']['season']['gf'],5)

    def test_poisson_known_values(self):
        p=poisson_pmf(2)
        self.assertAlmostEqual(p[0],math.exp(-2),12)
        self.assertAlmostEqual(p[2],2*math.exp(-2),12)

    def test_pmf_mass(self):
        for mean in (0,.05,1,2.75,8,15,40):
            with self.subTest(mean=mean):self.assertAlmostEqual(sum(poisson_pmf(mean)),1,12)

    def test_poisson_invalid(self):
        for value in (-1,float('nan'),float('inf'),41):
            with self.subTest(value=value),self.assertRaises(ValueError):poisson_pmf(value)

    def test_distribution_mass_and_no_final_draw(self):
        d=distribution(2.75,1.5)
        self.assertAlmostEqual(sum(d['regulation'].values()),1,12)
        self.assertAlmostEqual(sum(d['winner'].values()),1,12)
        self.assertAlmostEqual(d['mass'],1,12)
        self.assertTrue(all(r['home']!=r['away'] for r in d['top_final']))

    def test_symmetric_teams_have_half_win_probability(self):
        d=distribution(3,3)
        self.assertAlmostEqual(d['winner']['home'],.5,12)

    def test_extra_time_split(self):
        d=distribution(2,3)
        self.assertAlmostEqual(d['winner']['home'],d['regulation']['home']+.5*d['regulation']['draw'])
        self.assertAlmostEqual(d['expected_total_final'],5+d['regulation']['draw'])

    def test_degenerate_zero_score_ot(self):
        d=distribution(0,0)
        self.assertEqual(d['regulation']['draw'],1)
        self.assertEqual(d['winner']['home'],.5)

    def test_future_and_same_day_results_excluded(self):
        baseline=predict(self.fixture,self.games,'simple',NOW)['trace']
        bad=[game(gid=50,day='2026-09-27',home='Koti',away='D',hg=12,ag=1),
             game(gid=51,day='2026-09-28',home='Koti',away='D',hg=14,ag=1)]
        self.assertEqual(predict(self.fixture,self.games+bad,'simple',NOW)['trace'],baseline)

    def test_target_result_cannot_leak(self):
        completed=replace(self.fixture,ended=True,home_goals=9,away_goals=1,home_60=9,away_60=1)
        baseline=predict(self.fixture,self.games,'simple',NOW)['trace']
        self.assertEqual(predict(completed,self.games+[completed],'simple',NOW)['trace'],baseline)

    def test_no_training_refuses_prediction(self):
        with self.assertRaises(DataError):predict(self.fixture,[],now=NOW)

    def test_simple_needs_both_teams(self):
        with self.assertRaises(DataError):predict(self.fixture,self.games[:2],'simple',NOW)

    def test_h2h_small_sample_weight(self):
        pair=game(gid=15,day='2026-09-19',hg=6,ag=1)
        r=predict(self.fixture,self.games+[pair],now=NOW)
        self.assertAlmostEqual(r['trace']['h2h_weight'],.02)
        self.assertEqual(r['h2h']['n'],1)

    def test_h2h_no_matches_zero(self):
        r=predict(self.fixture,self.games,now=NOW)
        self.assertEqual(r['trace']['h2h_weight'],0)

    def test_overtime_goals_removed_from_totals(self):
        s=stats([game(finish='ENDED_DURING_OVERTIME',hg=3,ag=2)],'koti')
        self.assertEqual(s['gf'],2);self.assertEqual(s['gf_final'],3)

    def test_zero_game_stats_no_fake_zero_average(self):
        s=stats([],'koti');self.assertEqual(s['n'],0);self.assertIsNone(s['gf_avg'])

    def test_backtest_does_not_use_later_results(self):
        allgames=make_demo(date(2026,9,27))
        first=backtest(allgames,2027,now=NOW,limit=10)
        future=game(gid=989,day='2026-09-29',home='Koti A',away='Vieras B',hg=20,ag=0)
        second=backtest(allgames+[future],2027,now=NOW,limit=10)
        self.assertEqual(first,second)
        self.assertGreater(first['n'],0)


class ProviderTests(unittest.TestCase):
    def test_cache_live_then_cached_then_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            client=JsonClient(Path(directory));url='https://liiga.fi/api/v2/games?test=1'
            with patch.object(client,'_network',return_value=[record()]) as network:
                first=client.get(url);second=client.get(url)
                self.assertFalse(first.cached);self.assertTrue(second.cached)
                self.assertEqual(network.call_count,1)
            path=next(Path(directory).glob('*.json'))
            saved=json.loads(path.read_text());saved['fetched_at']='2020-01-01T00:00:00+00:00';path.write_text(json.dumps(saved))
            with patch.object(client,'_network',side_effect=SourceUnavailable('test offline')):
                stale=client.get(url)
                self.assertTrue(stale.stale);self.assertEqual(stale.data,[record()])

    def test_no_cache_failure_never_generates_demo(self):
        with tempfile.TemporaryDirectory() as directory:
            client=JsonClient(Path(directory))
            with patch.object(client,'_network',side_effect=SourceUnavailable('test offline')):
                with self.assertRaises(SourceUnavailable):client.get('https://liiga.fi/api/v2/games')

    def test_network_hosts_locked(self):
        with tempfile.TemporaryDirectory() as directory:
            client=JsonClient(Path(directory))
            for url in ('http://liiga.fi/api/v2/games','https://example.com/foo','https://liiga.fi.evil.test/foo'):
                with self.subTest(url=url),self.assertRaises(SourceUnavailable):client._network(url)

    def test_wrong_day_not_displayed(self):
        with tempfile.TemporaryDirectory() as directory:
            client=JsonClient(Path(directory));provider=LiigaProvider(client)
            with patch.object(client,'get',return_value=Fetch({'games':[record()]},'https://liiga.fi/test',NOW.isoformat())):
                with self.assertRaises(DataError):provider.day(date(2026,9,27))

    def test_daily_response_not_treated_as_full_season(self):
        with tempfile.TemporaryDirectory() as directory:
            client=JsonClient(Path(directory));provider=LiigaProvider(client)
            payload={'games':[record()],'previousGameDate':'2026-09-14','nextGameDate':'2026-09-16'}
            from liigaarvio.provider import Dataset
            with patch.object(client,'get',return_value=Fetch(payload,'https://liiga.fi/test',NOW.isoformat())),patch.object(provider,'_walk_history',return_value=Dataset([],[],[])) as walk:
                provider.season(2027,date(2026,9,26))
                walk.assert_called_once()

    def test_history_chain_cannot_wrap_into_future(self):
        with tempfile.TemporaryDirectory() as directory:
            client=JsonClient(Path(directory));provider=LiigaProvider(client)
            payload={'games':[],'previousGameDate':'2027-03-20'}
            with patch.object(client,'get',return_value=Fetch(payload,'https://liiga.fi/test',NOW.isoformat())):
                with self.assertRaises(DataError):provider._walk_history(2027,date(2026,9,26),False)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=LocalServer(('127.0.0.1',0),Service(DemoProvider()))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(2)

    def get_json(self,path):
        with urllib.request.urlopen(self.base+path,timeout=10) as response:return json.load(response)

    def test_static_and_csp(self):
        with urllib.request.urlopen(self.base,timeout=5) as response:
            self.assertIn("script-src 'self'",response.headers['Content-Security-Policy'])
            self.assertIn('LiigaArvio',response.read().decode())

    def test_day_and_prediction_end_to_end_demo(self):
        config=self.get_json('/api/config');day=self.get_json('/api/day?date='+config['today'])
        self.assertTrue(day['demo']);self.assertGreater(len(day['games']),0)
        query=urllib.parse.urlencode({'date':config['today'],'game':day['games'][0]['key']})
        result=self.get_json('/api/predict?'+query)
        self.assertTrue(result['demo']);self.assertAlmostEqual(result['probabilities']['mass'],1)
        self.assertEqual(result['sources'],[])

    def test_host_rebinding_blocked(self):
        request=urllib.request.Request(self.base+'/api/config',headers={'Host':'evil.test'})
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
        self.assertEqual(error.exception.code,403)

    def test_cross_origin_blocked(self):
        request=urllib.request.Request(self.base+'/api/config',headers={'Origin':'https://evil.test'})
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
        self.assertEqual(error.exception.code,403)

    def test_path_traversal_not_served(self):
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(self.base+'/../app.py')
        self.assertEqual(error.exception.code,404)

    def test_invalid_date(self):
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(self.base+'/api/day?date=nope')
        self.assertEqual(error.exception.code,503)


if __name__=='__main__':unittest.main(verbosity=2)
