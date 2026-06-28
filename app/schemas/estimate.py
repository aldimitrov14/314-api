from pydantic import BaseModel, Field


class Dimensions(BaseModel):
    width_mm: float = Field(ge=0)
    depth_mm: float = Field(ge=0)
    height_mm: float = Field(ge=0)


class BoundingBox(BaseModel):
    min_x_mm: float
    min_y_mm: float
    min_z_mm: float
    max_x_mm: float
    max_y_mm: float
    max_z_mm: float


class EstimateRequestMetadata(BaseModel):
    material: str = Field(default="PLA")
    material_density_g_cm3: float = Field(default=1.24, gt=0, le=25)
    filament_diameter_mm: float = Field(default=1.75, gt=0, le=5)
    infill_percentage: float = Field(default=20, ge=0, le=100)
    layer_height_mm: float = Field(default=0.2, gt=0, le=1)


class STLAnalysisResponse(BaseModel):
    filename: str
    unit_assumption: str = "millimeters"
    is_watertight: bool
    is_empty: bool
    triangle_count: int
    vertex_count: int
    dimensions: Dimensions
    bounding_box: BoundingBox
    volume_cm3: float | None = None
    surface_area_cm2: float
    estimated_weight_g: float | None = None
    estimated_filament_length_m: float | None = None
    estimated_print_time_minutes: int | None = None
    estimate_method: str
    warnings: list[str] = Field(default_factory=list)
