"""JSON adapter for the web server; secret hashes stay server-side."""
import json
import sys
from tools.benchmarks.core import public_view
from tools.benchmarks.storage import DriveStore


def dispatch(command, payload):
    store = DriveStore()
    if command == "benchmark-list":
        return {"reports": store.list_reports()}
    document = store.get(payload["id"])
    if command == "benchmark-passwords":
        from tools.benchmarks.access import report_passwords
        import hashlib
        import hmac
        passwords = report_passwords(payload["id"])
        for view, password in passwords.items():
            salt, stored = document["access"][view].split(":")
            digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
            if not hmac.compare_digest(stored, digest):
                raise ValueError("Password seed differs from the seed used for this snapshot")
        return passwords
    if command == "benchmark-access":
        return {"hash": document["access"][payload["view"]]}
    if command == "benchmark-read":
        return public_view(document, private=payload["view"] == "private")
    raise ValueError("Unknown benchmark command")
