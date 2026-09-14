"""Deterministic per-report passphrases. Root secret never leaves server."""
import hashlib
import hmac
import os
from tools.benchmarks.core import REPORT_ID


def report_passwords(report_id):
    if not REPORT_ID.fullmatch(report_id):
        raise ValueError("Invalid report ID")
    root = os.environ.get("BENCHMARK_PASSWORD_SEED", "")
    if len(root) < 32:
        raise ValueError("BENCHMARK_PASSWORD_SEED must contain at least 32 characters")
    return {view: f"{'Review' if view == 'private' else 'Share'}-{hmac.new(root.encode(), (report_id + ':' + view).encode(), hashlib.sha256).hexdigest()[:12]}" for view in ("private", "share")}
