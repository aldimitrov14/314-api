from dataclasses import dataclass
from io import BytesIO
from math import pi

import trimesh

from app.schemas.estimate import BoundingBox, Dimensions, STLAnalysisResponse


class STLAnalysisError(ValueError):
    pass


@dataclass(frozen=True)
class PrintEstimateParameters:
    material: str
    material_density_g_cm3: float
    filament_diameter_mm: float
    infill_percentage: float
    layer_height_mm: float


class STLAnalysisService:
    def analyze(
        self,
        file_bytes: bytes,
        filename: str,
        parameters: PrintEstimateParameters,
    ) -> STLAnalysisResponse:
        try:
            loaded_mesh = trimesh.load_mesh(BytesIO(file_bytes), file_type="stl", process=True)
        except Exception as exc:
            raise STLAnalysisError("Uploaded file could not be parsed as a valid STL mesh.") from exc

        if not isinstance(loaded_mesh, trimesh.Trimesh):
            raise STLAnalysisError("Uploaded STL did not contain a single valid mesh.")

        mesh = loaded_mesh
        if mesh.is_empty:
            raise STLAnalysisError("Uploaded STL mesh is empty.")

        bounds = mesh.bounds
        extents = mesh.extents

        width_mm = float(extents[0])
        depth_mm = float(extents[1])
        height_mm = float(extents[2])
        surface_area_cm2 = float(mesh.area / 100)

        warnings: list[str] = []
        volume_cm3: float | None = None
        estimated_weight_g: float | None = None
        filament_length_m: float | None = None

        if mesh.is_watertight:
            solid_volume_cm3 = abs(float(mesh.volume)) / 1000
            volume_cm3 = solid_volume_cm3

            effective_volume_cm3 = self._effective_print_volume_cm3(
                solid_volume_cm3=solid_volume_cm3,
                infill_percentage=parameters.infill_percentage,
            )
            estimated_weight_g = effective_volume_cm3 * parameters.material_density_g_cm3
            filament_length_m = self._filament_length_m(
                volume_cm3=effective_volume_cm3,
                filament_diameter_mm=parameters.filament_diameter_mm,
            )
        else:
            warnings.append(
                "Mesh is not watertight. Volume, weight and filament estimates are unavailable."
            )

        estimated_print_time_minutes = self._estimate_print_time_minutes(
            volume_cm3=volume_cm3,
            height_mm=height_mm,
            surface_area_cm2=surface_area_cm2,
            layer_height_mm=parameters.layer_height_mm,
            infill_percentage=parameters.infill_percentage,
        )

        warnings.append(
            "Print time is a heuristic estimate. For accurate print time, integrate a headless slicer with printer/profile settings."
        )

        return STLAnalysisResponse(
            filename=filename,
            is_watertight=bool(mesh.is_watertight),
            is_empty=bool(mesh.is_empty),
            triangle_count=int(len(mesh.faces)),
            vertex_count=int(len(mesh.vertices)),
            dimensions=Dimensions(
                width_mm=round(width_mm, 2),
                depth_mm=round(depth_mm, 2),
                height_mm=round(height_mm, 2),
            ),
            bounding_box=BoundingBox(
                min_x_mm=round(float(bounds[0][0]), 2),
                min_y_mm=round(float(bounds[0][1]), 2),
                min_z_mm=round(float(bounds[0][2]), 2),
                max_x_mm=round(float(bounds[1][0]), 2),
                max_y_mm=round(float(bounds[1][1]), 2),
                max_z_mm=round(float(bounds[1][2]), 2),
            ),
            volume_cm3=round(volume_cm3, 2) if volume_cm3 is not None else None,
            surface_area_cm2=round(surface_area_cm2, 2),
            estimated_weight_g=round(estimated_weight_g, 2)
            if estimated_weight_g is not None
            else None,
            estimated_filament_length_m=round(filament_length_m, 2)
            if filament_length_m is not None
            else None,
            estimated_print_time_minutes=estimated_print_time_minutes,
            estimate_method="geometry_heuristic_v1",
            warnings=warnings,
        )

    def _effective_print_volume_cm3(self, solid_volume_cm3: float, infill_percentage: float) -> float:
        shell_factor = 0.18
        infill_factor = max(0.0, min(infill_percentage, 100.0)) / 100
        return solid_volume_cm3 * (shell_factor + ((1 - shell_factor) * infill_factor))

    def _filament_length_m(self, volume_cm3: float, filament_diameter_mm: float) -> float:
        filament_radius_mm = filament_diameter_mm / 2
        filament_area_mm2 = pi * filament_radius_mm**2
        volume_mm3 = volume_cm3 * 1000
        return volume_mm3 / filament_area_mm2 / 1000

    def _estimate_print_time_minutes(
        self,
        volume_cm3: float | None,
        height_mm: float,
        surface_area_cm2: float,
        layer_height_mm: float,
        infill_percentage: float,
    ) -> int | None:
        if volume_cm3 is None:
            return None

        layer_count = height_mm / layer_height_mm
        volume_component = volume_cm3 * (4.0 + (infill_percentage / 100 * 5.0))
        layer_component = layer_count * 0.35
        surface_component = surface_area_cm2 * 0.08
        return max(1, round(volume_component + layer_component + surface_component))
