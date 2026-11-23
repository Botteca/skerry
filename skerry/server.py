"""Local HTTP server (127.0.0.1 only) for agent hooks and the status line."""
import logging
import threading

from flask import Flask, jsonify, request
from werkzeug.serving import make_server

from . import agents

log = logging.getLogger("skerry")

MAX_BODY = 1024 * 1024          # hook payloads are a few KB; refuse anything absurd
LOCAL_HOSTS = {"127.0.0.1", "localhost"}


def _refused():
    """Why a request must be refused, or None. Agents (skerry-cli, Claude Code, Codex) never send an Origin or
    Sec-Fetch-* header; browsers always do. A Host other than the loopback name means DNS rebinding."""
    if request.headers.get("Origin") is not None or request.headers.get("Sec-Fetch-Site") is not None:
        return "browser request"
    host = (request.host or "").rsplit(":", 1)[0].strip("[]").lower()
    if host not in LOCAL_HOSTS:
        return f"foreign Host {host!r}"
    if request.method == "POST" and request.mimetype != "application/json":
        return "not JSON"
    return None


def create_app(store, settings, on_show=None):
    app = Flask("skerry")
    app.config["MAX_CONTENT_LENGTH"] = MAX_BODY
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    @app.before_request
    def guard():
        if (request.content_length or 0) > MAX_BODY:
            log.warning("Refused %s %s: body too large", request.method, request.path)
            return jsonify({}), 413
        why = _refused()
        if why:
            log.warning("Refused %s %s: %s", request.method, request.path, why)
            return jsonify({}), 403

    @app.post("/hook/<event>")
    def hook(event):
        payload = request.get_json(silent=True) or {}
        agent = request.args.get("agent", "claude")
        ev = payload.get("hook_event_name") or event
        if not settings.get(f"modules.{agent}", True):
            return jsonify({})
        try:
            ev, payload = agents.normalize(agent, ev, payload)
            if ev is None:
                return jsonify({})
            if ev == "PermissionRequest" and agent not in agents.ACTIVITY_ONLY:
                out = store.request_permission(payload, settings.get("permission_wait", 300), agent)
                return jsonify(agents.reply(agent, out))
            store.handle(ev, payload, agent)
        except Exception:
            log.exception("Error handling event %s", ev)
        return jsonify({})

    @app.post("/statusline")
    def statusline():
        try:
            store.statusline(request.get_json(silent=True) or {})
        except Exception:
            log.exception("Status line error")
        return jsonify({})

    @app.post("/ui/show")
    def show():
        if on_show:
            on_show()
        return jsonify({"ok": True})

    @app.get("/health")
    def health():
        from . import VERSION
        return jsonify({"ok": True, "version": VERSION})

    return app


def start_server(store, settings, on_show=None):
    app = create_app(store, settings, on_show)
    srv = make_server("127.0.0.1", int(settings.get("port", 47800)), app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True, name="http").start()
    return srv
