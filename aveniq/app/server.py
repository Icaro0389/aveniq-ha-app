"""Aveniq API: ingress-only frontend and small Home Assistant REST proxy.
No long-lived access token is ever exposed to the browser.
"""
import json
import logging
import mimetypes
import os
import time
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, parse_qs, urlencode
from urllib.request import Request, urlopen

DATA_DIR = Path('/data')
PREFS_FILE = DATA_DIR / 'aveniq-config.json'
PREFS_LOCK = Lock()
PREFS_DEFAULT = {'rooms': {}, 'widgets': [], 'theme': 'light', 'compact': False}
def read_prefs():
    try:
        if PREFS_FILE.exists():
            obj = json.loads(PREFS_FILE.read_text(encoding='utf-8'))
            return obj if isinstance(obj, dict) else dict(PREFS_DEFAULT)
    except (ValueError, OSError):
        pass
    return dict(PREFS_DEFAULT)

def save_prefs(obj):
    if not isinstance(obj, dict) or set(obj) - {'rooms', 'widgets', 'theme', 'compact', 'entityMap', 'showHero', 'showStatus', 'showWidgets', 'showQuick'}:
        raise ValueError('Invalid configuration')
    if len(json.dumps(obj)) > 4096:
        raise ValueError('Configuration too large')
    rooms = obj.get('rooms', {})
    widgets = obj.get('widgets', [])
    if not isinstance(rooms, dict) or len(rooms) > 25 or not isinstance(widgets, list) or len(widgets) > 30:
        raise ValueError('Invalid room/widget layout')
    for room, ids in rooms.items():
        if not isinstance(room, str) or len(room) > 64 or not isinstance(ids, list) or len(ids) > 100:
            raise ValueError('Invalid rooms')
        if any(not isinstance(e, str) or not __import__('re').fullmatch(r'[a-z_]+\.[a-z0-9_]+', e) for e in ids):
            raise ValueError('Invalid entity')
    for widget in widgets:
        if not isinstance(widget, dict) or set(widget) - {'type', 'title', 'entity', 'span'} or widget.get('type') not in ('entity', 'proxmox', 'ups', 'energy', 'network', 'zigbee', 'kodi'):
            raise ValueError('Invalid widget')
        if widget.get('span', 1) not in (1, 2, 3):
            raise ValueError('Invalid span')
        if len(str(widget.get('title', ''))) > 80 or len(str(widget.get('entity', ''))) > 150:
            raise ValueError('Invalid widget data')
    if obj.get('theme', 'light') not in ('dark', 'light') or not isinstance(obj.get('compact', False), bool):
        raise ValueError('Invalid appearance')
    with PREFS_LOCK:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = PREFS_FILE.with_suffix('.tmp')
        tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')
        tmp.replace(PREFS_FILE)


BRIDGE_GET = {'health', 'roots', 'favourites', 'radio'}
BRIDGE_POST = {'browse', 'play', 'favourite', 'favourite/remove'}
def bridge_request(action, payload=None):
    from urllib.parse import urlparse
    options_path = DATA_DIR / 'options.json'
    try:
        options = json.loads(options_path.read_text())
    except (OSError, ValueError):
        options = {}
    base_url = str(options.get('bridge_url', '')).rstrip('/')
    token = str(options.get('bridge_token', ''))
    parsed = urlparse(base_url)
    if parsed.scheme != 'http' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('', '/'):
        raise ValueError('Bridge URL non configurato correttamente')
    if len(token) < 32:
        raise ValueError('Token bridge non configurato')
    if action not in BRIDGE_GET | BRIDGE_POST:
        raise ValueError('Azione bridge non consentita')
    method = 'GET' if action in BRIDGE_GET else 'POST'
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(base_url + '/v1/' + action, data=data, method=method, headers={
        'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urlopen(req, timeout=12) as response:
        raw = response.read(1024 * 1024)
    return json.loads(raw) if raw else {}

STATIC = Path(__file__).resolve().parent / 'static'
PORT = int(os.environ.get('PORT', '8099'))
TOKEN = os.environ.get('SUPERVISOR_TOKEN') or os.environ.get('HASSIO_TOKEN')
BASE = 'http://supervisor/core/api'
ALLOWED = {
    'alarm_control_panel': {'alarm_arm_away', 'alarm_arm_night', 'alarm_disarm'},
    'lock': {'lock', 'unlock', 'open'},
    'light': {'turn_on', 'turn_off', 'toggle'},
    'switch': {'turn_on', 'turn_off', 'toggle'},
    'cover': {'open_cover', 'close_cover', 'stop_cover', 'set_cover_position'},
    'climate': {'set_temperature', 'set_hvac_mode', 'turn_on', 'turn_off', 'set_fan_mode', 'set_swing_mode'},
    'vacuum': {'start', 'pause', 'return_to_base', 'stop'},
    'script': {'turn_on'},
    'kodi': {'call_method'},
    'media_player': {'media_play_pause', 'media_stop', 'media_next_track', 'media_previous_track', 'volume_up', 'volume_down'},
}
# Security-sensitive commands intentionally omitted in the first release:
# garage control, remote execution, service restarts.
# Alarmo controls are restricted to its exact configured entity ID.


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
        if path == '/api/events':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache, no-transform')
            self.send_header('X-Accel-Buffering', 'no')
            self.end_headers()
            prev_states = prev_config = None
            try:
                for tick in range(900):
                    if tick % 2 == 0:
                        try:
                            snapshot = ha('GET', '/states')
                            raw = json.dumps(snapshot, separators=(',', ':'))
                            digest = hashlib.sha256(raw.encode()).hexdigest()
                            if prev_states != digest:
                                self.wfile.write(('event: states\ndata: ' + json.dumps({'states': snapshot}) + '\n\n').encode())
                                prev_states = digest
                        except (RuntimeError, HTTPError, URLError, TimeoutError):
                            self.wfile.write(b'event: offline\ndata: {}\n\n')
                    conf = read_prefs()
                    digest = hashlib.sha256(json.dumps(conf, sort_keys=True).encode()).hexdigest()
                    if prev_config != digest:
                        self.wfile.write(('event: config\ndata: ' + json.dumps({'config': conf}) + '\n\n').encode())
                        prev_config = digest
                    self.wfile.write(b': heartbeat\n\n')
                    self.wfile.flush()
                    time.sleep(2)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            return
        if path == '/api/config':
            return self.send_json(200, {'config': read_prefs()})
        if path.startswith('/api/bridge/'):
            action = path[len('/api/bridge/'):]
            if action not in BRIDGE_GET:
                return self.send_json(404, {'error':'Azione non consentita'})
            try:
                return self.send_json(200, bridge_request(action))
            except (ValueError, HTTPError, URLError, TimeoutError, OSError) as exc:
                logging.warning('Bridge read unavailable: %s', type(exc).__name__)
                return self.send_json(502, {'error': 'Bridge non raggiungibile o non configurato'})
        if path == '/api/health':
            return self.send_json(200, {'ok': True, 'name': 'Aveniq', 'ha_connected': bool(TOKEN)})
        if path == '/api/history':
            try:
                entity = parse_qs(urlsplit(self.path).query).get('entity_id', [''])[0]
                if entity != 'sensor.shellyemg3_b08184e86778_energy_meter_0_power':
                    return self.send_json(403, {'error': 'Entità non autorizzata'})
                from datetime import datetime, timedelta, timezone
                start = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                qs = urlencode({'filter_entity_id': entity, 'minimal_response': 'true', 'no_attributes': 'true'})
                data = ha('GET', '/history/period/' + start + '?' + qs)
                events = data[0] if isinstance(data, list) and data else []
                points = []
                for event in events:
                    try:
                        value = float(event.get('state', ''))
                        if value != value or abs(value) == float('inf'):
                            continue
                        points.append({'time': event.get('last_changed') or event.get('last_updated'), 'value': value})
                    except (ValueError, TypeError, AttributeError):
                        continue
                # Downsample to 180 samples to bound response size.
                step = max(1, (len(points) + 179) // 180)
                return self.send_json(200, {'points': points[::step][-180:]})
            except (RuntimeError, HTTPError, URLError, TimeoutError, ValueError) as ex:
                logging.warning('History error: %s', ex)
                return self.send_json(502, {'error': 'Storico non raggiungibile'})
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

    def read_post_body(self):
        """Read a bounded JSON request, including chunked bodies forwarded by Ingress."""
        limit = 8192
        transfer = self.headers.get('Transfer-Encoding', '').lower()
        if 'chunked' in transfer:
            body = bytearray()
            while True:
                line = self.rfile.readline(128)
                if not line or len(line) >= 128:
                    raise ValueError('Invalid chunk header')
                try:
                    size = int(line.split(b';', 1)[0].strip(), 16)
                except ValueError as exc:
                    raise ValueError('Invalid chunk size') from exc
                if size == 0:
                    # Consume trailers up to a conservative bound.
                    for _ in range(16):
                        trailer = self.rfile.readline(1024)
                        if trailer in (b'\r\n', b'\n'):
                            break
                        if not trailer or len(trailer) >= 1024:
                            raise ValueError('Invalid chunk trailer')
                    else:
                        raise ValueError('Too many chunk trailers')
                    break
                if size < 0 or len(body) + size > limit:
                    raise ValueError('Request too large')
                chunk = self.rfile.read(size)
                if len(chunk) != size or self.rfile.read(2) != b'\r\n':
                    raise ValueError('Incomplete chunk')
                body.extend(chunk)
            if not body:
                raise ValueError('Empty request')
            return bytes(body)

        length_header = self.headers.get('Content-Length')
        if length_header is None:
            raise ValueError('Missing request length')
        try:
            length = int(length_header)
        except ValueError as exc:
            raise ValueError('Invalid request length') from exc
        if length <= 0 or length > limit:
            raise ValueError('Invalid request size')
        body = self.rfile.read(length)
        if len(body) != length:
            raise ValueError('Incomplete request')
        return body

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ('/api/service', '/api/config') and not (path.startswith('/api/bridge/') and path[len('/api/bridge/'):] in BRIDGE_POST):
            return self.send_json(404, {'error': 'Not found'})
        if self.headers.get('Sec-Fetch-Site', 'same-origin') not in ('same-origin', 'none'):
            return self.send_json(403, {'error': 'Origin non consentita'})
        try:
            data = json.loads(self.read_post_body())
            if path.startswith('/api/bridge/'):
                action = path[len('/api/bridge/'):]
                if not isinstance(data, dict) or set(data) - {'id','root','page','page_size','search','group','title','poster'}:
                    return self.send_json(400, {'error':'Parametri bridge non validi'})
                try:
                    return self.send_json(200, bridge_request(action, data))
                except (ValueError, HTTPError, URLError, TimeoutError, OSError) as exc:
                    logging.warning('Bridge action unavailable: %s', type(exc).__name__)
                    return self.send_json(502, {'error':'Comando bridge non riuscito'})
            if path == '/api/config':
                save_prefs(data)
                return self.send_json(200, {'ok': True})
            domain, service = data['domain'], data['service']
            entity_id = data['entity_id']
            if not all(isinstance(x, str) for x in (domain, service, entity_id)):
                raise ValueError('Bad fields')
            if service not in ALLOWED.get(domain, ()) or (domain != 'kodi' and not entity_id.startswith(domain + '.')):
                return self.send_json(403, {'error': 'Comando non consentito'})
            extra = data.get('data', {})
            if domain == 'kodi':
                methods = {'Input.Up', 'Input.Down', 'Input.Left', 'Input.Right', 'Input.Select',
                           'Input.Back', 'Input.Home', 'Input.Info', 'Input.ContextMenu', 'Input.ShowOSD'}
                if service != 'call_method' or not isinstance(extra, dict) or set(extra) != {'method'} or extra['method'] not in methods or not entity_id.startswith('media_player.'):
                    return self.send_json(403, {'error': 'Comando Kodi non consentito'})
                current = next((a for a in ha('GET', '/states') if a.get('entity_id') == entity_id), None)
                if not current or 'kodi' not in (entity_id + ' ' + current.get('attributes', {}).get('friendly_name', '')).lower():
                    return self.send_json(403, {'error': 'Kodi non verificato'})
                ha('POST', '/services/kodi/call_method', {'entity_id': entity_id, **extra})
                return self.send_json(200, {'ok': True})
            if domain == 'lock':
                if entity_id != 'lock.porta_ingresso' or extra != {}:
                    return self.send_json(403, {'error': 'Comando serratura non consentito'})
                if service == 'open':
                    entity = next((s for s in ha('GET', '/states') if s.get('entity_id') == entity_id), None)
                    if entity is None or not (int(entity.get('attributes', {}).get('supported_features', 0)) & 1):
                        return self.send_json(403, {'error': 'Apertura non supportata'})
            if domain == 'alarm_control_panel':
                if entity_id != 'alarm_control_panel.alarmo':
                    return self.send_json(403, {'error': 'Entità antifurto non consentita'})
                if not isinstance(extra, dict) or any(k != 'code' for k in extra):
                    return self.send_json(400, {'error': 'Parametri Alarmo non validi'})
                if 'code' in extra and (not isinstance(extra['code'], str) or len(extra['code']) > 64):
                    return self.send_json(400, {'error': 'Codice non valido'})
            elif not isinstance(extra, dict) or any(k not in ('brightness_pct','rgb_color','temperature','hvac_mode','position','fan_mode','swing_mode') for k in extra):
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
