from io import BytesIO

import trimesh

from app.services.stl_analysis_service import PrintEstimateParameters, STLAnalysisService


def test_analyze_valid_box_stl() -> None:
    mesh = trimesh.creation.box(extents=(10, 20, 30))
    buffer = BytesIO()
    mesh.export(buffer, file_type="stl")

    service = STLAnalysisService()
    response = service.analyze(
        file_bytes=buffer.getvalue(),
        filename="box.stl",
        parameters=PrintEstimateParameters(
            material="PLA",
            material_density_g_cm3=1.24,
            filament_diameter_mm=1.75,
            infill_percentage=20,
            layer_height_mm=0.2,
        ),
    )

    assert response.filename == "box.stl"
    assert response.is_watertight is True
    assert response.dimensions.width_mm == 10
    assert response.dimensions.depth_mm == 20
    assert response.dimensions.height_mm == 30
    assert response.volume_cm3 == 6
    assert response.estimated_weight_g is not None
