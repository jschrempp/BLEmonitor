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

### Database Schema
- **monitors**: Tracks each monitoring device with location and status
- **ble_devices**: Catalog of discovered BLE devices
- **device_sightings**: Final sightings with best RSSI per interval
- **sighting_staging**: Temporary storage for all readings before selecting best RSSI

### Best RSSI Selection Logic
1. Each monitor scans for BLE devices and stores readings in the staging table
2. At the end of each 5-minute interval, the system processes staged data
3. For each device, only the reading with the highest RSSI (least negative) is kept
4. This ensures only the closest/strongest monitor's reading is logged per interval

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

[database]
host = localhost                    # MySQL server IP/hostname
port = 3306
user = ble_user
password = your_password
database = ble_monitor
```

**Important**: Each monitor must have a unique `name` in the config file!

### 7. Test the Installation

Run a single scan to verify everything works:

```bash
python3 ble_monitor.py --single
```

Check the logs:
```bash
tail -f ble_monitor.log
```

## Running the Monitor

### Start Manually

```bash
# Activate virtual environment
source venv/bin/activate

# Run continuously
python3 ble_monitor.py

# Or run single scan for testing
python3 ble_monitor.py --single
```

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
4. Start the monitor service on each device

Example configurations:

**Monitor 1 (Living Room)**:
```ini
[monitor]
name = RPi_Monitor_LivingRoom
location = Living Room
```

**Monitor 2 (Bedroom)**:
```ini
[monitor]
name = RPi_Monitor_Bedroom
location = Bedroom
```

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

```bash
# Test MySQL connection
mysql -h <host> -u ble_user -p ble_monitor

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
