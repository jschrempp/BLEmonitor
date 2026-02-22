# BLE Monitor Quick Reference

## Quick Start Commands

### Initial Setup (One Time)
```bash
# Run setup script
./setup.sh

# Create database (on MySQL server)
mysql -u root -p < schema.sql

# Create database user
create user 'ble_user'@'localhost' identified by 'MAKE A PASSWORD';

# Grant user permissions
grant all privileges on ble_monitor.* to 'ble_user'@'localhost';

# Edit configuration
nano config.ini

# Test database connection
python3 test_db.py
```

### Running the Monitor

#### Manual Mode
```bash
# Single scan (testing)
python3 ble_monitor.py --single

# Continuous monitoring
python3 ble_monitor.py
```

#### As a Service
```bash
# Install service
./service.sh install

# Enable auto-start
./service.sh enable

# Start service
./service.sh start

# Check status
./service.sh status

# View logs
./service.sh logs

# Stop service
./service.sh stop
```

### Generating Reports

#### Hourly Device Counts
```bash
# Last 24 hours
python3 ble_reporter.py

# Specific date range
python3 ble_reporter.py --start-date 2026-02-01 --end-date 2026-02-15

# Specific monitor
python3 ble_reporter.py --monitor RPi_Monitor_01

# CSV output
python3 ble_reporter.py --format csv > report.csv
```

#### Monitor Summary
```bash
python3 ble_reporter.py --report monitors
```

#### Device Summary
```bash
# Last 24 hours
python3 ble_reporter.py --report devices

# Last week
python3 ble_reporter.py --report devices --hours 168
```

## Database Queries

### Quick Status Check
```sql
-- Active monitors
SELECT monitor_name, location, last_seen, is_active 
FROM monitors WHERE is_active = TRUE;

-- Recent sightings
SELECT * FROM recent_device_activity LIMIT 20;

-- Today's hourly counts
SELECT * FROM hourly_device_counts 
WHERE hour_start >= CURDATE()
ORDER BY hour_start DESC;
```

### Device Statistics
```sql
-- Most seen devices (last 24 hours)
SELECT 
    bd.mac_address,
    bd.device_name,
    COUNT(*) as sightings,
    AVG(ds.rssi) as avg_rssi,
    MAX(ds.rssi) as best_rssi
FROM device_sightings ds
JOIN ble_devices bd ON ds.device_id = bd.device_id
WHERE ds.sighting_timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY bd.device_id
ORDER BY sightings DESC
LIMIT 20;
```

### Monitor Performance
```sql
-- Sightings per monitor (last 24 hours)
SELECT 
    m.monitor_name,
    m.location,
    COUNT(*) as total_sightings,
    COUNT(DISTINCT ds.device_id) as unique_devices
FROM device_sightings ds
JOIN monitors m ON ds.monitor_id = m.monitor_id
WHERE ds.sighting_timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY m.monitor_id
ORDER BY total_sightings DESC;
```

## Troubleshooting Commands

### Check BLE Hardware
```bash
# Bluetooth status
sudo systemctl status bluetooth

# Restart Bluetooth
sudo systemctl restart bluetooth

# bring bluetooth up
sudo rfkill unblock bluetooth
sudo hciconfig hci0 up

# List BLE adapters
hciconfig

# Manual BLE scan
sudo hcitool lescan
```

### Check Service Status
```bash
# Service status
./service.sh status

# Recent logs
./service.sh logs

# Or using journalctl
sudo journalctl -u ble-monitor.service -n 100

# Check if process is running
ps aux | grep ble_monitor
```

### Database Connection
```bash
# Test connection
python3 test_db.py

# Connect manually
mysql -h <host> -u ble_user -p ble_monitor

# Check tables
mysql -h <host> -u ble_user -p -e "USE ble_monitor; SHOW TABLES;"
```

### View Logs
```bash
# Application log
tail -f ble_monitor.log

# Service log
./service.sh logs

# System log
sudo journalctl -xe
```

## Configuration Tips

### Optimal Settings for Different Scenarios

**High Traffic Area (many devices)**:
```ini
scan_interval_seconds = 300  # 5 minutes
scan_duration_seconds = 15   # Longer scan to catch more devices
```

**Low Traffic Area (few devices)**:
```ini
scan_interval_seconds = 180  # 3 minutes
scan_duration_seconds = 8    # Shorter scan is sufficient
```

**Battery-Powered Setup**:
```ini
scan_interval_seconds = 600  # 10 minutes
scan_duration_seconds = 5    # Minimal scan time
```

### Multiple Monitor Naming Convention
```
RPi_Monitor_<Location>_<Number>

Examples:
- RPi_Monitor_LivingRoom_01
- RPi_Monitor_Bedroom_01
- RPi_Monitor_Garage_01
- RPi_Monitor_Office_01
```

## Maintenance Tasks

### Daily
- Check service status: `./service.sh status`
- Review recent logs for errors

### Weekly
- Generate and review weekly report
- Check database size: `SELECT table_name, round(((data_length + index_length) / 1024 / 1024), 2) AS "Size (MB)" FROM information_schema.TABLES WHERE table_schema = "ble_monitor";`

### Monthly
- Clean up old staging data: `CALL cleanup_old_staging(7);`
- Archive old sighting data (>90 days)
- Update system: `sudo apt update && sudo apt upgrade`
- Check disk space: `df -h`

## File Locations

```
Project Directory:
├── ble_monitor.py          # Main scanner
├── ble_reporter.py          # Report generator
├── test_db.py               # Database test utility
├── setup.sh                 # Setup script
├── service.sh               # Service manager
├── schema.sql               # Database schema
├── config.ini               # Your config (create from example)
├── config.ini.example       # Config template
├── requirements.txt         # Python dependencies
├── ble-monitor.service      # Systemd service template
├── ble_monitor.log         # Application logs
└── README.md               # Full documentation

System Service:
/etc/systemd/system/ble-monitor.service

Logs:
- Application: ./ble_monitor.log
- Service: sudo journalctl -u ble-monitor.service
```

## Common Issues and Solutions

### Issue: "Permission denied" for BLE scanning
```bash
# Add user to bluetooth group
sudo usermod -a -G bluetooth $USER

# Grant capabilities
sudo setcap cap_net_raw,cap_net_admin+eip $(readlink -f venv/bin/python3)

# Log out and back in
```

### Issue: No devices found
```bash
# Check Bluetooth is working
hciconfig
sudo hcitool lescan

# Increase scan duration in config.ini
scan_duration_seconds = 15

# Check if devices are in range and have BLE enabled
```

### Issue: Database connection fails
```bash
# Test connection
python3 test_db.py

# Check MySQL is running
sudo systemctl status mysql

# Verify credentials in config.ini
# Check firewall if using remote database
```

### Issue: Service won't start
```bash
# Check service status
./service.sh status

# View detailed logs
./service.sh logs

# Test manual run
python3 ble_monitor.py --single

# Check file permissions
ls -la ble_monitor.py
```
