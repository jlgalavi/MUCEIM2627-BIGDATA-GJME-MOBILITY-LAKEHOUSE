-- QUERY 1: Show the source filename
SELECT filename AS source_file FROM raw_trips LIMIT 1;

-- QUERY 2: Inspect the raw column names and types
DESCRIBE raw_trips;

-- QUERY 3: Display ten original observations
SELECT * FROM raw_trips LIMIT 10;

-- QUERY 4: Count source records and inspect date coverage
SELECT COUNT(*) AS source_records, MIN(fecha) AS first_date,
       MAX(fecha) AS last_date, COUNT(DISTINCT fecha) AS distinct_dates
FROM raw_trips;

-- QUERY 5: Check record dates against the date in the filename
SELECT fecha, REGEXP_EXTRACT(filename, '([0-9]{8})_Viajes', 1) AS filename_date,
       COUNT(*) AS records,
       fecha = REGEXP_EXTRACT(filename, '([0-9]{8})_Viajes', 1) AS dates_match
FROM raw_trips GROUP BY fecha, filename;

-- QUERY 6: Inspect records per hourly period
SELECT periodo AS source_period, COUNT(*) AS records
FROM raw_trips GROUP BY periodo ORDER BY periodo;

-- QUERY 7: Detect invalid dates and hourly periods
SELECT COUNT(*) FILTER (WHERE trip_date IS NULL) AS invalid_dates,
       COUNT(*) FILTER (WHERE hour_slot IS NULL OR hour_slot NOT BETWEEN 0 AND 23)
           AS invalid_hours
FROM typed_trips;

-- QUERY 8: Check missing zone codes and count distinct zones
SELECT COUNT(*) FILTER (WHERE origen IS NULL OR TRIM(origen) IN ('', 'NA'))
           AS missing_origins,
       COUNT(*) FILTER (WHERE destino IS NULL OR TRIM(destino) IN ('', 'NA'))
           AS missing_destinations,
       COUNT(DISTINCT origen) AS distinct_origin_codes,
       COUNT(DISTINCT destino) AS distinct_destination_codes
FROM raw_trips;

-- QUERY 9: Show textual zone identifiers and their lengths
SELECT origen, LENGTH(origen) AS code_length, COUNT(*) AS records
FROM raw_trips GROUP BY origen ORDER BY origen LIMIT 15;

-- QUERY 10: Count measures that cannot be parsed as numbers
SELECT COUNT(*) AS records,
       COUNT(*) FILTER (WHERE trip_count IS NULL) AS trips_missing_or_unparseable,
       COUNT(*) FILTER (WHERE trip_km IS NULL) AS trip_km_missing_or_unparseable
FROM typed_trips;

-- QUERY 11: Inspect the raw trip values that failed numeric conversion
SELECT viajes AS original_trip_value, COUNT(*) AS records
FROM typed_trips WHERE trip_count IS NULL
GROUP BY viajes ORDER BY records DESC LIMIT 15;

-- QUERY 12: Check negative and zero measures without deleting them
SELECT COUNT(*) FILTER (WHERE trip_count < 0) AS negative_trip_records,
       COUNT(*) FILTER (WHERE trip_count = 0) AS zero_trip_records,
       COUNT(*) FILTER (WHERE trip_km < 0) AS negative_trip_km_records,
       COUNT(*) FILTER (WHERE trip_km = 0) AS zero_trip_km_records
FROM typed_trips;

-- QUERY 13: Inspect distance bands rather than treating them as centroid distances
SELECT distancia AS distance_band, COUNT(*) AS records,
       SUM(trip_count) AS observed_trips
FROM typed_trips GROUP BY distancia ORDER BY records DESC;

-- QUERY 14: Inspect activity segmentation in the source
SELECT actividad_origen, actividad_destino, COUNT(*) AS records,
       SUM(trip_count) AS observed_trips
FROM typed_trips GROUP BY actividad_origen, actividad_destino
ORDER BY observed_trips DESC;

-- QUERY 15: Demonstrate that hourly OD keys can have multiple segment records
SELECT fecha, periodo, origen, destino, COUNT(*) AS segment_records
FROM raw_trips GROUP BY fecha, periodo, origen, destino
HAVING COUNT(*) > 1 ORDER BY segment_records DESC, fecha, periodo, origen, destino
LIMIT 10;

-- QUERY 16: Calculate observed trips and trip-kilometres for the selected day
SELECT trip_date, SUM(trip_count) AS observed_trips,
       SUM(trip_km) AS observed_trip_km,
       COUNT(*) FILTER (WHERE trip_count IS NULL) AS records_without_numeric_trips
FROM typed_trips GROUP BY trip_date ORDER BY trip_date;

-- QUERY 17: Aggregate daily trips by hour
SELECT trip_date, hour_slot, SUM(trip_count) AS observed_trips,
       COUNT(*) AS source_records
FROM typed_trips GROUP BY trip_date, hour_slot ORDER BY trip_date, hour_slot;

-- QUERY 18: Rank origins by observed departures
SELECT origen AS origin_zone, SUM(trip_count) AS observed_departures
FROM typed_trips GROUP BY origen
ORDER BY observed_departures DESC NULLS LAST, origen LIMIT 10;

-- QUERY 19: Rank origin-destination pairs and compute weighted mean trip length
SELECT origen, destino, SUM(trip_count) AS observed_trips,
       SUM(trip_km) AS observed_trip_km,
       SUM(CASE WHEN trip_count > 0 AND trip_km >= 0 THEN trip_km END)
       / NULLIF(SUM(CASE WHEN trip_count > 0 AND trip_km >= 0 THEN trip_count END), 0)
           AS mean_km_per_trip_on_valid_records
FROM typed_trips GROUP BY origen, destino
ORDER BY observed_trips DESC NULLS LAST, origen, destino LIMIT 10;

-- QUERY 20: Reconcile source trip totals with aggregated hourly OD totals
WITH hourly_od AS (
    SELECT trip_date, hour_slot, origen, destino,
           SUM(trip_count) AS observed_trips
    FROM typed_trips GROUP BY trip_date, hour_slot, origen, destino
), totals AS (
    SELECT (SELECT SUM(trip_count) FROM typed_trips) AS source_total,
           (SELECT SUM(observed_trips) FROM hourly_od) AS aggregated_total
)
SELECT source_total, aggregated_total,
       aggregated_total - source_total AS floating_point_difference,
       ABS(aggregated_total - source_total)
           / NULLIF(ABS(source_total), 0) AS relative_difference
FROM totals;
