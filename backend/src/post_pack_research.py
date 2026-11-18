"""Niche research for post packs: what similar, well-performing YouTube videos use.

Uses the YouTube Data API when a key is configured (``YOUTUBE_DATA_API_KEY`` or
``GOOGLE_API_KEY``), otherwise a free yt-dlp search. Either way the result is the
same small, JSON-safe dict, so the generator never cares where it came from.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
import yt_dlp

from .config import get_config

logger = logging.getLogger(__name__)

SEARCH_RESULTS = 15
DETAILED_RESULTS = 6
REQUEST_TIMEOUT_SECONDS = 15
HASHTAG_RE = re.compile(r"#([\w\d_]{2,40})", re.UNICODE)


def _hashtags_in(text: str) -> List[str]:
    return [tag.lower() for tag in HASHTAG_RE.findall(text or "")]


def _summarise(videos: List[Dict[str, Any]], source: str) -> Dict[str, Any]:
    """Weight each tag and hashtag by the views of the videos that use it."""
    videos = sorted(videos, key=lambda v: v.get("views") or 0, reverse=True)
    tag_weight: Counter[str] = Counter()
    hashtag_weight: Counter[str] = Counter()
    for video in videos:
        weight = max(1, int(video.get("views") or 0))
        for tag in {t.strip().lower() for t in video.get("tags") or [] if t and t.strip()}:
            tag_weight[tag] += weight
        for tag in set(video.get("hashtags") or []):
            hashtag_weight[tag] += weight
    return {
        "source": source,
        "videos": [
            {
                "title": v.get("title") or "",
                "channel": v.get("channel") or "",
                "views": int(v.get("views") or 0),
            }
            for v in videos[:10]
        ],
        "top_tags": [t for t, _ in tag_weight.most_common(25)],
        "top_hashtags": [t for t, _ in hashtag_weight.most_common(15)],
    }


def _research_with_data_api(query: str, api_key: str, exclude_id: Optional[str]) -> Dict[str, Any]:
    published_after = (datetime.now(timezone.utc) - timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%SZ")
    search = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "key": api_key, "part": "id", "q": query, "type": "video",
            "order": "viewCount", "maxResults": SEARCH_RESULTS, "publishedAfter": published_after,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    search.raise_for_status()
    ids = [
        item["id"]["videoId"] for item in search.json().get("items", [])
        if item.get("id", {}).get("videoId") and item["id"]["videoId"] != exclude_id
    ]
    if not ids:
        return _summarise([], "youtube_data_api")
    details = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"key": api_key, "part": "snippet,statistics", "id": ",".join(ids)},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    details.raise_for_status()
    videos = []
    for item in details.json().get("items", []):
        snippet = item.get("snippet", {})
        videos.append({
            "title": snippet.get("title"),
            "channel": snippet.get("channelTitle"),
            "views": int(item.get("statistics", {}).get("viewCount") or 0),
            "tags": snippet.get("tags") or [],
            "hashtags": _hashtags_in(f"{snippet.get('title', '')} {snippet.get('description', '')}"),
        })
    return _summarise(videos, "youtube_data_api")


def _research_with_ytdlp(query: str, exclude_id: Optional[str]) -> Dict[str, Any]:
    base_opts = {"quiet": True, "no_warnings": True, "skip_download": True, "socket_timeout": REQUEST_TIMEOUT_SECONDS}
    with yt_dlp.YoutubeDL({**base_opts, "extract_flat": True}) as ydl:
        found = ydl.extract_info(f"ytsearch{SEARCH_RESULTS}:{query}", download=False) or {}
    entries = [e for e in found.get("entries") or [] if e and e.get("id") and e.get("id") != exclude_id]
    entries.sort(key=lambda e: e.get("view_count") or 0, reverse=True)

    videos: List[Dict[str, Any]] = []
    with yt_dlp.YoutubeDL(base_opts) as ydl:
        for entry in entries:
            video = {
                "title": entry.get("title"),
                "channel": entry.get("channel") or entry.get("uploader"),
                "views": entry.get("view_count") or 0,
                "tags": [],
                "hashtags": _hashtags_in(entry.get("title") or ""),
            }
            # Tags and descriptions need a full lookup; only do it for the top few.
            if len([v for v in videos if v["tags"]]) < DETAILED_RESULTS:
                try:
                    info = ydl.extract_info(f"https://www.youtube.com/watch?v={entry['id']}", download=False) or {}
                    video["tags"] = info.get("tags") or []
                    video["hashtags"] = _hashtags_in(f"{info.get('title', '')} {info.get('description', '')}")
                    video["views"] = info.get("view_count") or video["views"]
                    video["channel"] = info.get("channel") or info.get("uploader") or video["channel"]
                except Exception as exc:  # one private or age-gated video must not sink the rest
                    logger.info("Post pack research skipped %s: %s", entry.get("id"), exc)
            videos.append(video)
    return _summarise(videos, "yt_dlp_search")


def research_niche(query: str, exclude_id: Optional[str] = None) -> Dict[str, Any]:
    """Blocking. Return titles, view counts, tags and hashtags of similar videos.

    Never raises: a research failure yields an empty summary and the generator
    still writes copy from the clip alone.
    """
    query = (query or "").strip()[:200]
    if not query:
        return _summarise([], "none")
    api_key = get_config().resolve_youtube_data_api_key()
    if api_key:
        try:
            return _research_with_data_api(query, api_key, exclude_id)
        except Exception as exc:
            logger.warning("YouTube Data API research failed, falling back to yt-dlp: %s", exc)
    try:
        return _research_with_ytdlp(query, exclude_id)
    except Exception as exc:
        logger.warning("Post pack research failed for %r: %s", query, exc)
        return _summarise([], "failed")
