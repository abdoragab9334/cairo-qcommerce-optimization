# Q-Commerce Network Optimization & Cannibalization Analysis in Cairo

Spatial data engineering project that identifies optimal locations for opening
3 new dark stores / delivery hubs in Cairo, Egypt — maximizing coverage of new
areas while minimizing revenue cannibalization from existing stores.

## Problem

Q-commerce and delivery companies expanding a store network face a trade-off:
new locations should reach high-demand areas, but sites too close to existing
stores cannibalize sales instead of capturing new demand. This project builds
an end-to-end pipeline — from raw geospatial data to a queryable API — that
solves this trade-off algorithmically.

## Data

- **663 real stores** (pharmacies, supermarkets, convenience stores) in Cairo,
  fetched from OpenStreetMap via `osmnx`.
- **1,979 real Cairo neighborhoods**, also from OpenStreetMap, used as
  candidate expansion sites (their centroids represent local demand hubs).
- **Synthetic demand score** per neighborhood (uniform random, 1–100) — a
  documented limitation, used as a placeholder for real order/population data
  that wasn't available for this project. Swapping in real demand data
  (population density, historical order volume) would be a direct extension.

## Methodology

1. **Coordinate system**: all distance and area calculations use **EPSG:32636
   (UTM Zone 36N)**, the projected metric CRS for Egypt — not WGS84 (degrees,
   distorts distance) or Web Mercator (global approximation, less accurate at
   Cairo's latitude).
2. **Catchment buffers**: a 2km buffer is computed around each existing store
   using `ST_Buffer` in PostGIS, after projecting to the metric CRS.
3. **Distance scoring**: for each candidate neighborhood, the distance to the
   nearest existing store is computed. Distance is **capped at 5,000m** before
   scoring — beyond that range, a site is already well outside any real
   competitive catchment, so further distance shouldn't keep increasing its
   score (an earlier version without the cap kept selecting the single most
   remote points in the dataset, which was not a meaningful business signal).
4. **Suitability score (MCDA)**: `0.6 × normalized_demand + 0.4 ×
   normalized_distance`, both min-max normalized to [0, 1].
5. **Greedy iterative selection**: instead of picking the top-3 scoring sites
   independently (which can select two nearby sites that would cannibalize
   each other), the algorithm selects one winner per round, adds it to the
   "existing stores" set, and recalculates distances for the next round. This
   prevents two winning sites from being clustered together.

## Architecture

```
OpenStreetMap (osmnx)
        │
        ▼
  PostGIS (PostgreSQL)
   - stores_analysis (existing stores + UTM buffers)
   - candidate_sites (neighborhood centroids)
        │
        ▼
  Python / GeoPandas
   - Greedy MCDA iterative algorithm
        │
        ▼
  FastAPI endpoint  →  GET /api/v1/optimal-locations
        │
        ▼
  GeoJSON FeatureCollection
```

## API

```
GET /api/v1/optimal-locations?n_stores=3&distance_cap=5000
```

Returns a GeoJSON `FeatureCollection` with the selected sites, ranked by
selection round, including suitability score and distance to nearest store.

## Example Result

| Round | Neighborhood | Distance to nearest store (m) | Suitability score |
|-------|-------------|-------------------------------|--------------------|
| 1 | منطقة هـ | 5,801 | 1.000 |
| 2 | كمبوند جمعية الدلتا | 5,753 | 0.995 |
| 3 | كمبوند الياسمين | 7,708 | 0.965 |

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file (see `.env.example`) with your PostgreSQL credentials,
then create the `cairo_gis` database with the PostGIS extension enabled:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

Run the data pipeline scripts in `scripts/`, then start the API:

```bash
python -m uvicorn scripts.main:app --reload
```

## Known Limitations

- Demand is synthetic (random), not derived from real population or order
  data — noted above as the clearest next improvement.
- The greedy algorithm is a heuristic, not a globally optimal solution — it
  can produce a locally-optimal but not globally-optimal set of 3 sites.
- No population/demographic weighting; all neighborhoods are treated as
  equally likely candidates regardless of size.

## Tech Stack

Python (GeoPandas, OSMnx, FastAPI), PostgreSQL + PostGIS, SQLAlchemy.
