-- BLE Monitor - Useful SQL Queries
-- Collection of helpful queries for analyzing BLE monitoring data

-- ============================================================================
-- MONITOR QUERIES
-- ============================================================================

-- List all monitors with their status
SELECT 
    monitor_id,
    monitor_name,
    location,
    IF(is_active, 'Active', 'Inactive') as status,
    last_seen,
    TIMESTAMPDIFF(MINUTE, last_seen, NOW()) as minutes_since_seen
FROM monitors
ORDER BY monitor_name;

-- Monitor activity summary (last 7 days)
SELECT 
    m.monitor_name,
    m.location,
    COUNT(DISTINCT DATE(ds.interval_start)) as active_days,
    COUNT(DISTINCT ds.device_id) as unique_devices,
    COUNT(*) as total_sightings,
    AVG(ds.rssi) as avg_rssi
FROM monitors m
LEFT JOIN device_sightings ds ON m.monitor_id = ds.monitor_id
    AND ds.interval_start >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY m.monitor_id
ORDER BY total_sightings DESC;

-- ============================================================================
-- DEVICE QUERIES
-- ============================================================================

-- All devices seen in the last 24 hours
SELECT 
    bd.mac_address,
    bd.device_name,
    COUNT(DISTINCT ds.monitor_id) as seen_by_monitors,
    COUNT(*) as times_seen,
    MAX(ds.rssi) as best_rssi,
    AVG(ds.rssi) as avg_rssi,
    MIN(ds.interval_start) as first_seen,
    MAX(ds.interval_start) as last_seen
FROM ble_devices bd
JOIN device_sightings ds ON bd.device_id = ds.device_id
WHERE ds.interval_start >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY bd.device_id
ORDER BY times_seen DESC;

-- Devices that haven't been seen recently (more than 7 days)
SELECT 
    bd.mac_address,
    bd.device_name,
    bd.last_seen,
    TIMESTAMPDIFF(DAY, bd.last_seen, NOW()) as days_since_seen
FROM ble_devices bd
LEFT JOIN device_sightings ds ON bd.device_id = ds.device_id
    AND ds.interval_start >= DATE_SUB(NOW(), INTERVAL 7 DAY)
WHERE ds.sighting_id IS NULL
ORDER BY bd.last_seen DESC;

-- New devices discovered today
SELECT 
    bd.mac_address,
    bd.device_name,
    bd.first_seen,
    COUNT(ds.sighting_id) as sightings_today
FROM ble_devices bd
JOIN device_sightings ds ON bd.device_id = ds.device_id
WHERE DATE(bd.first_seen) = CURDATE()
GROUP BY bd.device_id
ORDER BY bd.first_seen DESC;

-- ============================================================================
-- HOURLY ANALYSIS
-- ============================================================================

-- Hourly device counts for today
SELECT * FROM hourly_device_counts
WHERE DATE(hour_start) = CURDATE()
ORDER BY hour_start DESC;

-- Busiest hours (last 7 days)
SELECT 
    HOUR(interval_start) as hour_of_day,
    COUNT(DISTINCT device_id) as avg_unique_devices,
    COUNT(*) as total_sightings
FROM device_sightings
WHERE interval_start >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY HOUR(interval_start)
ORDER BY hour_of_day;

-- Daily device counts by monitor (last 30 days)
SELECT 
    m.monitor_name,
    DATE(ds.interval_start) as date,
    COUNT(DISTINCT ds.device_id) as unique_devices,
    COUNT(*) as total_sightings
FROM device_sightings ds
JOIN monitors m ON ds.monitor_id = m.monitor_id
WHERE ds.interval_start >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY m.monitor_id, DATE(ds.interval_start)
ORDER BY date DESC, m.monitor_name;

-- ============================================================================
-- RSSI ANALYSIS
-- ============================================================================

-- RSSI distribution (last 24 hours)
SELECT 
    CASE 
        WHEN rssi >= -50 THEN 'Excellent (-50 to 0)'
        WHEN rssi >= -60 THEN 'Good (-60 to -50)'
        WHEN rssi >= -70 THEN 'Fair (-70 to -60)'
        WHEN rssi >= -80 THEN 'Weak (-80 to -70)'
        ELSE 'Very Weak (< -80)'
    END as signal_strength,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
FROM device_sightings
WHERE interval_start >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY 
    CASE 
        WHEN rssi >= -50 THEN 'Excellent (-50 to 0)'
        WHEN rssi >= -60 THEN 'Good (-60 to -50)'
        WHEN rssi >= -70 THEN 'Fair (-70 to -60)'
        WHEN rssi >= -80 THEN 'Weak (-80 to -70)'
        ELSE 'Very Weak (< -80)'
    END
ORDER BY MIN(rssi) DESC;

-- Average RSSI per device per monitor (last 7 days)
SELECT 
    bd.mac_address,
    bd.device_name,
    m.monitor_name,
    COUNT(*) as sightings,
    AVG(ds.rssi) as avg_rssi,
    MIN(ds.rssi) as min_rssi,
    MAX(ds.rssi) as max_rssi
FROM device_sightings ds
JOIN ble_devices bd ON ds.device_id = bd.device_id
JOIN monitors m ON ds.monitor_id = m.monitor_id
WHERE ds.interval_start >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY bd.device_id, m.monitor_id
HAVING sightings >= 10
ORDER BY bd.mac_address, avg_rssi DESC;

-- ============================================================================
-- MULTI-MONITOR COMPARISON
-- ============================================================================

-- Which monitor sees each device best?
SELECT 
    bd.mac_address,
    bd.device_name,
    m.monitor_name as best_monitor,
    MAX(ds.rssi) as best_rssi,
    COUNT(*) as times_seen
FROM device_sightings ds
JOIN ble_devices bd ON ds.device_id = bd.device_id
JOIN monitors m ON ds.monitor_id = m.monitor_id
WHERE ds.interval_start >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY bd.device_id, m.monitor_id
ORDER BY bd.mac_address, best_rssi DESC;

-- Monitor coverage overlap (devices seen by multiple monitors)
SELECT 
    bd.mac_address,
    bd.device_name,
    COUNT(DISTINCT ds.monitor_id) as monitor_count,
    GROUP_CONCAT(DISTINCT m.monitor_name ORDER BY m.monitor_name) as monitors,
    COUNT(*) as total_sightings
FROM device_sightings ds
JOIN ble_devices bd ON ds.device_id = bd.device_id
JOIN monitors m ON ds.monitor_id = m.monitor_id
WHERE ds.interval_start >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY bd.device_id
HAVING monitor_count > 1
ORDER BY monitor_count DESC, total_sightings DESC;

-- ============================================================================
-- PERFORMANCE AND STATISTICS
-- ============================================================================

-- Database size and row counts
SELECT 
    table_name,
    table_rows,
    ROUND(((data_length + index_length) / 1024 / 1024), 2) as size_mb,
    ROUND((data_length / 1024 / 1024), 2) as data_mb,
    ROUND((index_length / 1024 / 1024), 2) as index_mb
FROM information_schema.TABLES
WHERE table_schema = 'ble_monitor'
ORDER BY (data_length + index_length) DESC;

-- Sightings per day (last 30 days)
SELECT 
    DATE(interval_start) as date,
    COUNT(DISTINCT device_id) as unique_devices,
    COUNT(*) as total_sightings,
    COUNT(DISTINCT monitor_id) as active_monitors
FROM device_sightings
WHERE interval_start >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY DATE(interval_start)
ORDER BY date DESC;

-- Data growth rate (sightings per day for last 30 days)
SELECT 
    DATE(interval_start) as date,
    COUNT(*) as sightings,
    LAG(COUNT(*)) OVER (ORDER BY DATE(interval_start)) as prev_day_sightings,
    COUNT(*) - LAG(COUNT(*)) OVER (ORDER BY DATE(interval_start)) as daily_change
FROM device_sightings
WHERE interval_start >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY DATE(interval_start)
ORDER BY date DESC;

-- ============================================================================
-- DEVICE PATTERNS
-- ============================================================================

-- Devices that appear at specific times (daily pattern)
SELECT 
    bd.mac_address,
    bd.device_name,
    HOUR(ds.interval_start) as hour,
    COUNT(*) as appearances,
    AVG(ds.rssi) as avg_rssi
FROM device_sightings ds
JOIN ble_devices bd ON ds.device_id = bd.device_id
WHERE ds.interval_start >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY bd.device_id, HOUR(ds.interval_start)
HAVING appearances >= 3
ORDER BY bd.mac_address, hour;

-- Devices consistently seen (present in >80% of intervals today)
SELECT 
    bd.mac_address,
    bd.device_name,
    COUNT(DISTINCT ds.interval_start) as intervals_present,
    (SELECT COUNT(DISTINCT interval_start) 
     FROM device_sightings 
     WHERE DATE(interval_start) = CURDATE()) as total_intervals,
    ROUND(COUNT(DISTINCT ds.interval_start) * 100.0 / 
          (SELECT COUNT(DISTINCT interval_start) 
           FROM device_sightings 
           WHERE DATE(interval_start) = CURDATE()), 1) as presence_percentage
FROM device_sightings ds
JOIN ble_devices bd ON ds.device_id = bd.device_id
WHERE DATE(ds.interval_start) = CURDATE()
GROUP BY bd.device_id
HAVING presence_percentage >= 80
ORDER BY presence_percentage DESC;

-- ============================================================================
-- MAINTENANCE QUERIES
-- ============================================================================

-- Find and remove duplicate entries (if any)
-- First, identify duplicates
SELECT 
    device_id,
    interval_start,
    COUNT(*) as duplicate_count
FROM device_sightings
GROUP BY device_id, interval_start
HAVING COUNT(*) > 1;

-- Check staging table for unprocessed data
SELECT 
    interval_start,
    COUNT(*) as unprocessed_count
FROM sighting_staging
WHERE processed = FALSE
GROUP BY interval_start
ORDER BY interval_start DESC;

-- Staging table size and cleanup candidates
SELECT 
    DATE(scan_timestamp) as date,
    processed,
    COUNT(*) as record_count
FROM sighting_staging
GROUP BY DATE(scan_timestamp), processed
ORDER BY date DESC;

-- Monitor last activity check (identify inactive monitors)
SELECT 
    monitor_name,
    location,
    last_seen,
    TIMESTAMPDIFF(HOUR, last_seen, NOW()) as hours_since_seen,
    is_active,
    CASE 
        WHEN TIMESTAMPDIFF(HOUR, last_seen, NOW()) > 24 THEN 'Alert: Inactive >24h'
        WHEN TIMESTAMPDIFF(HOUR, last_seen, NOW()) > 1 THEN 'Warning: Inactive >1h'
        ELSE 'OK'
    END as status
FROM monitors
ORDER BY last_seen DESC;

-- ============================================================================
-- ARCHIVE/CLEANUP QUERIES
-- ============================================================================

-- Count old data eligible for archival (>90 days)
SELECT 
    'device_sightings' as table_name,
    COUNT(*) as records_to_archive,
    MIN(interval_start) as oldest_record,
    MAX(interval_start) as newest_old_record
FROM device_sightings
WHERE interval_start < DATE_SUB(NOW(), INTERVAL 90 DAY);

-- Archive old data (example - adjust date as needed)
-- Step 1: Create archive table if not exists
-- CREATE TABLE device_sightings_archive LIKE device_sightings;

-- Step 2: Copy old data to archive
-- INSERT INTO device_sightings_archive 
-- SELECT * FROM device_sightings 
-- WHERE interval_start < DATE_SUB(NOW(), INTERVAL 90 DAY);

-- Step 3: Verify archive
-- SELECT COUNT(*) FROM device_sightings_archive;

-- Step 4: Delete archived data from main table
-- DELETE FROM device_sightings 
-- WHERE interval_start < DATE_SUB(NOW(), INTERVAL 90 DAY);
