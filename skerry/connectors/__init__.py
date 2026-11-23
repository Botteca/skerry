"""Connectors: optional links to external services (Microsoft 365, Google Calendar, Azure Data Factory,
SQL Server / Azure SQL).

Each connector has: a state readable by the UI, sign-in/out started from settings, a polling thread,
and no credentials in settings.json (tokens live in `skerry.secrets`)."""
from .adf import ADF
from .google import Google
from .m365 import M365
from .sql import SQL


class Connectors:
    def __init__(self, settings, store):
        self.m365 = M365(settings, store)
        self.google = Google(settings, store)
        self.adf = ADF(settings, store)
        self.sql = SQL(settings, store)
        self._all = {"m365": self.m365, "google": self.google, "adf": self.adf, "sql": self.sql}

    def start(self):
        for c in self._all.values():
            c.start()

    def stop(self):
        for c in self._all.values():
            c.stop()

    def states(self):
        return {k: c.status() for k, c in self._all.items()}

    def get(self, cid):
        return self._all.get(cid)

    def meeting(self):
        """The meeting in progress or the next one, from Microsoft 365 and Google Calendar."""
        found = [m for m in (self.m365.meeting(), self.google.meeting()) if m]
        return min(found, key=lambda m: m["start"]) if found else None
