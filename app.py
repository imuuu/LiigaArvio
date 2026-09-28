#!/usr/bin/env python3
"""Run: python app.py. Standard library only; binds to this computer, not the LAN."""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import threading
import urllib.parse
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from liigaarvio.domain import DataError, helsinki, season_for, utc_now
from liigaarvio.provider import JsonClient, LiigaProvider
from liigaarvio.service import Service

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
LOG = logging.getLogger("liigaarvio")


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, service):
        self.service = service
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "LiigaArvio/1.0"

    def _send(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, value, status=200):
        self._send(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _allowed(self):
        port = self.server.server_port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host", "") not in allowed:
            self._json({"error": "Vain paikalliset pyynnöt on sallittu."}, 403)
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{host}" for host in allowed}:
            self._json({"error": "Toisen sivuston pyyntö estettiin."}, 403)
            return False
        return True

    def do_GET(self):
        if not self._allowed():
            return
        parsed = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        assets = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/index.html": ("index.html", "text/html; charset=utf-8"),
                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                  "/style.css": ("style.css", "text/css; charset=utf-8")}
        if parsed.path in assets:
            name, mime = assets[parsed.path]
            self._send(200, (STATIC / name).read_bytes(), mime)
            return
        if parsed.path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
            return
        service = self.server.service
        try:
            if parsed.path in ("/api/config", "/api/health"):
                self._json(service.config())
                return
            if parsed.path == "/api/status":
                client = getattr(service.provider, "client", None)
                self._json({"activity": getattr(client, "last_activity", "Valmis")})
                return
            if parsed.path not in ("/api/day", "/api/predict", "/api/backtest"):
                self._json({"error": "Sivua ei löydy."}, 404)
                return
            raw_day = query.get("date", [service.config()["today"]])[0]
            try:
                day = date.fromisoformat(raw_day)
                if not 2001 <= day.year <= 2099:
                    raise ValueError()
            except ValueError as exc:
                raise DataError("Anna päivä muodossa VVVV-KK-PP (vuodet 2001–2099).") from exc
            force = query.get("refresh", ["0"])[0] == "1"
            model = query.get("model", ["balanced"])[0]
            if model not in ("balanced", "simple"):
                raise DataError("Tuntematon laskentamalli.")
            if parsed.path == "/api/day":
                self._json(service.day(day, force))
            elif parsed.path == "/api/predict":
                game = query.get("game", [""])[0]
                if not re.fullmatch(r"\d{4}-\d{1,9}", game):
                    raise DataError("Virheellinen ottelutunniste.")
                self._json(service.prediction(day, game, model, force))
            else:
                self._json(service.history_test(day, model))
        except DataError as exc:
            LOG.warning("%s: %s", parsed.path, exc)
            self._json({"error": str(exc), "kind": "data",
                        "help": "Tarkista internetyhteys ja kokeile Päivitä. Yksityiskohdat näet KAYNNISTA-ikkunasta. TARKISTA_YHTEYS.bat tekee erillisen verkkotestin. Ohjelma ei vaihda itsestään demodataan."}, 503)
        except Exception:
            LOG.exception("Unexpected request failure")
            self._json({"error": "Ohjelmassa tapahtui odottamaton virhe. Katso käynnistysikkunan virheloki."}, 500)

    def do_POST(self):
        self._json({"error": "Kirjoitusrajapintoja ei ole käytössä."}, 405)

    def log_message(self, fmt, *args):
        if args and str(args[1] if len(args) > 1 else "") not in {"200", "204"}:
            LOG.info(fmt, *args)


def check_connection(service: Service) -> int:
    today = helsinki(utc_now()).date()
    print("LiigaArvio – yhteystesti")
    print("Päivä Suomessa:", today.isoformat())
    print("Datalähde:", "KEKSITTY DEMODATA" if service.provider.demo else "Liiga.fi JSON API")
    try:
        day = service.day(today, True)
        print("Päivän otteluita:", len(day["games"]))
        for source in day["sources"]:
            print("Lähde:", source)
        season = service.provider.season(season_for(today), today, True)
        print("Kauden otteluita:", len(season.games))
        print("Päättyneitä, 60 min tulos kelvollinen:", sum(g.usable for g in season.games))
        if day["games"]:
            report = service.prediction(today, day["games"][0]["key"])
            first = report["probabilities"]["top_final"][0]
            print("Esimerkkiarvio:", report["fixture"]["home"], first["home"], "–", first["away"], report["fixture"]["away"])
        if any(source["stale"] for source in day["sources"] + season.sources):
            print("VAROITUS: vastaus tuli osittain vanhasta välimuistista. Live-yhteys ei ole kunnossa.")
            return 1
        print("Yhteystesti valmistui.")
        return 0
    except DataError as exc:
        print("YHTEYSTESTI EPÄONNISTUI:", exc)
        return 1


def main():
    parser = argparse.ArgumentParser(description="LiigaArvio – paikallinen Liigan runkosarjan arviointisovellus")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--demo", action="store_true", help="Käytä VAIN keksittyä testidataa")
    parser.add_argument("--check", action="store_true", help="Testaa datalähteen verkkoyhteys ja poistu")
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65525:
        parser.error("Portin on oltava välillä 1024–65525.")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.demo:
        from liigaarvio.demo import DemoProvider
        service = Service(DemoProvider())
    else:
        service = Service(LiigaProvider(JsonClient(args.cache_dir)))
    if args.check:
        return check_connection(service)
    server = None
    for port in range(args.port, args.port + 10):
        try:
            server = LocalServer(("127.0.0.1", port), service)
            break
        except OSError:
            continue
    if server is None:
        print("Paikallista porttia ei saatu avattua. Sulje toinen sovellus tai käytä --port 9000.")
        return 1
    url = f"http://127.0.0.1:{server.server_port}"
    print("\nLiigaArvio 1.0" + (" – DEMO / KEKSITTY DATA" if args.demo else " – Liigan runkosarja"))
    print("Avaa selaimessa:", url)
    print("Pidä tämä ikkuna auki käytön ajan. Sulje sovellus painamalla Ctrl+C.\n")
    if not args.no_browser:
        timer = threading.Timer(0.5, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSovellus suljetaan.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        print("LiigaArvio tarvitsee Python 3.10:n tai uudemman.")
        sys.exit(1)
    sys.exit(main())
