#!/usr/bin/env python3
"""Send sample events to the running intake API using only the Python standard library."""

from __future__ import annotations

import json
import os
import urllib.request


API_URL = os.getenv("LEAD_FILTER_API_URL", "http://localhost:8000/events")
API_KEY = os.getenv("INGEST_API_KEY", "development-key")

EVENTS = [
    {
        "source": "demo",
        "source_message_id": "demo-001",
        "group_name": "Frisco Neighbors",
        "author": "Sample User",
        "text": "Can anyone recommend a realtor? We are moving to Frisco and want to buy a home.",
        "post_url": "https://example.com/posts/demo-001"
    },
    {
        "source": "demo",
        "source_message_id": "demo-002",
        "group_name": "Dallas Homeowners",
        "author": "Sample User",
        "text": "Need a licensed roofer ASAP before closing. Who do you recommend?",
        "post_url": "https://example.com/posts/demo-002"
    },
    {
        "source": "demo",
        "source_message_id": "demo-003",
        "group_name": "Neighborhood Chat",
        "author": "Sample User",
        "text": "I already found someone and am no longer looking for a contractor.",
        "post_url": "https://example.com/posts/demo-003"
    }
]


for event in EVENTS:
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(event).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        print(response.read().decode("utf-8"))

