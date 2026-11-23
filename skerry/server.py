"""Local HTTP server (127.0.0.1 only) for agent hooks and the status line."""
import logging
import threading

from flask import Flask, jsonify, request
from werkzeug.serving import make_server

log = logging.getLogger("skerry")


def create_app(store, settings, on_show=None):
    app = Flask("skerry")
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    @app.post("/hook/<event>")
    def hook(event):
        payload = request.get_json(silent=True) or {}
        agent = request.args.get("agent", "claude")
        ev = payload.get("hook_event_name") or event
        if not settings.get(f"modules.{agent}", True):
            return jsonify({})
        try:
            if ev == "PermissionRequest":
                return jsonify(store.request_permission(payload, settings.get("permission_wait", 300), agent))
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
