"""Ready-to-post YouTube Shorts copy for a clip.

``GET`` returns the saved pack (404 when none yet); ``POST`` researches similar
videos, writes a new pack with the configured LLM and saves it. Generation runs
in the request: with a local model it can take a minute or two.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...services.post_pack_service import generate_post_pack, load_post_pack, save_post_pack
from ...services.task_service import TaskService
from .tasks import _require_task_reader

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["post-packs"])


async def _task_and_clip(request: Request, db: AsyncSession, task_id: str, clip_id: str):
    task_service = TaskService(db)
    task = await _require_task_reader(request, task_service, db, task_id)
    clip = await task_service.clip_repo.get_clip_by_id(db, clip_id)
    if not clip or clip.get("task_id") != task_id:
        raise HTTPException(status_code=404, detail="Clip not found")
    return task, clip


@router.get("/{task_id}/clips/{clip_id}/post-pack")
async def get_post_pack(task_id: str, clip_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _task_and_clip(request, db, task_id, clip_id)
    pack = await load_post_pack(db, clip_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="No post pack yet")
    return pack


@router.post("/{task_id}/clips/{clip_id}/post-pack")
async def create_post_pack(task_id: str, clip_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    task, clip = await _task_and_clip(request, db, task_id, clip_id)
    try:
        pack = await generate_post_pack(task, clip)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except TimeoutError:
        raise HTTPException(status_code=504, detail="The AI model took too long. Try again.") from None
    except RuntimeError as exc:  # missing model configuration
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except Exception:
        logger.exception("Post pack generation failed for clip %s", clip_id)
        raise HTTPException(status_code=502, detail="Couldn't write a post pack. Try again.") from None
    await save_post_pack(db, task_id, clip_id, pack)
    return await load_post_pack(db, clip_id)
