"""
main.py

FastAPI service for the Cairo Q-Commerce Network Optimization project.

Computes the optimal new store locations on each request: pulls existing
stores and candidate neighborhood sites from PostGIS, runs a greedy
iterative MCDA algorithm to pick non-cannibalizing sites, and returns the
result as a GeoJSON FeatureCollection.
"""

import os
from fastapi import FastAPI
import geopandas as gpd
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

engine = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")


@app.get("/api/v1/optimal-locations")
def get_optimal_locations(n_stores: int = 3, distance_cap: float = 5000):
    stores_gdf = gpd.read_postgis(
        "SELECT name, geom_utm FROM stores_analysis",
        engine, geom_col="geom_utm"
    )
    sites_gdf = gpd.read_postgis(
        "SELECT name, geometry FROM candidate_sites",
        engine, geom_col="geometry"
    )
    sites_gdf = sites_gdf.to_crs(epsg=32636)

    # Synthetic demand score - a documented limitation, used as a
    # placeholder for real order/population data that wasn't available
    np.random.seed(42)
    sites_gdf["synthetic_demand_score"] = np.random.uniform(1, 100, len(sites_gdf))

    selected_sites = []
    existing_stores = stores_gdf.copy()
    remaining_sites = sites_gdf.copy()

    for round_num in range(n_stores):
        # Distance to the nearest store (existing + previously selected)
        distances = remaining_sites.geometry.apply(
            lambda site: existing_stores.geometry.distance(site).min()
        )
        remaining_sites = remaining_sites.copy()
        remaining_sites["distance_to_nearest"] = distances

        # Engineering decision: cap distance before scoring - beyond this
        # range a site is already well outside any real competitive
        # catchment, so further distance shouldn't keep increasing its
        # score. An earlier version without the cap kept selecting the
        # single most remote points in the dataset, which was not a
        # meaningful business signal.
        remaining_sites["distance_capped"] = remaining_sites["distance_to_nearest"].clip(upper=distance_cap)

        dist_norm = (remaining_sites["distance_capped"] - remaining_sites["distance_capped"].min()) / \
                    (remaining_sites["distance_capped"].max() - remaining_sites["distance_capped"].min())
        demand_norm = (remaining_sites["synthetic_demand_score"] - remaining_sites["synthetic_demand_score"].min()) / \
                      (remaining_sites["synthetic_demand_score"].max() - remaining_sites["synthetic_demand_score"].min())

        remaining_sites["suitability_score"] = (0.6 * demand_norm) + (0.4 * dist_norm)

        winner = remaining_sites.loc[remaining_sites["suitability_score"].idxmax()]
        selected_sites.append({
            "round": round_num + 1,
            "name": winner["name"],
            "distance_to_nearest_store_m": round(winner["distance_to_nearest"], 2),
            "suitability_score": round(winner["suitability_score"], 4),
            "geometry": winner["geometry"]
        })

        # Add the winner to "existing stores" so the next round accounts
        # for it - this is what prevents two selected sites from being
        # clustered near each other (greedy iterative selection)
        new_store_row = gpd.GeoDataFrame(
            {"name": [winner["name"]], "geom_utm": [winner["geometry"]]},
            geometry="geom_utm", crs=existing_stores.crs
        )
        existing_stores = pd.concat([existing_stores, new_store_row], ignore_index=True)
        remaining_sites = remaining_sites[remaining_sites["name"] != winner["name"]]

    result_gdf = gpd.GeoDataFrame(selected_sites, geometry="geometry", crs="EPSG:32636")
    result_gdf = result_gdf.to_crs(epsg=4326)  # back to WGS84 for GeoJSON output

    return result_gdf.__geo_interface__
