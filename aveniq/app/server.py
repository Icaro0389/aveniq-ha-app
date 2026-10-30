"""Aveniq API: ingress-only frontend and small Home Assistant REST proxy.
No long-lived access token is ever exposed to the browser.
"""
import json
import logging
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

STATIC = Path(__file__).resolve().parent / 'static'
PORT = int(os.environ.get('PORT', '8099'))
TOKEN = os.environ.get('SUPERVISOR_TOKEN') or os.environ.get('HASSIO_TOKEN')
BASE = 'http://supervisor/core/api'
ALLOWED = {
    'light': {'turn_on', 'turn_off', 'toggle'},
    'switch': {'turn_on', 'turn_off', 'toggle'},
    'cover': {'open_cover', 'close_cover', 'stop_cover', 'set_cover_position'},
    'climate': {'set_temperature', 'set_hvac_mode', 'turn_on', 'turn_off'},
    'vacuum': {'start', 'pause', 'return_to_base', 'stop'},
    'script': {'turn_on'},
    'media_player': {'media_play_pause', 'media_stop', 'media_next_track', 'media_previous_track', 'volume_up', 'volume_down'},
}
# Security-sensitive commands intentionally omitted in the first release:
# unlock, alarm disarm, garage control, remote execution, service restarts.


def ha(method, resource, payload=None):
    if not TOKEN:
        raise RuntimeError('SUPERVISOR_TOKEN mancante: eseguire come Home Assistant App')
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = Request(BASE + resource, data=data, method=method, headers={
        'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'
    })
    with urlopen(req, timeout=12) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        logging.info('%s %s', self.address_string(), fmt % args)

    def send_json(self, code, value):
        raw = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'self'")
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/health':
            return self.send_json(200, {'ok': True, 'name': 'Aveniq', 'ha_connected': bool(TOKEN)})
        if path == '/api/states':
            try:
                return self.send_json(200, {'states': ha('GET', '/states')})
            except (RuntimeError, HTTPError, URLError, TimeoutError) as ex:
                logging.warning('HA error: %s', ex)
                return self.send_json(502, {'error': 'Home Assistant non raggiungibile'})
        if path in ('/', '/index.html'):
            path = '/index.html'
        # Serve only explicit static paths; no traversal.
        if path != '/index.html' and not path.startswith('/assets/'):
            return self.send_json(404, {'error': 'Not found'})
        file = (STATIC / path.lstrip('/')).resolve()
        if not file.is_relative_to(STATIC.resolve()) or not file.is_file():
            return self.send_json(404, {'error': 'Not found'})
        raw = file.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'self'")
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if urlsplit(self.path).path != '/api/service':
            return self.send_json(404, {'error': 'Not found'})
        if self.headers.get('Sec-Fetch-Site', 'same-origin') not in ('same-origin', 'none'):
            return self.send_json(403, {'error': 'Origin non consentita'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 8192:
                return self.send_json(400, {'error': 'Dimensione richiesta non valida'})
            data = json.loads(self.rfile.read(length))
            domain, service = data['domain'], data['service']
            entity_id = data['entity_id']
            if not all(isinstance(x, str) for x in (domain, service, entity_id)):
                raise ValueError('Bad fields')
            if service not in ALLOWED.get(domain, ()) or not entity_id.startswith(domain + '.'):
                return self.send_json(403, {'error': 'Comando non consentito'})
            extra = data.get('data', {})
            if not isinstance(extra, dict) or any(k not in ('brightness_pct','rgb_color','temperature','hvac_mode','position') for k in extra):
                return self.send_json(400, {'error': 'Parametri non validi'})
            ha('POST', f'/services/{domain}/{service}', {'entity_id': entity_id, **extra})
            return self.send_json(200, {'ok': True})
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return self.send_json(400, {'error': 'Richiesta non valida'})
        except (RuntimeError, HTTPError, URLError, TimeoutError) as ex:
            logging.warning('Service error: %s', ex)
            return self.send_json(502, {'error': 'Comando non riuscito'})


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if not TOKEN:
        logging.warning('SUPERVISOR_TOKEN non impostato; gli endpoint HA non funzioneranno')
    print(f'Aveniq API listening on :{PORT}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
