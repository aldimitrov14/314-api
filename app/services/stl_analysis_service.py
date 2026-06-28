from dataclasses import dataclass
from io import BytesIO
from math import pi

import trimesh

from app.schemas.estimate import BoundingBox, Dimensions, STLAnalysisResponse


class STLAnalysisError(ValueError):
    pass


@dataclass(frozen=True)
class PrintEstimateParameters:
    printer: str
    material: str
    material_density_g_cm3: float
    filament_diameter_mm: float
    nozzle_diameter_mm: float
    infill_percentage: float
    layer_height_mm: float


@dataclass(frozen=True)
class VolumeEstimate:
    solid_volume_cm3: float
    confidence: str
    method: str
    warning: str | None = None


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

        self._clean_mesh(mesh)

        bounds = mesh.bounds
        extents = mesh.extents

        width_mm = float(extents[0])
        depth_mm = float(extents[1])
        height_mm = float(extents[2])
        surface_area_cm2 = float(mesh.area / 100)

        warnings: list[str] = []

        volume_estimate = self._estimate_solid_volume_cm3(
            mesh=mesh,
            width_mm=width_mm,
            depth_mm=depth_mm,
            height_mm=height_mm,
            surface_area_cm2=surface_area_cm2,
        )

        if volume_estimate.warning:
            warnings.append(volume_estimate.warning)

        effective_volume_cm3 = self._effective_print_volume_cm3(
            solid_volume_cm3=volume_estimate.solid_volume_cm3,
            infill_percentage=parameters.infill_percentage,
        )

        estimated_weight_g = effective_volume_cm3 * parameters.material_density_g_cm3

        filament_length_m = self._filament_length_m(
            volume_cm3=effective_volume_cm3,
            filament_diameter_mm=parameters.filament_diameter_mm,
        )

        estimated_print_time_minutes = self._estimate_print_time_minutes(
            filament_length_m=filament_length_m,
            infill_percentage=parameters.infill_percentage,
        )

        estimated_price, price_breakdown = self._calculate_price(
            estimated_weight_g=estimated_weight_g,
            estimated_print_time_minutes=estimated_print_time_minutes,
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
            volume_cm3=round(volume_estimate.solid_volume_cm3, 2),
            surface_area_cm2=round(surface_area_cm2, 2),
            estimated_weight_g=round(estimated_weight_g, 2),
            estimated_filament_length_m=round(filament_length_m, 2),
            estimated_print_time_minutes=estimated_print_time_minutes,
            estimated_price=estimated_price,
            currency="EUR",
            price_breakdown=price_breakdown,
            estimate_method="geometry_heuristic_v3",
            estimate_confidence=volume_estimate.confidence,
            volume_estimation_method=volume_estimate.method,
            warnings=warnings,
        )

    def _clean_mesh(self, mesh: trimesh.Trimesh) -> None:
        try:
            mesh.remove_unreferenced_vertices()
        except Exception:
            pass

        try:
            mesh.merge_vertices()
        except Exception:
            pass

        try:
            mesh.update_faces(mesh.unique_faces())
        except Exception:
            pass

        try:
            mesh.update_faces(mesh.nondegenerate_faces())
        except Exception:
            pass

        try:
            mesh.fix_normals()
        except Exception:
            pass

        try:
            mesh.fill_holes()
        except Exception:
            pass

        try:
            mesh.process(validate=True)
        except Exception:
            pass

    def _estimate_solid_volume_cm3(
        self,
        mesh: trimesh.Trimesh,
        width_mm: float,
        depth_mm: float,
        height_mm: float,
        surface_area_cm2: float,
    ) -> VolumeEstimate:
        if mesh.is_volume:
            return VolumeEstimate(
                solid_volume_cm3=abs(float(mesh.volume)) / 1000,
                confidence="high",
                method="mesh_volume",
            )

        convex_hull_volume_cm3 = self._convex_hull_volume_cm3(mesh)
        bounding_box_volume_cm3 = self._bounding_box_volume_cm3(
            width_mm=width_mm,
            depth_mm=depth_mm,
            height_mm=height_mm,
        )

        if convex_hull_volume_cm3 is not None:
            occupancy = self._estimate_convex_hull_occupancy(
                mesh=mesh,
                convex_hull_volume_cm3=convex_hull_volume_cm3,
                bounding_box_volume_cm3=bounding_box_volume_cm3,
                surface_area_cm2=surface_area_cm2,
            )

            return VolumeEstimate(
                solid_volume_cm3=convex_hull_volume_cm3 * occupancy,
                confidence="medium",
                method="convex_hull_occupancy",
                warning=(
                    "Mesh is not a valid closed solid. Volume, weight, filament usage and print time "
                    "are estimated from convex-hull occupancy and should be treated as approximate."
                ),
            )

        occupancy = self._estimate_bounding_box_occupancy(
            width_mm=width_mm,
            depth_mm=depth_mm,
            height_mm=height_mm,
            surface_area_cm2=surface_area_cm2,
        )

        return VolumeEstimate(
            solid_volume_cm3=bounding_box_volume_cm3 * occupancy,
            confidence="low",
            method="bounding_box_occupancy",
            warning=(
                "Mesh is not a valid closed solid and convex hull calculation failed. Volume, weight, "
                "filament usage and print time are rough bounding-box estimates."
            ),
        )

    def _convex_hull_volume_cm3(self, mesh: trimesh.Trimesh) -> float | None:
        try:
            hull = mesh.convex_hull

            if hull.is_empty:
                return None

            hull_volume_cm3 = abs(float(hull.volume)) / 1000

            if hull_volume_cm3 <= 0:
                return None

            return hull_volume_cm3
        except Exception:
            return None

    def _bounding_box_volume_cm3(
        self,
        width_mm: float,
        depth_mm: float,
        height_mm: float,
    ) -> float:
        return max((width_mm * depth_mm * height_mm) / 1000, 0.01)

    def _estimate_convex_hull_occupancy(
        self,
        mesh: trimesh.Trimesh,
        convex_hull_volume_cm3: float,
        bounding_box_volume_cm3: float,
        surface_area_cm2: float,
    ) -> float:
        hull_to_box_ratio = self._clamp(
            convex_hull_volume_cm3 / bounding_box_volume_cm3,
            minimum=0.05,
            maximum=1.0,
        )

        surface_density = surface_area_cm2 / max(convex_hull_volume_cm3, 0.01)
        triangle_count = len(mesh.faces)

        if hull_to_box_ratio >= 0.65:
            base_occupancy = 0.75
        elif hull_to_box_ratio >= 0.40:
            base_occupancy = 0.62
        elif hull_to_box_ratio >= 0.20:
            base_occupancy = 0.48
        else:
            base_occupancy = 0.35

        if surface_density > 30:
            base_occupancy -= 0.18
        elif surface_density > 18:
            base_occupancy -= 0.10
        elif surface_density < 8:
            base_occupancy += 0.08

        if triangle_count > 150_000:
            base_occupancy -= 0.06
        elif triangle_count < 5_000:
            base_occupancy += 0.04

        return self._clamp(base_occupancy, minimum=0.22, maximum=0.85)

    def _estimate_bounding_box_occupancy(
        self,
        width_mm: float,
        depth_mm: float,
        height_mm: float,
        surface_area_cm2: float,
    ) -> float:
        bounding_box_volume_cm3 = self._bounding_box_volume_cm3(
            width_mm=width_mm,
            depth_mm=depth_mm,
            height_mm=height_mm,
        )

        surface_density = surface_area_cm2 / bounding_box_volume_cm3

        if surface_density < 6:
            return 0.65

        if surface_density < 12:
            return 0.50

        if surface_density < 22:
            return 0.38

        return 0.28

    def _effective_print_volume_cm3(
        self,
        solid_volume_cm3: float,
        infill_percentage: float,
    ) -> float:
        shell_factor = 0.18
        infill_factor = max(0.0, min(infill_percentage, 100.0)) / 100
        return solid_volume_cm3 * (shell_factor + ((1 - shell_factor) * infill_factor))

    def _filament_length_m(
        self,
        volume_cm3: float,
        filament_diameter_mm: float,
    ) -> float:
        filament_radius_mm = filament_diameter_mm / 2
        filament_area_mm2 = pi * filament_radius_mm**2
        volume_mm3 = volume_cm3 * 1000
        return volume_mm3 / filament_area_mm2 / 1000

    def _estimate_print_time_minutes(
        self,
        filament_length_m: float,
        infill_percentage: float,
    ) -> int:
        baseline_minutes_per_meter = 8.0
        infill_multiplier = 1.0 + ((infill_percentage / 100) * 0.35)

        estimated_minutes = filament_length_m * baseline_minutes_per_meter * infill_multiplier

        return max(5, round(estimated_minutes))

    def _clamp(
        self,
        value: float,
        minimum: float,
        maximum: float,
    ) -> float:
        return max(minimum, min(value, maximum))

    def _calculate_price(
    self,
    estimated_weight_g: float,
    estimated_print_time_minutes: int,
    ) -> tuple[float, dict[str, float]]:

    MATERIAL_PRICE_PER_G = 0.025
    MACHINE_RATE_PER_HOUR = 2.50
    PRINTER_POWER_KW = 0.12
    ELECTRICITY_PRICE = 0.30
    SETUP_FEE = 2.00
    MARKUP = 2.0
    MINIMUM_PRICE = 5.00

    print_hours = estimated_print_time_minutes / 60

    material_cost = estimated_weight_g * MATERIAL_PRICE_PER_G
    machine_cost = print_hours * MACHINE_RATE_PER_HOUR
    electricity_cost = (
        print_hours *
        PRINTER_POWER_KW *
        ELECTRICITY_PRICE
    )

    base_cost = (
        material_cost +
        machine_cost +
        electricity_cost +
        SETUP_FEE
    )

    final_price = max(
        base_cost * MARKUP,
        MINIMUM_PRICE,
    )

    return round(final_price, 2), {
        "material_cost": round(material_cost, 2),
        "machine_cost": round(machine_cost, 2),
        "electricity_cost": round(electricity_cost, 2),
        "setup_fee": round(SETUP_FEE, 2),
        "markup": round(final_price - base_cost, 2),
    }
