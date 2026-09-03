"""Prompt presets: reusable task framings for common project types."""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas import PromptPreset
from ..services.prompts import get_preset, list_presets

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("/presets", response_model=list[PromptPreset], summary="List prompt presets")
def presets() -> list[PromptPreset]:
    return [PromptPreset(**preset) for preset in list_presets()]


@router.get("/presets/{name}", response_model=PromptPreset, summary="Fetch one preset")
def preset(name: str) -> PromptPreset:
    return PromptPreset(**get_preset(name))
