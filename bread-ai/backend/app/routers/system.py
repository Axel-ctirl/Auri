"""Health, GPU and overall system status."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ..config import Settings, get_settings
from ..schemas import GpuStatus, HealthResponse, ModelStatus, SystemStatus
from ..security import ensure_lan_guard
from ..services.gpu import dependency_report, gpu_status, platform_summary
from ..services.inference import registry

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        app=settings.app_name,
        version=settings.app_version,
        time=datetime.now(timezone.utc),
    )


@router.get("/system/gpu", response_model=GpuStatus, summary="CUDA and VRAM report")
def system_gpu() -> GpuStatus:
    return GpuStatus(**gpu_status())


@router.get("/system/status", response_model=SystemStatus, summary="Everything at once")
def system_status(settings: Settings = Depends(get_settings)) -> SystemStatus:
    platform_info = platform_summary()
    return SystemStatus(
        app=settings.app_name,
        version=settings.app_version,
        python_version=platform_info["python_version"],
        platform=platform_info["platform"],
        host=settings.host,
        port=settings.port,
        binds_to_lan=settings.binds_to_lan,
        api_key_required=settings.require_api_key or settings.binds_to_lan,
        data_dir=str(settings.data_dir),
        database_url=settings.resolved_database_url,
        rag_enabled=settings.rag_enabled,
        model=ModelStatus(**registry.status().as_dict()),
        gpu=GpuStatus(**gpu_status()),
        optional_dependencies=dependency_report(),
        warnings=ensure_lan_guard(settings),
    )
