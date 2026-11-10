#!/usr/bin/env python3
"""Brücke: Browser (WebSocket) <-> Auto (UDP Joystick, TCP Telemetrie/Modus).

Zwei Webseiten in einem Prozess:
  Port 8080  öffentliche Steuerung (Zugang per ?key=...)
  Port 8081  Admin-Panel (Authentifizierung übernimmt Pangolin SSO davor)
"""
import asyncio, functools, json, os, secrets, signal, struct, time
from pathlib import Path
import segno
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

cfg = {"token": "", "allowed": True}           # wird in data/settings.json gespeichert
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
                state["tele"][parts[1]] = float(parts[2])
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
            try:
                await ws.send_json({**state, "ctrl": can(key), "blocked": not cfg["allowed"]})
            except ConnectionError:
                pass


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
            "car": f"{CAR_IP}:{TCP_PORT}"}


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


def admin_app():
    app = web.Application(middlewares=[csrf_guard])
    app.router.add_get("/", lambda r: web.FileResponse(HERE / "admin.html"))
    app.router.add_get("/api/state", api_state)
    app.router.add_post("/api/key", api_key)
    app.router.add_post("/api/car", api_car)
    return app


# ---------- Start ----------
async def main():
    load_cfg()
    loop = asyncio.get_running_loop()
    tr, _ = await loop.create_datagram_endpoint(
        asyncio.DatagramProtocol, remote_addr=(CAR_IP, UDP_PORT))
    tasks = [asyncio.create_task(c) for c in (udp_loop(tr), tcp_loop(), mode_loop(), broadcast_loop())]
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
