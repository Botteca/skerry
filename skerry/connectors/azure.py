"""Azure access tokens for connectors, two ways:

- "az": the Azure CLI account of the user (`az login` once; Skerry runs `az account get-access-token`);
- "sp": a service principal: tenant and client id in settings, the client secret encrypted in `skerry.secrets`.

Tokens are cached in memory until 5 minutes before they expire. Every call has a timeout.
"""
import json
import logging
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .. import secrets
from ..i18n import Msg

log = logging.getLogger("skerry")

LOGIN = "https://login.microsoftonline.com"   # replaced by a fake server in tests
TIMEOUT = 20
NO_WINDOW = 0x08000000                         # CREATE_NO_WINDOW: no console flash when running az
_cache = {}
_lock = threading.Lock()


class AzureError(Exception):
    """An error to show in settings: `msg` is a translatable `Msg` or plain text."""

    def __init__(self, msg):
        super().__init__(str(msg))
        self.msg = msg


def http_error(e):
    """Short message from an Azure HTTPError body ({"error": {"message"}} or {"error_description"})."""
    try:
        body = json.load(e)
    except Exception:
        return ""
    err = body.get("error")
    text = err.get("message") if isinstance(err, dict) else body.get("error_description") or err or ""
    return str(text).splitlines()[0][:160] if text else ""


def _az(resource, tenant):
    exe = shutil.which("az")
    if not exe:
        raise AzureError(Msg("azure.no_cli"))
    args = [exe, "account", "get-access-token", "--resource", resource, "--output", "json"]
    if tenant:
        args += ["--tenant", tenant]
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=45,
                           creationflags=NO_WINDOW if hasattr(subprocess, "STARTUPINFO") else 0)
    except subprocess.TimeoutExpired:
        raise AzureError(Msg("azure.cli_timeout")) from None
    if r.returncode != 0:
        lines = [x for x in (r.stderr or "").splitlines() if x.strip()]
        raise AzureError(Msg("azure.cli_failed", message=(lines[-1] if lines else "")[:160]))
    d = json.loads(r.stdout)
    return d["accessToken"], float(d.get("expires_on") or time.time() + 1800)


def _sp(resource, tenant, client_id, secret_name):
    secret = secrets.load(secret_name)
    if not (tenant and client_id and secret):
        raise AzureError(Msg("azure.sp_incomplete"))
    data = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": client_id,
                                   "client_secret": secret, "scope": resource.rstrip("/") + "/.default"}).encode()
    req = urllib.request.Request(f"{LOGIN}/{urllib.parse.quote(tenant)}/oauth2/v2.0/token", data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        raise AzureError(Msg("azure.sign_in_failed", message=http_error(e))) from None
    return d["access_token"], time.time() + float(d.get("expires_in") or 3600)


def token(auth, resource, tenant="", client_id="", secret_name=""):
    """Access token for `resource` (e.g. https://management.azure.com/). Raises AzureError."""
    key = (auth, resource, tenant, client_id, secret_name)
    with _lock:
        hit = _cache.get(key)
    if hit and hit[1] - 300 > time.time():
        return hit[0]
    tok = _sp(resource, tenant, client_id, secret_name) if auth == "sp" else _az(resource, tenant)
    with _lock:
        _cache[key] = tok
    return tok[0]


def forget():
    """Drop cached tokens (after the secret or the sign-in method changes)."""
    with _lock:
        _cache.clear()
