"""Rotating file log: %LOCALAPPDATA%\\Skerry\\logs\\skerry.log"""
import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler

from . import paths


def setup(name="skerry", filename="skerry.log"):
    logger = logging.getLogger("skerry")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fh = RotatingFileHandler(os.path.join(paths.log_dir(), filename), maxBytes=1_000_000,
                             backupCount=5, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s [%(threadName)s] %(message)s"))
    logger.addHandler(fh)
    if not paths.FROZEN:
        # in development the log also goes to the project folder (logs/skerry.log)
        dev_dir = os.path.join(paths.resource_dir(), "logs")
        os.makedirs(dev_dir, exist_ok=True)
        dh = RotatingFileHandler(os.path.join(dev_dir, filename), maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        dh.setFormatter(fh.formatter)
        logger.addHandler(dh)
    if sys.stderr and getattr(sys.stderr, "isatty", lambda: False)():
        logger.addHandler(logging.StreamHandler())

    def excepthook(exc_type, exc, tb):
        logger.critical("Eccezione non gestita", exc_info=(exc_type, exc, tb))

    def thread_excepthook(args):
        logger.error("Eccezione nel thread %s", args.thread.name if args.thread else "?",
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook
    return logger
