# BLE Monitor System

A comprehensive Raspberry Pi application for monitoring Bluetooth Low Energy (BLE) devices in an area, logging their RSSI (signal strength), and storing data in a MySQL database. The system supports multiple monitors reporting to a single database and automatically selects the best RSSI reading per device per interval.

## Features

- **Automatic BLE Scanning**: Scans for BLE devices every 5 minutes (configurable)
- **Multi-Monitor Support**: Multiple Raspberry Pi monitors can report to one central database
- **Best RSSI Selection**: Automatically logs only the monitor with the best RSSI per device per interval
- **Comprehensive Reporting**: Generate hourly device count reports by monitor
- **Scalable Database Design**: MySQL schema optimized for multiple monitors and high-volume data
- **Configurable**: Easy configuration via INI file
- **Logging**: Detailed logging for debugging and monitoring

## System Architecture

### How the Monitor Works

The BLE Monitor application (`ble_monitor.py`) continuously scans for Bluetooth Low Energy devices and intelligently stores them in a MySQL database with automatic deduplication across multiple monitors.

**Monitor Operation Flow:**

1. **Initialization**: Monitor registers itself in the database with name, location, and status
2. **Scan Cycle**: Every 5 minutes (configurable), performs a BLE scan for 10 seconds (configurable)
3. **Data Collection**: Captures MAC address, device name, and RSSI (signal strength) for each device
4. **Staging**: Writes all readings to the `sighting_staging` table with interval timestamp
5. **Processing**: Automatically selects the best RSSI reading per device per interval
6. **Storage**: Writes deduplicated data to the final `device_sightings` table
7. **Repeat**: Sleeps until the next interval and repeats

**Key Features:**
- **Automatic retry**: Recovers from database connection errors
- **Graceful shutdown**: Handles CTRL+C and systemd stop signals
- **Detailed logging**: Logs all operations to both file and console
- **Simulation mode**: Can run without BLE hardware for testing

### Database Schema

- **monitors**: Tracks each monitoring device with location and status
- **ble_devices**: Catalog of discovered BLE devices (MAC addresses and names)
- **device_sightings**: Final sightings with best RSSI per interval
- **sighting_staging**: Temporary storage for all readings before selecting best RSSI

### Best RSSI Selection Logic (Multi-Monitor Coordination)

When multiple monitors detect the same device during a 5-minute interval, the system automatically selects the best reading:

1. **Each monitor scans independently**: All monitors scan for BLE devices at their configured intervals
2. **Staging table collects all readings**: Each monitor writes its findings to `sighting_staging` with:
   - MAC address and device name
   - Monitor ID
   - RSSI value
   - Interval start timestamp (5-minute boundary)
3. **Best RSSI selection**: After writing to staging, the monitor calls stored procedure `process_interval_best_rssi()` which:
   - Groups all readings by device and interval
   - Selects the reading with the highest RSSI (least negative = strongest signal)
   - Inserts the best reading into `device_sightings`
   - Marks staged records as processed
4. **Result**: Only one record per device per 5-minute interval in the final table, from the monitor with the best signal

**Example:**
- Monitor "Living Room" sees device AA:BB:CC:DD:EE:FF with RSSI -65
- Monitor "Kitchen" sees same device with RSSI -72
- Only the Living Room reading (-65) is stored in `device_sightings`

This ensures accurate location tracking (closest monitor) and prevents duplicate data.

### Processor Role (Multi-Monitor Coordination)

**Problem**: When multiple monitors run independently, they can't all process intervals simultaneously without conflicts.

**Solution**: Only ONE monitor is designated as the "processor" - it's the only one that runs `process_interval_best_rssi()`.

**How it works:**

1. **Configuration**: Set `process_intervals = true` in config.ini for ONLY ONE monitor
2. **Startup**: The designated monitor attempts to claim the processor role:
   - Checks if another monitor already claimed it (within last 10 minutes)
   - Fails to start if another active processor exists
   - Claims the role if no active processor or stale claim (>10 min old)
3. **Operation**: 
   - **Processor monitor**: Scans → writes to staging → waits 60s → processes interval → repeats
   - **Non-processor monitors**: Scans → writes to staging → repeats (no processing)
4. **Heartbeat**: Processor updates its claim timestamp every cycle to show it's alive
5. **Failover**: If processor monitor dies (no heartbeat for 10+ minutes), another monitor configured with `process_intervals=true` can take over

**Benefits:**
- ✅ Prevents race conditions and duplicate processing
- ✅ Wait period (60s) ensures all monitors finish scanning before processing
- ✅ Automatic failover if processor monitor fails
- ✅ Clear error messages if multiple processors configured incorrectly

**Important**: Only configure ONE monitor with `process_intervals = true` to avoid conflicts!

### Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    BLE Monitor Application                       │
│                    (ble_monitor.py)                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────┐
        │  1. Initialize & Register Monitor        │
        │     - Connect to database                │
        │     - Create/update monitor record       │
        │     - Get monitor_id                     │
        │     - Try claim processor role (if cfg)  │
        └─────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────┐
        │  2. Calculate 5-Minute Interval Start    │
        │     (e.g., 14:35:00, 14:40:00)          │
        └─────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────┐
        │  3. Scan for BLE Devices (10 seconds)   │
        │     - Discover nearby BLE devices        │
        │     - Collect MAC, name, RSSI            │
        └─────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────┐
        │  4. Write to Staging Table               │
        │     INSERT INTO sighting_staging         │
        │     (ALL monitors do this)               │
        └─────────────────────────────────────────┘
                              │
                   ┌──────────┴──────────┐
                   │                     │
           Is Processor?             Is Processor?
               NO                        YES
                   │                     │
                   ▼                     ▼
        ┌──────────────────┐  ┌─────────────────────────┐
        │  Skip Processing  │  │  5. Wait 60 seconds     │
        │  (Scanner only)   │  │  (for other monitors)   │
        └──────────────────┘  └─────────────────────────┘
                   │                     │
                   │                     ▼
                   │          ┌─────────────────────────┐
                   │          │  6. Ensure Devices Exist│
                   │          │  INSERT INTO ble_devices│
                   │          └─────────────────────────┘
                   │                     │
                   │                     ▼
                   │          ┌─────────────────────────┐
                   │          │  7. Process Best RSSI   │
                   │          │  CALL process_interval   │
                   │          │  _best_rssi()            │
                   │          │  - Group by device       │
                   │          │  - SELECT MAX(rssi)      │
                   │          │  - INSERT device_sightings│
                   │          │  - Mark staging processed│
                   │          └─────────────────────────┘
                   │                     │
                   │                     ▼
                   │          ┌─────────────────────────┐
                   │          │  8. Refresh processor   │
                   │          │     claim (heartbeat)    │
                   │          └─────────────────────────┘
                   │                     │
                   └──────────┬──────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────┐
        │  9. Sleep Until Next Interval            │
        │     (Processor: 300s - scan - 60s wait) │
        │     (Scanner: 300s - scan)               │
        └─────────────────────────────────────────┘
                              │
                              └──────► Loop back to step 2
```

**Database Tables Interaction:**
- `monitors` ← Monitor registers/updates itself, processor claims role
- `sighting_staging` ← Raw scan data from ALL monitors
- `ble_devices` ← Device catalog (auto-created by processor)
- `device_sightings` ← Final deduplicated data (best RSSI, written by processor)

**Key Points:**
- ALL monitors write to `sighting_staging`
- ONLY the processor monitor runs `process_interval_best_rssi()`
- Processor waits 60s to ensure all monitors finish scanning before processing

## Requirements

### Hardware
- Raspberry Pi (3, 4, or 5 recommended) with Bluetooth support
- Network connection to MySQL server

### Software
- Python 3.7 or higher
- MySQL 5.7 or higher (or MariaDB 10.3+)
- Bluetooth support (built into most RPi models)

## Installation

### 1. Install System Dependencies

```bash
# Update system
sudo apt update
sudo apt upgrade -y

# Install Bluetooth tools
sudo apt install -y bluetooth bluez libbluetooth-dev

# Enable Bluetooth if blocked by RF-kill
sudo rfkill unblock bluetooth
sudo hciconfig hci0 up

# Verify Bluetooth is working
hciconfig

# Install MySQL client (if database is remote)
sudo apt install -y default-mysql-client

# Install Python pip
sudo apt install -y python3-pip python3-venv
```

### 2. Clone or Download This Repository

```bash
cd ~
git clone <your-repo-url> ble_monitor
cd ble_monitor
```

### 3. Create Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Python Dependencies

```bash
pip3 install -r requirements.txt
```

### 5. Set Up MySQL Database

On your MySQL server, create the database and user:

```sql
-- Create database
CREATE DATABASE ble_monitor;

-- Create user (replace 'your_password' with a strong password)
CREATE USER 'ble_user'@'%' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON ble_monitor.* TO 'ble_user'@'%';
FLUSH PRIVILEGES;
```

**Configure MariaDB/MySQL for Remote Access** (required for multiple monitors):

```bash
# Edit MariaDB configuration
sudo nano /etc/mysql/mariadb.conf.d/50-server.cnf
```

Find and change the bind-address:
```ini
# Change this:
bind-address = 127.0.0.1

# To this (listen on all interfaces):
bind-address = 0.0.0.0
```

Restart MariaDB and verify:
```bash
# Restart the service
sudo systemctl restart mariadb

# Verify it's listening on all interfaces (should show 0.0.0.0:3306)
sudo netstat -tlnp | grep 3306

# If you have a firewall, allow MySQL port
sudo ufw allow 3306/tcp
# Or allow only from your local network (more secure):
sudo ufw allow from 192.168.0.0/16 to any port 3306
```

Import the schema:

```bash
mysql -u ble_user -p ble_monitor < schema.sql
```

### 6. Configure the Application

```bash
cp config.ini.example config.ini
nano config.ini
```

Edit the configuration:

```ini
[monitor]
name = RPi_Monitor_01              # UNIQUE name for each monitor
location = Living Room              # Physical location
scan_interval_seconds = 300         # 5 minutes
scan_duration_seconds = 10          # How long each scan takes
process_intervals = false           # IMPORTANT: Only ONE monitor should be 'true'
processor_wait_seconds = 60         # Wait time before processing (if processor)

[database]
host = localhost                    # MySQL server IP/hostname
port = 3306
user = ble_user
password = your_password
database = ble_monitor
```

**Important Configuration Notes:**

1. **Each monitor must have a unique `name`** in the config file
2. **Only ONE monitor should have `process_intervals = true`**
   - This monitor processes intervals (selects best RSSI)
   - It waits 60 seconds after scanning for other monitors to finish
   - All other monitors should have `process_intervals = false`
3. If you accidentally configure multiple monitors with `process_intervals = true`, the second one will fail to start with an error message

### 7. Test the Installation

Run a single scan to verify everything works:

```bash
# Activate virtual environment
source venv/bin/activate

# Run a single test scan
python3 ble_monitor.py --single
```

Check the logs:
```bash
tail -f ble_monitor.log
```

You should see output like:
```
2026-02-22 15:30:18 - BLEMonitor - INFO - Running single scan mode
2026-02-22 15:30:18 - BLEMonitor - INFO - Monitor registered: RPi_Monitor_01 (ID: 1)
2026-02-22 15:30:18 - BLEMonitor - INFO - Starting scan cycle for interval: 2026-02-22 15:30:00
2026-02-22 15:30:18 - BLEMonitor - INFO - Starting BLE scan for 10 seconds...
2026-02-22 15:30:28 - BLEMonitor - INFO - Scan complete. Found 47 devices
2026-02-22 15:30:28 - BLEMonitor - INFO - Stored 47 sightings in staging for interval 2026-02-22 15:30:00
2026-02-22 15:30:28 - BLEMonitor - INFO - Processed interval 2026-02-22 15:30:00 - selected best RSSI per device
2026-02-22 15:30:28 - BLEMonitor - INFO - Single scan complete
```

## Running the Monitor

### Command-Line Options

```bash
python3 ble_monitor.py [options]

Options:
  -c, --config FILE    Configuration file path (default: config.ini)
  --single             Run single scan and exit (for testing)
  -h, --help          Show help message
```

**Examples:**
```bash
# Continuous monitoring (runs forever)
python3 ble_monitor.py

# Single scan test
python3 ble_monitor.py --single

# Use alternate config file
python3 ble_monitor.py -c /path/to/custom_config.ini

# Test with custom config
python3 ble_monitor.py -c test_config.ini --single
```

### Start Manually

```bash
# Activate virtual environment
source venv/bin/activate

# Run continuously (press CTRL+C to stop)
python3 ble_monitor.py

# Monitor logs in another terminal
tail -f ble_monitor.log
```

**What happens in continuous mode:**
- Scans every 5 minutes (or configured interval)
- Automatically reconnects if database connection is lost
- Logs all operations to `ble_monitor.log` and console
- Handles CTRL+C gracefully for shutdown

### Run as a System Service

Create a systemd service file:

```bash
sudo nano /etc/systemd/system/ble-monitor.service
```

Add this content (adjust paths as needed):

```ini
[Unit]
Description=BLE Monitor Service
After=network.target mysql.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/ble_monitor
ExecStart=/home/pi/ble_monitor/venv/bin/python3 /home/pi/ble_monitor/ble_monitor.py
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ble-monitor.service
sudo systemctl start ble-monitor.service
```

Check service status:

```bash
sudo systemctl status ble-monitor.service
sudo journalctl -u ble-monitor.service -f
```

## Monitoring Monitor Health

### Check if Monitor is Running and Active

```bash
# Check service status
sudo systemctl status ble-monitor.service

# View recent log entries
tail -n 50 ble_monitor.log

# Check when monitor last reported
mysql -u ble_user -p ble_monitor -e "
SELECT 
    monitor_name, 
    location, 
    last_seen,
    TIMESTAMPDIFF(MINUTE, last_seen, NOW()) as minutes_ago,
    is_active
FROM monitors;"
```

### Verify Data is Being Written

```bash
# Check recent sightings
mysql -u ble_user -p ble_monitor -e "
SELECT COUNT(*) as recent_sightings
FROM device_sightings 
WHERE sighting_timestamp >= DATE_SUB(NOW(), INTERVAL 1 HOUR);"

# Check staging table status
mysql -u ble_user -p ble_monitor -e "
SELECT processed, COUNT(*) as count 
FROM sighting_staging 
GROUP BY processed;"

# View most recent scan data
mysql -u ble_user -p ble_monitor -e "
SELECT * FROM device_sightings 
ORDER BY sighting_timestamp DESC 
LIMIT 10;"
```

### Monitor Performance Metrics

```sql
-- Average devices per scan (last 24 hours)
SELECT 
    m.monitor_name,
    COUNT(DISTINCT ds.device_id) / COUNT(DISTINCT ds.interval_start) as avg_devices_per_scan,
    COUNT(*) as total_sightings
FROM device_sightings ds
JOIN monitors m ON ds.monitor_id = m.monitor_id
WHERE ds.sighting_timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY m.monitor_id;

-- Check for gaps in monitoring
SELECT 
    interval_start,
    COUNT(DISTINCT monitor_id) as monitor_count,
    COUNT(*) as device_count
FROM device_sightings 
WHERE interval_start >= DATE_SUB(NOW(), INTERVAL 2 HOUR)
GROUP BY interval_start
ORDER BY interval_start DESC;
```

### Dashboard for Real-Time Monitoring

Use the included dashboard for live monitoring:

```bash
# Run live dashboard (refreshes every 30 seconds)
python3 dashboard.py

# Or run once and exit
python3 dashboard.py --once
```

## Generating Reports

### Hourly Device Count Report

```bash
# Last 24 hours (default)
python3 ble_reporter.py --report hourly

# Specific date range
python3 ble_reporter.py --report hourly --start-date 2026-02-01 --end-date 2026-02-15

# Filter by specific monitor
python3 ble_reporter.py --report hourly --monitor RPi_Monitor_01

# Output as CSV
python3 ble_reporter.py --report hourly --format csv > report.csv

# Output as JSON
python3 ble_reporter.py --report hourly --format json > report.json
```

### Monitor Summary

```bash
python3 ble_reporter.py --report monitors
```

### Device Summary

```bash
# Last 24 hours (default)
python3 ble_reporter.py --report devices

# Last 7 days
python3 ble_reporter.py --report devices --hours 168
```

## Setting Up Multiple Monitors

To set up multiple Raspberry Pi monitors:

1. Install the application on each RPi following the installation steps
2. Ensure each monitor has a **unique name** in `config.ini`
3. Configure all monitors to connect to the **same MySQL database**
4. **Designate ONE monitor as the processor** (set `process_intervals = true`)
5. Set all other monitors with `process_intervals = false`
6. Start the monitor service on each device

Example configurations:

**Monitor 1 (Living Room) - Processor**:
```ini
[monitor]
name = RPi_Monitor_LivingRoom
location = Living Room
process_intervals = true          # This monitor processes intervals
processor_wait_seconds = 60
```

**Monitor 2 (Bedroom) - Scanner Only**:
```ini
[monitor]
name = RPi_Monitor_Bedroom
location = Bedroom
process_intervals = false         # This monitor only scans
```

**Monitor 3 (Kitchen) - Scanner Only**:
```ini
[monitor]
name = RPi_Monitor_Kitchen
location = Kitchen
process_intervals = false         # This monitor only scans
```

**How it works:**
- **All monitors** scan for BLE devices and write to the staging table
- **Only the processor monitor** (Living Room in this example) runs the stored procedure to select best RSSI
- The processor waits 60 seconds after scanning to ensure other monitors finish before processing
- If the processor monitor fails, you can start another monitor with `process_intervals = true` to take over

The system will automatically select the best RSSI reading per device per interval across all monitors.

## Database Maintenance

### View Recent Activity

```sql
-- Recent device sightings
SELECT * FROM recent_device_activity LIMIT 50;

-- Hourly counts
SELECT * FROM hourly_device_counts 
WHERE hour_start >= DATE_SUB(NOW(), INTERVAL 7 DAY);
```

### Cleanup Old Staging Data

```sql
-- Clean up staging data older than 7 days
CALL cleanup_old_staging(7);
```

### Archive Old Data

To keep the database performant, consider archiving old data:

```sql
-- Archive data older than 90 days
CREATE TABLE device_sightings_archive LIKE device_sightings;

INSERT INTO device_sightings_archive 
SELECT * FROM device_sightings 
WHERE interval_start < DATE_SUB(NOW(), INTERVAL 90 DAY);

DELETE FROM device_sightings 
WHERE interval_start < DATE_SUB(NOW(), INTERVAL 90 DAY);
```

## Troubleshooting

### Monitor and Database Writer Issues

**Problem: "Another monitor is already the interval processor" error**
This means you have two monitors configured with `process_intervals = true`. Only ONE monitor can be the processor.

```bash
# Solution 1: Fix config on the second monitor
nano config.ini
# Change: process_intervals = false

# Solution 2: Check which monitor is the processor
mysql -u ble_user -p ble_monitor -e "
SELECT monitor_name, is_processor, processor_claimed_at 
FROM monitors 
WHERE is_processor = TRUE;"

# Solution 3: If the processor monitor is dead, clear stale claim
mysql -u ble_user -p ble_monitor -e "
UPDATE monitors 
SET is_processor = FALSE, processor_claimed_at = NULL 
WHERE processor_claimed_at < DATE_SUB(NOW(), INTERVAL 10 MINUTE);"
```

**Problem: Intervals not being processed (data stays in staging)**
Check if any monitor is configured as processor:

```bash
# Check processor status
mysql -u ble_user -p ble_monitor -e "
SELECT monitor_name, is_processor, processor_claimed_at, last_seen
FROM monitors;"

# Check staging table for unprocessed data
mysql -u ble_user -p ble_monitor -e "
SELECT interval_start, processed, COUNT(*) 
FROM sighting_staging 
GROUP BY interval_start, processed 
ORDER BY interval_start DESC 
LIMIT 10;"

# Solution: Ensure ONE monitor has process_intervals = true
nano config.ini
# Set: process_intervals = true
# Then restart that monitor
```

**Problem: Monitor fails to start**
```bash
# Check config file exists and is readable
cat config.ini

# Verify database connection settings
python3 test_db.py

# Check Python dependencies
pip3 list | grep -E "bleak|mysql-connector"
```

**Problem: "No devices found" in logs**
```bash
# Verify Bluetooth is working
sudo hciconfig
sudo hcitool lescan

# Check BLE adapter is up
sudo hciconfig hci0 up

# Try increasing scan duration in config.ini
scan_duration_seconds = 15
```

**Problem: Database connection errors**
```bash
# Verify database exists
mysql -u ble_user -p -e "SHOW DATABASES;"

# Check if stored procedures exist
mysql -u ble_user -p ble_monitor -e "SHOW PROCEDURE STATUS WHERE Db = 'ble_monitor';"

# Recreate schema if needed
mysql -u ble_user -p ble_monitor < schema.sql
```

**Problem: Staging table filling up**
```sql
-- Check staging table size
SELECT COUNT(*), processed FROM sighting_staging GROUP BY processed;

-- Clean up processed staging records
CALL cleanup_old_staging(1);

-- Check for unprocessed records stuck
SELECT interval_start, COUNT(*) 
FROM sighting_staging 
WHERE processed = FALSE 
GROUP BY interval_start 
ORDER BY interval_start DESC;
```

**Problem: Duplicate device records in same interval**
```sql
-- Check for duplicates (should return 0)
SELECT device_id, interval_start, COUNT(*) as count
FROM device_sightings
GROUP BY device_id, interval_start
HAVING count > 1;

-- If duplicates exist, the stored procedure may not be running
-- Verify it exists:
SHOW CREATE PROCEDURE process_interval_best_rssi;
```

**Problem: Monitor stops responding**
```bash
# Check if process is running
ps aux | grep ble_monitor.py

# Check system resources
free -h
df -h

# Check for errors in log
tail -n 100 ble_monitor.log | grep ERROR

# Restart the monitor
sudo systemctl restart ble-monitor.service
```

### BLE Scanning Issues

If BLE scanning fails:

```bash
# Check Bluetooth status
sudo systemctl status bluetooth

# Restart Bluetooth
sudo systemctl restart bluetooth

# Check for Bluetooth devices
hciconfig
sudo hcitool lescan
```

### Permission Issues

If you get permission errors for BLE scanning:

```bash
# Add user to bluetooth group
sudo usermod -a -G bluetooth $USER

# Grant capabilities to Python
sudo setcap cap_net_raw,cap_net_admin+eip $(readlink -f $(which python3))
```

### Database Connection Issues

**Problem: "Can't connect to MySQL server" (Error 2003 or 111)**

This usually means MariaDB is only listening on localhost, not accepting remote connections.

```bash
# On MySQL server, check what interface it's listening on
sudo netstat -tlnp | grep 3306

# If you see 127.0.0.1:3306 (BAD - localhost only):
tcp        0      0 127.0.0.1:3306          0.0.0.0:*               LISTEN

# You need 0.0.0.0:3306 (GOOD - all interfaces):
tcp        0      0 0.0.0.0:3306            0.0.0.0:*               LISTEN
```

**Solution:**
```bash
# Edit MariaDB config
sudo nano /etc/mysql/mariadb.conf.d/50-server.cnf

# Change:
bind-address = 127.0.0.1
# To:
bind-address = 0.0.0.0

# Restart
sudo systemctl restart mariadb

# Verify
sudo netstat -tlnp | grep 3306

# Check firewall
sudo ufw allow 3306/tcp
```

**Problem: "Access denied for user"**

User may not have remote access permissions.

```sql
-- On MySQL server
mysql -u root -p

-- Check user permissions
SELECT user, host FROM mysql.user WHERE user = 'ble_user';

-- Grant remote access (% = any host)
CREATE USER 'ble_user'@'%' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON ble_monitor.* TO 'ble_user'@'%';
FLUSH PRIVILEGES;
```

**Test connection from remote monitor:**
```bash
# Test MySQL connection
mysql -h <host> -u ble_user -p ble_monitor

# Test port connectivity
telnet <host> 3306

# Check if MySQL service is running
sudo systemctl status mysql
```

### View Logs

```bash
# Application logs
tail -f ble_monitor.log

# System service logs
sudo journalctl -u ble-monitor.service -f
```

### mariadb will not start

# Check for running MariaDB processes
ps aux | grep -i maria
ps aux | grep -i mysql

# Kill any stray processes (use the PIDs you see)
sudo killall mariadbd
sudo killall mysqld

# Remove stale lock/pid files
sudo rm -f /var/lib/mysql/*.pid
sudo rm -f /var/run/mysqld/*.pid
sudo rm -f /var/run/mysqld/mysqld.sock

# Now start the service
sudo systemctl start mariadb

# Check status
sudo systemctl status mariadb


## File Structure

```
ble_monitor/
├── ble_monitor.py           # Main scanner application
├── ble_reporter.py           # Report generator
├── schema.sql                # Database schema
├── config.ini.example        # Configuration template
├── config.ini                # Your configuration (not in git)
├── requirements.txt          # Python dependencies
├── README.md                 # This file
├── ble_monitor.log          # Application logs (generated)
└── venv/                     # Python virtual environment (generated)
```

## Performance Considerations

- **Scan Duration**: 10 seconds is usually sufficient. Longer scans find more devices but increase system load.
- **Scan Interval**: 5 minutes (300 seconds) balances data granularity with system resources.
- **Database Indexing**: The schema includes proper indexes for query performance.
- **Staging Table**: Regularly clean up old staging data to maintain performance.

## Security Recommendations

1. **Database Security**:
   - Use strong passwords
   - Restrict database user permissions
   - Use SSL/TLS for remote database connections
   - Consider firewall rules to limit database access

2. **System Security**:
   - Keep Raspberry Pi OS updated
   - Use SSH key authentication
   - Configure firewall (ufw)
   - Run the service with minimal privileges

3. **Data Privacy**:
   - BLE MAC addresses can identify devices/individuals
   - Comply with local privacy regulations
   - Consider anonymizing MAC addresses if required

## Future Enhancements

Potential improvements:
- Web dashboard for real-time monitoring
- Email/SMS alerts for specific devices
- Machine learning for device classification
- Integration with Home Assistant or other smart home platforms
- REST API for external integrations

## License

[Add your license here]

## Support

[Add support contact information]

## Contributing

[Add contribution guidelines]
