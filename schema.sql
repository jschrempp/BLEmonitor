-- BLE Monitor Database Schema
-- This schema supports multiple monitors reporting BLE device sightings
-- with automatic best-RSSI selection per interval

-- Create database
CREATE DATABASE IF NOT EXISTS ble_monitor;
USE ble_monitor;

-- Monitors table: tracks each monitoring device
CREATE TABLE IF NOT EXISTS monitors (
    monitor_id INT AUTO_INCREMENT PRIMARY KEY,
    monitor_name VARCHAR(100) NOT NULL UNIQUE,
    location VARCHAR(200),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    is_processor BOOLEAN DEFAULT FALSE,
    processor_claimed_at TIMESTAMP NULL,
    INDEX idx_monitor_name (monitor_name),
    INDEX idx_active (is_active),
    INDEX idx_processor (is_processor, processor_claimed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- BLE Devices table: tracks discovered BLE devices
CREATE TABLE IF NOT EXISTS ble_devices (
    device_id INT AUTO_INCREMENT PRIMARY KEY,
    mac_address VARCHAR(17) NOT NULL UNIQUE,
    device_name VARCHAR(200),
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_mac_address (mac_address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Device Sightings table: records each detection with best RSSI per interval
-- This table stores only the best RSSI reading per device per 5-minute interval
CREATE TABLE IF NOT EXISTS device_sightings (
    sighting_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    device_id INT NOT NULL,
    monitor_id INT NOT NULL,
    rssi INT NOT NULL,
    interval_start TIMESTAMP NOT NULL,
    interval_end TIMESTAMP NOT NULL,
    sighting_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    extra_data JSON,
    FOREIGN KEY (device_id) REFERENCES ble_devices(device_id) ON DELETE CASCADE,
    FOREIGN KEY (monitor_id) REFERENCES monitors(monitor_id) ON DELETE CASCADE,
    INDEX idx_device_interval (device_id, interval_start),
    INDEX idx_monitor_timestamp (monitor_id, sighting_timestamp),
    INDEX idx_interval_start (interval_start),
    INDEX idx_rssi (rssi),
    UNIQUE KEY unique_device_interval (device_id, interval_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Staging table for collecting readings before selecting best RSSI
-- This temporary table holds all readings during a 5-minute interval
CREATE TABLE IF NOT EXISTS sighting_staging (
    staging_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    mac_address VARCHAR(17) NOT NULL,
    device_name VARCHAR(200),
    monitor_id INT NOT NULL,
    rssi INT NOT NULL,
    interval_start TIMESTAMP NOT NULL,
    scan_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT FALSE,
    INDEX idx_staging_interval (interval_start, processed),
    INDEX idx_staging_mac (mac_address, interval_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- View for hourly device counts per monitor
CREATE OR REPLACE VIEW hourly_device_counts AS
SELECT 
    m.monitor_name,
    m.location,
    DATE_FORMAT(ds.interval_start, '%Y-%m-%d %H:00:00') as hour_start,
    COUNT(DISTINCT ds.device_id) as unique_devices,
    COUNT(*) as total_sightings,
    AVG(ds.rssi) as avg_rssi,
    MIN(ds.rssi) as min_rssi,
    MAX(ds.rssi) as max_rssi
FROM device_sightings ds
JOIN monitors m ON ds.monitor_id = m.monitor_id
GROUP BY m.monitor_id, m.monitor_name, m.location, DATE_FORMAT(ds.interval_start, '%Y-%m-%d %H:00:00')
ORDER BY hour_start DESC, m.monitor_name;

-- View for recent device activity
CREATE OR REPLACE VIEW recent_device_activity AS
SELECT 
    bd.mac_address,
    bd.device_name,
    m.monitor_name,
    ds.rssi,
    ds.interval_start,
    ds.sighting_timestamp
FROM device_sightings ds
JOIN ble_devices bd ON ds.device_id = bd.device_id
JOIN monitors m ON ds.monitor_id = m.monitor_id
WHERE ds.sighting_timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
ORDER BY ds.sighting_timestamp DESC;

-- Stored procedure to process staging data and select best RSSI per interval
DELIMITER //

CREATE PROCEDURE process_interval_best_rssi(IN p_interval_start TIMESTAMP)
BEGIN
    -- For each device in the staging table for this interval,
    -- insert only the record with the best (highest/least negative) RSSI
    
    INSERT INTO device_sightings (device_id, monitor_id, rssi, interval_start, interval_end, sighting_timestamp)
    SELECT 
        bd.device_id,
        best_readings.monitor_id,
        best_readings.rssi,
        best_readings.interval_start,
        DATE_ADD(best_readings.interval_start, INTERVAL 5 MINUTE) as interval_end,
        best_readings.scan_timestamp
    FROM (
        SELECT 
            st.mac_address,
            st.monitor_id,
            st.rssi,
            st.interval_start,
            st.scan_timestamp,
            ROW_NUMBER() OVER (PARTITION BY st.mac_address ORDER BY st.rssi DESC) as rn
        FROM sighting_staging st
        WHERE st.interval_start = p_interval_start
          AND st.processed = FALSE
    ) best_readings
    JOIN ble_devices bd ON bd.mac_address = best_readings.mac_address
    WHERE best_readings.rn = 1
    ON DUPLICATE KEY UPDATE
        monitor_id = VALUES(monitor_id),
        rssi = VALUES(rssi),
        sighting_timestamp = VALUES(sighting_timestamp);
    
    -- Mark staged records as processed
    UPDATE sighting_staging
    SET processed = TRUE
    WHERE interval_start = p_interval_start
      AND processed = FALSE;
      
END //

DELIMITER ;

-- Cleanup procedure to remove old staging data
DELIMITER //

CREATE PROCEDURE cleanup_old_staging(IN days_to_keep INT)
BEGIN
    DELETE FROM sighting_staging
    WHERE scan_timestamp < DATE_SUB(NOW(), INTERVAL days_to_keep DAY);
END //

DELIMITER ;
