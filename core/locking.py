# SPDX-License-Identifier: AGPL-3.0-only
# This file is part of Agent Decisions Dashboard and is licensed under GNU AGPLv3 with Additional Terms (see LICENSE and LICENSE-ADDITIONAL_TERMS-zh-CN.md; ref: LICENSE-ADDITIONAL_TERMS-en.md).
"""Serialize in-process ledger mutations across service instances for one database."""
import os
import threading
from functools import wraps
from pathlib import Path

_locks = {}
_registry_lock = threading.Lock()


def ledger_lock(database_path):
    key = os.path.normcase(str(Path(database_path).resolve()))
    with _registry_lock:
        return _locks.setdefault(key, threading.RLock())


def serialized(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with ledger_lock(self.config.database_path):
            return method(self, *args, **kwargs)
    return wrapped
