"""Connectors: optional links to external services (Microsoft 365, Azure Data Factory, SQL Server / Azure SQL).

Each connector has: a state readable by the UI, sign-in/out started from settings, a polling thread,
and no credentials in settings.json (tokens live in `skerry.secrets`)."""
from .adf import ADF
from .m365 import M365
from .sql import SQL


class Connectors:
    def __init__(self, settings, store):
        self.m365 = M365(settings, store)
        self.adf = ADF(settings, store)
        self.sql = SQL(settings, store)
        self._all = {"m365": self.m365, "adf": self.adf, "sql": self.sql}

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
        return self.m365.meeting()
