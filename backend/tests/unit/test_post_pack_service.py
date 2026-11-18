import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import post_pack_research as research
from src.services import post_pack_service as packs
from src.services.post_pack_service import PostPackDraft, finalize_pack

RESEARCH = {
    "source": "yt_dlp_search",
    "videos": [{"title": "Similar video", "channel": "Someone", "views": 1000}],
    "top_tags": ["gta 6", "gta 6 ultimate edition"],
    "top_hashtags": ["gta6"],
}


def _draft(**overrides):
    fields = {
        "titles": ["One", "Two", "Three"],
        "description": "Hook line. Why to watch. Follow for more.",
        "hashtags": ["gta6", "gta6"],
        "tags": ["gta 6"],
    }
    fields.update(overrides)
    return PostPackDraft(**fields)


def test_finalize_enforces_youtube_limits():
    draft = _draft(
        titles=['"A #very good title"', "a #very good title", "x" * 150, "Fourth"],
        hashtags=["#GTA 6!", "gta6ultimate", "#shorts", "a", "b", "c", "d"],
        tags=["tag, with comma", "Tag, with comma"] + [f"tag number {i}" for i in range(60)],
    )
    pack = finalize_pack(draft, source_title="Src", source_url=None, channel=None, research=RESEARCH)

    assert pack["titles"] == ["A very good title", "x" * 100, "Fourth"]
    assert pack["hashtags"][-1] == "Shorts"
    assert len(pack["hashtags"]) == 5
    assert pack["hashtags"][0] == "GTA6"
    assert "shorts" not in [h.lower() for h in pack["hashtags"][:-1]]
    assert pack["tags"][0] == "tag with comma"
    assert len([t for t in pack["tags"] if t.lower() == "tag with comma"]) == 1
    # YouTube counts quotes around multi-word tags and separators toward its 500-character cap.
    cost = sum(len(t) + (2 if " " in t else 0) for t in pack["tags"]) + len(pack["tags"]) - 1
    assert cost <= 480


def test_finalize_adds_credit_and_hashtags_to_description():
    pack = finalize_pack(
        _draft(), source_title="Original", source_url="https://www.youtube.com/watch?v=h_xSOMtPCYI",
        channel="Hubi", research=RESEARCH,
    )
    assert pack["description"].startswith("Hook line.")
    assert "Source: Original by Hubi\nhttps://www.youtube.com/watch?v=h_xSOMtPCYI" in pack["description"]
    assert pack["description"].endswith("#gta6 #Shorts")
    assert pack["research"] == {"source": "yt_dlp_search", "videos": RESEARCH["videos"]}


def test_finalize_without_source_has_no_credit():
    pack = finalize_pack(_draft(), source_title="", source_url=None, channel=None, research=RESEARCH)
    assert "Source:" not in pack["description"]


async def test_generate_grounds_prompt_in_clip_and_research(monkeypatch):
    run = AsyncMock(return_value=SimpleNamespace(output=_draft()))
    monkeypatch.setattr(packs, "_get_agent", lambda: SimpleNamespace(run=run))
    monkeypatch.setattr(packs, "research_niche", lambda query, exclude: {**RESEARCH, "query": query, "exclude": exclude})
    monkeypatch.setattr(packs, "_source_channel", AsyncMock(return_value="Hubi"))

    pack = await packs.generate_post_pack(
        {"source_title": "Source title", "source_url": "https://youtu.be/h_xSOMtPCYI"},
        {"hook_title": "Hook", "text": "The real transcript"},
    )

    prompt = json.loads(run.await_args.args[0])
    assert prompt["transcript"] == "The real transcript"
    assert prompt["source_title"] == "Source title"
    assert prompt["research"]["popular_tags"] == RESEARCH["top_tags"]
    assert prompt["research"]["similar_videos"] == ["Similar video (1,000 views)"]
    assert pack["titles"] == ["One", "Two", "Three"]
    assert "by Hubi" in pack["description"]


async def test_generate_rejects_clip_without_transcript():
    with pytest.raises(ValueError):
        await packs.generate_post_pack({"source_title": "x"}, {"text": "  "})


def test_research_summary_weights_by_views():
    summary = research._summarise(
        [
            {"title": "small", "views": 10, "tags": ["rare"], "hashtags": ["rare"]},
            {"title": "big", "views": 1000, "tags": ["Popular", "popular "], "hashtags": ["popular"]},
        ],
        "test",
    )
    assert [v["title"] for v in summary["videos"]] == ["big", "small"]
    assert summary["top_tags"] == ["popular", "rare"]
    assert summary["top_hashtags"] == ["popular", "rare"]


def test_research_never_raises(monkeypatch):
    monkeypatch.setattr(research, "get_config", lambda: SimpleNamespace(resolve_youtube_data_api_key=lambda: None))

    def boom(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(research, "_research_with_ytdlp", boom)
    assert research.research_niche("anything")["source"] == "failed"
    assert research.research_niche("")["source"] == "none"
