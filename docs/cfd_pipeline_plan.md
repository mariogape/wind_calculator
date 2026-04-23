# CFD Pipeline Plan

## Goal

Build a small-area CFD workflow that starts from the repo's current `terrain + buildings` raster and produces direction-specific wind fields plus a climatology-weighted exposure layer.

The target use case is urban wind over a compact AOI, not a full-city operational CFD platform.

## Recommended Stack

- Editor and orchestration: VS Code
- Runtime: WSL2 Ubuntu on Windows
- Solver: OpenFOAM
- Pre/post-processing: Python in this repo
- Raster/vector IO: existing `rasterio`, `pyogrio`, `shapely`, `pyproj`
- Optional mesh helpers later: `gmsh`, `pyvista`, `vtk`

## Why This Stack

- VS Code is a good control plane for scripts, debugging, tasks, and notebooks.
- OpenFOAM is a realistic open-source option for steady urban CFD.
- WSL is much less painful than trying to build a robust OpenFOAM flow natively on Windows.
- The repo already has most of the geospatial plumbing needed for AOI, raster generation, and climatology weighting.

## MVP Scope

The MVP should:

1. Accept a small AOI and a prepared `terrain_buildings_1m.tif`.
2. Build a CFD-ready terrain-plus-buildings geometry.
3. Generate a coarse but usable 3D mesh.
4. Run a steady RANS simulation for one inflow direction.
5. Export near-surface wind speed-up or wind factor rasters.
6. Repeat for a few dominant directions and combine with the current wind climatology.

The MVP should not:

- attempt LES,
- solve a whole city at 1 m,
- aim for production-grade uncertainty quantification,
- include vegetation drag at first pass.

## Practical Limits

Suggested initial AOI sizes:

- Preferred: 200 m x 200 m to 400 m x 400 m
- Acceptable with care: up to around 800 m x 800 m
- Avoid for first version: multi-km 1 m full-detail domains

Reason: the mesh size explodes fast once buildings are extruded in 3D.

## Proposed Physics

First solver choice:

- Steady-state incompressible RANS
- `simpleFoam`
- Turbulence model: `kOmegaSST` preferred, `kEpsilon` as fallback benchmark

Why:

- It is a sensible balance between cost and realism for urban screening.
- It is much easier to operationalize than LES.

## Boundary Conditions

For the first version:

- Inlet:
  - logarithmic or power-law wind profile
  - reference speed at a chosen height, e.g. 10 m
  - turbulence fields derived from atmospheric boundary layer assumptions
- Outlet:
  - zero-gradient style outflow
- Top:
  - slip or symmetry-like condition
- Ground and buildings:
  - rough wall treatment
- Side boundaries:
  - symmetry or slip, depending on domain setup

## Domain Rules

The CFD domain should be larger than the AOI of interest.

Initial heuristic:

- Upwind fetch: 5H to 10H
- Downwind fetch: 15H to 20H
- Lateral margin: 5H to 10H
- Top height: 5H to 8H

Where `H` is the maximum building or terrain obstacle height within the modeled area.

The final exposure map should only be reported over the inner target AOI, not the full CFD domain.

## Geometry Workflow

Input:

- `terrain_buildings_1m.tif`
- optional `terrain_1m.tif`
- optional `buildings_height_1m.tif`

Derived geometry:

1. Read the raster in projected CRS.
2. Crop to CFD domain extent, not just the reporting AOI.
3. Build a continuous terrain surface.
4. Represent buildings as terrain-embedded solid volumes.
5. Export a geometry format usable by the meshing step.

Two viable implementation paths:

### Path A: Heightfield-first MVP

- Use the raster as a heightfield for the top of the urban surface.
- Generate a terrain-following volume mesh above it.
- Treat the whole lower boundary as a rough wall.

Pros:

- Much simpler and faster to build.

Cons:

- Buildings are not explicit solid obstacles with vertical walls.
- Urban recirculation around facades will be poorly represented.

### Path B: Explicit-building MVP

- Derive building footprints from `buildings_height_1m.tif`.
- Simplify and extrude them to block geometries.
- Keep terrain as a surface and merge buildings onto it.

Pros:

- Much more faithful for urban flow around streets and corners.

Cons:

- More geometry and meshing work.

Recommendation:

- Start with Path B if the AOI is small enough.
- Keep Path A as a fallback for a fast prototype.

## Mesh Strategy

Recommended first mesh path:

- Hex-dominant or Cartesian base mesh
- Local refinement around buildings and near the ground
- Coarser far field

Likely OpenFOAM tools:

- `blockMesh` for the outer box
- `snappyHexMesh` for obstacle-conforming refinement

Initial cell size ideas:

- Near buildings and ground: 1 m to 2 m
- Outer domain: 4 m to 10 m

Do not force the entire domain to 1 m.

## Output Variables

Per direction, we likely want:

- wind speed magnitude near the surface
- horizontal wind speed at pedestrian/tree-relevant height
- speed-up factor relative to inlet reference
- optional turbulence proxy

Recommended first analysis height:

- 5 m above local surface for tree/wind-damage screening

Optional second height later:

- 10 m for comparison with meteorological reference conditions

## How To Convert CFD To Exposure

For each simulated direction:

1. Run the CFD case with reference inflow.
2. Sample velocity magnitude at the target height.
3. Convert to a directional factor:

   `factor_dir = U_local / U_reference`

4. Rasterize that factor onto the reporting grid.

Then combine directions using the repo's existing strong-wind weighting:

`final_cfd_exposure = sum(weight_dir * factor_dir)`

Optionally normalize to `0-100` only at the very end for presentation.

## Integration With Current Repo

Suggested new modules:

- `wind_calculator/cfd.py`
  - high-level orchestration
- `wind_calculator/cfd_geometry.py`
  - raster to terrain/building geometry
- `wind_calculator/cfd_case.py`
  - OpenFOAM case templating
- `wind_calculator/cfd_post.py`
  - sampling and raster export

Suggested folders:

- `cfd_templates/openfoam/`
  - case templates
- `docs/`
  - design notes and validation docs

## Suggested CLI Shape

Add a separate entry path instead of overloading the current SAGA one too early.

Example:

```bash
python -m wind_calculator cfd \
  --aoi data/aoi/caceres_small.gpkg \
  --output-dir outputs/caceres_cfd \
  --surface-source lidar_latest \
  --directions 225 270 315 \
  --solver simpleFoam
```

Or as a first internal API:

- keep the current CLI untouched,
- add a dedicated `run_cfd_pipeline(...)` function,
- expose CLI only when the first case works.

## Validation Plan

Validation should happen in layers:

1. Geometry validation
   - terrain/building rasters look correct
   - buildings extrude to reasonable heights
2. Mesh validation
   - acceptable cell counts
   - no obvious snappy failures
3. Physics sanity checks
   - acceleration over ridges
   - shelter in lees
   - stronger channeling in street canyons
4. Cross-method comparison
   - compare SAGA wind-effect directional patterns against CFD
   - they should not match exactly, but broad trends should be explainable

## Development Roadmap

### Phase 1: Case Builder

- Pick one tiny AOI
- Generate `terrain_buildings_1m.tif`
- Build a single CFD domain and case folder
- Manually run one OpenFOAM direction
- Verify mesh and outputs

### Phase 2: Automated One-Direction Pipeline

- Add Python automation for:
  - domain sizing
  - case templating
  - solver launch
  - sampling
  - raster export

### Phase 3: Multi-Direction CFD

- Run 3 to 4 dominant directions
- Export direction rasters
- Combine with strong-wind weights

### Phase 4: Full Direction Set

- Expand to 8 directions if runtime is acceptable
- Add caching so repeated runs reuse surfaces and cases

### Phase 5: Calibration And Trust

- Compare with known windy/sheltered locations
- Tune roughness, domain margins, mesh refinement, and sampling height

## Key Risks

- Mesh complexity becomes too large at 1 m over broad AOIs
- Building extraction may create messy geometry
- Atmospheric boundary layer setup can be wrong even when cases converge
- Runtime may be too high for routine use unless domains are tightly constrained

## Recommendation

Build the CFD work as a separate pipeline branch inside this repo, not as a replacement for the current SAGA workflow.

Best near-term role:

- SAGA pipeline: fast screening across larger AOIs
- CFD pipeline: high-fidelity analysis on selected small hotspots

That split is practical and gives you a strong story for when to use each model.
