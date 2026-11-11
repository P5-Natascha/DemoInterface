#!/usr/bin/env python3
"""Brücke: Browser (WebSocket) <-> Auto (UDP Joystick, TCP Telemetrie/Modus).

Zwei Webseiten in einem Prozess:
  Port 8080  öffentliche Steuerung (Zugang per ?key=...)
  Port 8081  Admin-Panel (Authentifizierung übernimmt Pangolin SSO davor)
"""
import asyncio, functools, json, os, re, secrets, signal, struct, time
from contextlib import aclosing
from pathlib import Path
import segno
import aiohttp
from aiohttp import web, WSMsgType

HERE      = Path(__file__).parent
CAR_IP    = os.getenv("CAR_IP", "127.0.0.1")
UDP_PORT  = int(os.getenv("CAR_UDP_PORT", "9005"))
TCP_PORT  = int(os.getenv("CAR_TCP_PORT", "9006"))
HTTP_PORT = int(os.getenv("PORT", "8080"))
ADMIN_PORT = int(os.getenv("ADMIN_PORT", "8081"))
PUBLIC_URL = os.getenv("PUBLIC_URL", "")       # z. B. https://car.example.com (für den QR-Code)
DATA      = Path(os.getenv("DATA_DIR", "data"))
CENTER, DEADMAN = 2048, 0.5                    # Mitte; Sekunden ohne Eingabe -> Stopp
GRACE = float(os.getenv("DISCONNECT_GRACE", "5"))  # Sekunden nach dem letzten Browser bis zum Trennen

# Das Auto meldet den Strom (AMPR) mit umgekehrtem Vorzeichen; 1 = hier einmal umdrehen
AMPR_INVERT = os.getenv("AMPR_INVERT", "1").lower() in ("1", "true", "yes")

# Kameras (laufen auf einem eigenen Port des Autos, unabhängig von UDP/TCP)
CAMERA_HOST = os.getenv("CAMERA_HOST") or CAR_IP
CAMERA_PORT = os.getenv("CAMERA_PORT") or "81"
FRONT_URL = os.getenv("CAMERA_FRONT_URL") or \
    f"http://{CAMERA_HOST}:{CAMERA_PORT}{os.getenv('CAMERA_FRONT_PATH') or '/camera/front_feed'}"
BACK_URL = os.getenv("CAMERA_BACK_URL") or \
    f"http://{CAMERA_HOST}:{CAMERA_PORT}{os.getenv('CAMERA_BACK_PATH') or '/camera/back_feed'}"
# raw = Stream des Autos Byte für Byte durchreichen (geringste Verzögerung)
# shared = ein gemeinsamer Abruf, Bilder werden zerlegt und an alle verteilt (überspringt Bilder bei langsamem Netz)
CAMERA_MODE = (os.getenv("CAMERA_MODE") or "raw").lower()
CAM_KEY = os.getenv("CAMERA_REQUIRE_KEY", "0").lower() in ("1", "true", "yes")  # Bild nur mit gültigem Key

cfg = {"token": "", "allowed": True, "camera": True}           # wird in data/settings.json gespeichert
state = {"tele": {}, "tcp": False, "pps": 0, "mode": 0}
joy = {"x": CENTER, "y": CENTER, "t": 0.0, "n": 99}
clients = {}        # WebSocket -> Key aus der URL
sent = 0
tcp_writer = None   # offene TCP-Verbindung zum Auto
resend = False      # Modus beim (Neu-)Verbinden sofort senden


# ---------- Einstellungen ----------
def save_cfg():
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        (DATA / "settings.json").write_text(json.dumps(cfg))
    except OSError as e:
        print(f"Einstellungen konnten nicht gespeichert werden: {e!r}", flush=True)


def load_cfg():
    try:
        d = json.loads((DATA / "settings.json").read_text())
    except (OSError, ValueError):
        d = {}
    cfg["token"] = d.get("token") or os.getenv("CONTROL_TOKEN") or secrets.token_urlsafe(16)
    cfg["allowed"] = bool(d.get("allowed", True))
    cfg["camera"] = bool(d.get("camera", True))
    save_cfg()


def can(key):
    """Darf dieser Key steuern? (Prüfung bei jeder Nachricht, damit ein neuer Key sofort wirkt.)"""
    return bool(key) and secrets.compare_digest(key.encode(), cfg["token"].encode())


def clamp(v):
    return max(0, min(4095, int(v)))


# ---------- Verbindung zum Auto ----------
async def udp_loop(tr):
    """Sendet 50x/s <HH an das Auto. Ohne Eingabe: 10x Mitte, dann Ruhe. Gesperrt: nichts."""
    global sent
    while True:
        await asyncio.sleep(0.02)
        if not cfg["allowed"]:
            continue
        if time.monotonic() - joy["t"] < DEADMAN:
            x, y, joy["n"] = joy["x"], joy["y"], 0
        elif joy["n"] < 10:
            x = y = CENTER
            joy["n"] += 1
        else:
            continue
        tr.sendto(struct.pack("<HH", x, y))
        sent += 1


async def read_telemetry(r):
    """Liest 'SDATA:KEY:wert' vom Auto, bis die Verbindung endet."""
    while line := await r.readline():
        parts = line.decode(errors="ignore").strip().split(":", 2)
        if len(parts) == 3 and parts[0] == "SDATA":
            try:
                v = float(parts[2])
                if parts[1] == "AMPR" and AMPR_INVERT:
                    v = -v + 0.0            # "+ 0.0" verhindert die Anzeige von -0
                state["tele"][parts[1]] = v
            except ValueError:
                pass


def wanted():
    """Verbindung nur, wenn ein Browser verbunden ist UND der Admin sie nicht gesperrt hat."""
    return bool(clients) and cfg["allowed"]


async def unwanted_for(seconds):
    """Endet sofort bei Sperre, sonst wenn `seconds` lang kein Browser mehr verbunden war."""
    since = None
    while True:
        await asyncio.sleep(0.2)
        if not cfg["allowed"]:
            return
        if clients:
            since = None
        elif since is None:
            since = time.monotonic()
        elif time.monotonic() - since >= seconds:
            return


async def tcp_loop():
    global tcp_writer, resend
    last_err = None
    while True:
        while not wanted():
            await asyncio.sleep(0.2)
        try:
            r, w = await asyncio.wait_for(asyncio.open_connection(CAR_IP, TCP_PORT), 5)
        except (OSError, asyncio.TimeoutError) as e:
            if last_err != repr(e):
                last_err = repr(e)
                print(f"TCP {CAR_IP}:{TCP_PORT} nicht erreichbar: {e!r}", flush=True)
            await asyncio.sleep(2)
            continue
        last_err = None
        print(f"TCP verbunden mit {CAR_IP}:{TCP_PORT}", flush=True)
        state["tcp"], tcp_writer, resend = True, w, True
        tasks = [asyncio.create_task(read_telemetry(r)),
                 asyncio.create_task(unwanted_for(GRACE))]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                t.cancel()
                if t.done() and not t.cancelled():
                    t.exception()
            tcp_writer = None
            state["tcp"], state["tele"] = False, {}
            try:
                w.write(b"mode:0\r\n")           # erst Modus 0, dann trennen
                await w.drain()
                await asyncio.sleep(0.2)          # dem Auto Zeit geben, den Modus zu übernehmen
            except OSError:
                pass
            w.close()
        print("TCP getrennt", flush=True)
        if wanted():
            await asyncio.sleep(2)


async def mode_loop():
    """Meldet dem Auto per TCP den Modus:
    1 = jemand fährt, 4 = Website aktiv (niemand fährt), 0 = niemand da oder gesperrt.
    Bei Modus 0 sendet das Auto kein TCP mehr, deshalb wird 0 nur kurz vor dem Trennen genutzt."""
    global resend
    last, last_t = None, 0.0
    while True:
        await asyncio.sleep(0.05)
        now = time.monotonic()
        if not cfg["allowed"]:
            mode = 0
        elif now - joy["t"] < DEADMAN:
            mode = 1
        elif clients:
            mode = 4
        else:
            mode = 0
        state["mode"] = mode
        if tcp_writer and (mode != last or resend or now - last_t > 1.0):
            try:
                tcp_writer.write(f"mode:{mode}\r\n".encode())
                await tcp_writer.drain()
                last, last_t, resend = mode, now, False
            except OSError:
                pass


async def broadcast_loop():
    global sent
    tick = 0
    while True:
        await asyncio.sleep(0.1)
        tick += 1
        if tick % 10 == 0:
            state["pps"], sent = sent, 0
        for ws, key in list(clients.items()):
            cam = {"allowed": cfg["camera"] and (not CAM_KEY or can(key)), "disabled": not cfg["camera"],
                   "front": CAMS["front"].ok, "back": CAMS["back"].ok}
            try:
                await ws.send_json({**state, "ctrl": can(key), "blocked": not cfg["allowed"], "cam": cam})
            except ConnectionError:
                pass


# ---------- Kameras ----------
class Cam:
    def __init__(self, name, url):
        self.name, self.url = name, url
        self.subs = set()    # Warteschlangen der Browser, die zuschauen
        self.frame = None    # letztes Bild
        self.ok = False      # kommt gerade Bild vom Auto?
        self.last = 0.0      # Zeitpunkt der letzten Daten (nur Modus raw)


CAMS = {"front": Cam("front", FRONT_URL), "back": Cam("back", BACK_URL)}


def cam_wanted():
    """Bilder nur holen, solange ein Browser verbunden ist und der Admin die Kamera nicht deaktiviert hat."""
    return bool(clients) and cfg["camera"]


async def mjpeg_frames(resp):
    """Zerlegt einen MJPEG-Stream (multipart/x-mixed-replace) in einzelne JPEG-Bilder."""
    ctype = resp.headers.get("Content-Type", "")
    m = re.search(r'boundary="?([^";\s]+)', ctype)
    if "multipart" not in ctype or not m:
        raise ValueError(f"kein MJPEG-Stream (Content-Type: {ctype!r})")
    marker = b"--" + m.group(1).lstrip("-").encode()
    buf = b""
    async for chunk in resp.content.iter_any():
        buf += chunk
        while True:
            i = buf.find(marker)
            if i < 0:
                buf = buf[-len(marker):]
                break
            h_end = buf.find(b"\r\n\r\n", i)
            if h_end < 0:
                buf = buf[i:]
                break
            start = h_end + 4
            cl = re.search(rb"content-length:\s*(\d+)", buf[i:h_end], re.I)
            if cl:                                   # Länge bekannt: Bild sofort ausliefern
                end = start + int(cl.group(1))
                if len(buf) < end:
                    buf = buf[i:]
                    break
                body, buf = buf[start:end], buf[end:]
            else:                                    # keine Länge (z. B. Flask/OpenCV): Bildende suchen
                k = buf.find(b"\xff\xd9\r\n", start)  # Bild sofort ausliefern, nicht erst bei der nächsten Grenze
                j = buf.find(marker, start)
                if k >= 0 and (j < 0 or k < j):
                    body, buf = buf[start:k + 2], buf[k + 4:]
                elif j >= 0:
                    body, buf = buf[start:j], buf[j:]
                else:
                    buf = buf[i:]
                    break
            k = body.rfind(b"\xff\xd9")
            if body.startswith(b"\xff\xd8") and k > 0:
                yield body[:k + 2]
        if len(buf) > 4_000_000:
            raise ValueError("Bild zu groß oder Stream defekt")


async def cam_loop(cam):
    """Holt den Stream des Autos, solange cam_wanted() gilt, und verteilt die Bilder an alle Zuschauer."""
    timeout = aiohttp.ClientTimeout(total=None, connect=5, sock_read=10)
    last_err = None
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        while True:
            while not cam_wanted():
                await asyncio.sleep(0.3)
            try:
                async with sess.get(cam.url) as resp:
                    if resp.status != 200:
                        raise ValueError(f"HTTP {resp.status}")
                    async with aclosing(mjpeg_frames(resp)) as frames:
                        async for frame in frames:
                            if not cam.ok:
                                print(f"Kamera {cam.name} liefert Bilder", flush=True)
                            cam.ok, cam.frame, last_err = True, frame, None
                            for q in cam.subs:
                                if q.full():
                                    q.get_nowait()
                                q.put_nowait(frame)
                            if not cam_wanted():
                                break
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError) as e:
                if last_err != repr(e):
                    last_err = repr(e)
                    print(f"Kamera {cam.name} ({cam.url}): {e!r}", flush=True)
            cam.ok, cam.frame = False, None
            if cam_wanted():
                await asyncio.sleep(2)


async def raw_watch():
    """Modus raw: markiert eine Kamera als aktiv, solange Daten ankommen."""
    while True:
        await asyncio.sleep(0.5)
        for c in CAMS.values():
            c.ok = time.monotonic() - c.last < 3


async def cam_raw(req, cam):
    """Reicht den Stream des Autos Byte für Byte an den Browser durch: kein Zwischenspeicher, keine Neuverpackung."""
    timeout = aiohttp.ClientTimeout(total=None, connect=5, sock_read=10)
    token, resp, last_err = object(), None, None
    cam.subs.add(token)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            while cam_wanted():
                try:
                    async with sess.get(cam.url) as up:
                        if up.status != 200:
                            raise ValueError(f"HTTP {up.status}")
                        if resp is None:
                            resp = web.StreamResponse(headers={
                                "Content-Type": up.headers.get("Content-Type", "multipart/x-mixed-replace; boundary=frame"),
                                "Cache-Control": "no-store"})
                            await resp.prepare(req)
                        last_err = None
                        async for chunk in up.content.iter_any():
                            cam.last = time.monotonic()
                            await resp.write(chunk)
                            if not cam_wanted():
                                break
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError) as e:
                    if req.transport is None or req.transport.is_closing():
                        break                                   # Browser ist weg
                    if last_err != repr(e):
                        last_err = repr(e)
                        print(f"Kamera {cam.name} ({cam.url}): {e!r}", flush=True)
                if cam_wanted() and not (req.transport is None or req.transport.is_closing()):
                    await asyncio.sleep(2)
                else:
                    break
    finally:
        cam.subs.discard(token)
    if resp is None:
        raise web.HTTPBadGateway()
    return resp


async def cam_stream(req):
    """Gibt den gemeinsamen Kamerastream an einen Browser weiter (<img src="/camera/front">)."""
    cam = CAMS.get(req.match_info["name"])
    if cam is None:
        raise web.HTTPNotFound()
    if not cfg["camera"] or (CAM_KEY and not can(req.query.get("key", ""))):
        raise web.HTTPForbidden()
    if CAMERA_MODE == "raw":
        return await cam_raw(req, cam)
    resp = web.StreamResponse(headers={
        "Content-Type": "multipart/x-mixed-replace; boundary=frame", "Cache-Control": "no-store"})
    await resp.prepare(req)
    q = asyncio.Queue(maxsize=2)
    cam.subs.add(q)
    try:
        if cam.frame:
            q.put_nowait(cam.frame)
        while cfg["camera"]:
            try:
                frame = await asyncio.wait_for(q.get(), 2)
            except asyncio.TimeoutError:
                continue
            await resp.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(frame)
                             + frame + b"\r\n")
    except ConnectionError:
        pass
    finally:
        cam.subs.discard(q)
    return resp


def cam_coros():
    return [raw_watch()] if CAMERA_MODE == "raw" else [cam_loop(c) for c in CAMS.values()]


# ---------- Öffentliche Seite (Port 8080) ----------
async def ws_handler(req):
    ws = web.WebSocketResponse(heartbeat=15)
    await ws.prepare(req)
    key = req.query.get("key", "")
    clients[ws] = key
    try:
        async for m in ws:
            if m.type == WSMsgType.TEXT and can(key):
                try:
                    d = json.loads(m.data)
                    joy.update(x=clamp(d["x"]), y=clamp(d["y"]), t=time.monotonic())
                except (ValueError, KeyError, TypeError):
                    pass
    finally:
        clients.pop(ws, None)
    return ws


def public_app():
    app = web.Application()
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/camera/{name}", cam_stream)
    app.router.add_get("/", lambda r: web.FileResponse(HERE / "index.html"))
    return app


# ---------- Admin-Panel (Port 8081, Login macht Pangolin davor) ----------
@functools.lru_cache(maxsize=4)
def qr_svg(url):
    return segno.make(url, error="m").svg_inline(scale=1, border=2, omitsize=True, dark="#14181f", light="#ffffff")


def admin_state(req):
    base = (PUBLIC_URL or f"http://{req.host.rsplit(':', 1)[0]}:{HTTP_PORT}").rstrip("/")
    url = f"{base}/?key={cfg['token']}"
    return {"key": cfg["token"], "url": url, "qr": qr_svg(url), "allowed": cfg["allowed"],
            "tcp": state["tcp"], "mode": state["mode"], "pps": state["pps"],
            "clients": len(clients), "drivers": sum(can(k) for k in clients.values()),
            "car": f"{CAR_IP}:{TCP_PORT}", "camera": cfg["camera"],
            "cam_front": CAMS["front"].ok, "cam_back": CAMS["back"].ok,
            "cam_viewers": sum(len(c.subs) for c in CAMS.values())}


@web.middleware
async def csrf_guard(req, handler):
    """Schreibende Aufrufe nur mit eigenem Header (verhindert Aufrufe von fremden Webseiten)."""
    if req.method != "GET" and req.headers.get("X-Admin") != "1":
        raise web.HTTPForbidden()
    return await handler(req)


async def api_state(req):
    return web.json_response(admin_state(req))


async def api_key(req):
    cfg["token"] = secrets.token_urlsafe(16)
    save_cfg()
    return web.json_response(admin_state(req))


async def api_car(req):
    try:
        cfg["allowed"] = bool((await req.json())["allowed"])
    except (ValueError, KeyError, TypeError):
        raise web.HTTPBadRequest()
    save_cfg()
    return web.json_response(admin_state(req))


async def api_camera(req):
    try:
        cfg["camera"] = bool((await req.json())["allowed"])
    except (ValueError, KeyError, TypeError):
        raise web.HTTPBadRequest()
    save_cfg()
    return web.json_response(admin_state(req))


def admin_app():
    app = web.Application(middlewares=[csrf_guard])
    app.router.add_get("/", lambda r: web.FileResponse(HERE / "admin.html"))
    app.router.add_get("/api/state", api_state)
    app.router.add_post("/api/key", api_key)
    app.router.add_post("/api/car", api_car)
    app.router.add_post("/api/camera", api_camera)
    return app


# ---------- Start ----------
async def main():
    load_cfg()
    loop = asyncio.get_running_loop()
    tr, _ = await loop.create_datagram_endpoint(
        asyncio.DatagramProtocol, remote_addr=(CAR_IP, UDP_PORT))
    tasks = [asyncio.create_task(c) for c in (udp_loop(tr), tcp_loop(), mode_loop(), broadcast_loop(), *cam_coros())]
    runners = []
    for app, port in ((public_app(), HTTP_PORT), (admin_app(), ADMIN_PORT)):
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", port).start()
        runners.append(runner)
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    print(f"Öffentlich: Port {HTTP_PORT} | Admin: Port {ADMIN_PORT} | Auto: {CAR_IP}", flush=True)
    await stop.wait()
    for t in tasks:
        t.cancel()
    for ws in list(clients):
        await ws.close()
    for r in runners:
        await r.cleanup()
    tr.close()


if __name__ == "__main__":
    asyncio.run(main())
