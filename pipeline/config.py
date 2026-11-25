"""Project settings. Data lives here; logic lives in the other modules."""

# Coordinates from the Open-Meteo geocoding API (GeoNames data), checked 2026-11-25.
# For each town we took the most populated match in the Province of Laguna,
# skipping smaller barangays with the same name.
LOCATIONS = [
    {"name": "San Pablo",  "latitude": 14.06830, "longitude": 121.32560},
    {"name": "Calamba",    "latitude": 14.21167, "longitude": 121.16528},
    {"name": "Santa Cruz", "latitude": 14.28140, "longitude": 121.41610},
    {"name": "Los Baños",  "latitude": 14.17025, "longitude": 121.24181},
    {"name": "Biñan",      "latitude": 14.34267, "longitude": 121.08071},
]
