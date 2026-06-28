from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from app.api.dependencies.api_key import require_api_key
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.schemas.estimate import STLAnalysisResponse
from app.services.stl_analysis_service import (
    PrintEstimateParameters,
    STLAnalysisError,
    STLAnalysisService,
)

router = APIRouter(prefix="/v1/estimates", tags=["Estimates"])


@router.post(
    "/stl",
    response_model=STLAnalysisResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_api_key)],
    responses={
        200: {"description": "STL analysis result."},
        400: {"description": "Invalid upload."},
        401: {"description": "Invalid or missing API key."},
        413: {"description": "File too large."},
        422: {"description": "Invalid STL."},
        429: {"description": "Rate limit exceeded."},
    },
)
@limiter.limit(lambda: f"{get_settings().rate_limit_per_minute}/minute")
async def analyze_stl(
    request: Request,  # required by SlowAPI
    file: UploadFile = File(...),
    material: str = Form(default="PLA"),
    material_density_g_cm3: float = Form(default=1.24),
    filament_diameter_mm: float = Form(default=1.75),
    infill_percentage: float = Form(default=20),
    layer_height_mm: float = Form(default=0.2),
) -> STLAnalysisResponse:
    settings = get_settings()

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "MISSING_FILENAME", "message": "Uploaded file must have a filename."}},
        )

    if not file.filename.lower().endswith(".stl"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_FILE_EXTENSION", "message": "Only .stl files are supported."}},
        )

    if file.content_type not in {
        "model/stl",
        "application/sla",
        "application/vnd.ms-pki.stl",
        "application/octet-stream",
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_CONTENT_TYPE",
                    "message": "Unsupported content type for STL upload.",
                }
            },
        )

    file_bytes = await file.read(settings.max_upload_size_bytes + 1)
    if len(file_bytes) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "error": {
                    "code": "FILE_TOO_LARGE",
                    "message": f"Maximum file size is {settings.max_upload_size_mb} MB.",
                }
            },
        )

    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "EMPTY_FILE", "message": "Uploaded file is empty."}},
        )

    parameters = PrintEstimateParameters(
        material=material,
        material_density_g_cm3=material_density_g_cm3,
        filament_diameter_mm=filament_diameter_mm,
        infill_percentage=infill_percentage,
        layer_height_mm=layer_height_mm,
    )

    service = STLAnalysisService()
    try:
        return service.analyze(file_bytes=file_bytes, filename=file.filename, parameters=parameters)
    except STLAnalysisError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "INVALID_STL", "message": str(exc)}},
        ) from exc
