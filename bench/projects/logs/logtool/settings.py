"""Thresholds and display settings for the access-log report."""

THRESHOLDS = {
    "slow_ms": 800,
    "very_slow_ms": 1500,
    "error_rate_warn": 0.10,
    "error_rate_alert": 0.25,
}

PERCENTILES = (50, 90, 99)

TOP_N = 5

HISTOGRAM_BUCKETS_MS = (50, 100, 250, 500, 1000, 2000)

STATIC_PREFIXES = ("/static/", "/favicon")

BOT_MARKERS = ("bot", "crawler", "spider")

COLUMN_WIDTHS = {
    "path": 22,
    "count": 7,
    "ms": 9,
}
