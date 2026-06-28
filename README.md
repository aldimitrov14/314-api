# STL Estimator API

Production-ready MVP FastAPI service for accepting `.stl` files and returning geometry-derived 3D print metadata.

## What it returns

- Dimensions: width, depth, height
- Bounding box
- Triangle and vertex count
- Surface area
- Watertight validation
- Volume when mesh is watertight
- Estimated weight
- Estimated filament length
- Heuristic print-time estimate

Important: STL files do not contain printer settings, layer profile, supports, wall count, speeds, nozzle size, acceleration, or material profile. Therefore, print time from STL alone is a heuristic. For accurate print time, add a headless slicer service later.

## Architecture

```text
Client / Supabase Edge Function
        ↓
FastAPI Route
        ↓
API Key Dependency + Rate Limit
        ↓
STL Analysis Service
        ↓
Structured JSON Response
```

Business logic is isolated in `app/services`. Routes handle request validation, authentication, serialization, and HTTP concerns only.

## Main endpoint

```http
POST /v1/estimates/stl
X-API-Key: <secret>
Content-Type: multipart/form-data
```

Form fields:

| Field | Required | Default | Description |
|---|---:|---:|---|
| `file` | yes | - | `.stl` file |
| `material` | no | `PLA` | Material label |
| `material_density_g_cm3` | no | `1.24` | Density used for weight estimate |
| `filament_diameter_mm` | no | `1.75` | Filament diameter |
| `infill_percentage` | no | `20` | Infill percentage |
| `layer_height_mm` | no | `0.2` | Layer height used by heuristic print-time estimate |

## Health endpoints

```http
GET /health
GET /ready
GET /live
```

## Security

- Server-to-server API key authentication
- Constant-time API key comparison
- Upload size limit
- File extension validation
- MIME/content-type validation
- Structured errors
- Closed CORS by default
- Rate limiting
- No secrets in code
- Request ID middleware
- Structured JSON logs

## Deployment options

Recommended for MVP: Render Python Web Service.

Docker is included but optional.

See:

- `LOCAL_SETUP.md`
- `RENDER_SETUP.md`
- `SUPABASE_EDGE_FUNCTION.md`
