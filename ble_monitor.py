#!/usr/bin/env python3
"""
BLE Monitor Scanner
Scans for BLE devices every 5 minutes and logs them to MySQL database.
Automatically selects the best RSSI reading per device per interval.
"""

import sys
import time
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import mysql.connector
from mysql.connector import Error
import configparser

# BLE scanning library - using bleak for cross-platform support
# On RPi, you can also use bluepy for better performance
try:
    from bleak import BleakScanner
    USE_BLEAK = True
except ImportError:
    USE_BLEAK = False
    print("Warning: bleak not installed. Install with: pip3 install bleak")
    print("Falling back to simulation mode for testing")


class BLEMonitor:
    """Main BLE monitoring application"""
    
    def __init__(self, config_file: str = 'config.ini'):
        """Initialize the BLE monitor with configuration"""
        self.config = self._load_config(config_file)
        self.monitor_id = None
        self.monitor_name = self.config['monitor']['name']
        self.scan_interval = int(self.config['monitor']['scan_interval_seconds'])
        self.scan_duration = int(self.config['monitor']['scan_duration_seconds'])
        self.is_processor = False  # Will be set during startup if configured
        self.db_config = {
            'host': self.config['database']['host'],
            'port': int(self.config['database']['port']),
            'user': self.config['database']['user'],
            'password': self.config['database']['password'],
            'database': self.config['database']['database']
        }
        
        # Setup logging
        log_level = getattr(logging, self.config['monitor'].get('log_level', 'INFO'))
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('ble_monitor.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger('BLEMonitor')
        
    def _load_config(self, config_file: str) -> configparser.ConfigParser:
        """Load configuration from INI file"""
        config = configparser.ConfigParser()
        config.read(config_file)
        
        # Validate required sections
        required_sections = ['monitor', 'database']
        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required configuration section: {section}")
        
        return config
    
    def _get_db_connection(self):
        """Create and return a database connection"""
        try:
            connection = mysql.connector.connect(**self.db_config)
            return connection
        except Error as e:
            self.logger.error(f"Database connection error: {e}")
            raise
    
    def _register_monitor(self) -> int:
        """Register this monitor in the database and return monitor_id"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            location = self.config['monitor'].get('location', '')
            description = self.config['monitor'].get('description', '')
            
            # Insert or update monitor
            query = """
                INSERT INTO monitors (monitor_name, location, description, is_active)
                VALUES (%s, %s, %s, TRUE)
                ON DUPLICATE KEY UPDATE
                    location = VALUES(location),
                    description = VALUES(description),
                    is_active = TRUE,
                    last_seen = CURRENT_TIMESTAMP
            """
            cursor.execute(query, (self.monitor_name, location, description))
            conn.commit()
            
            # Get monitor_id
            cursor.execute("SELECT monitor_id FROM monitors WHERE monitor_name = %s", (self.monitor_name,))
            result = cursor.fetchone()
            monitor_id = result[0]
            
            cursor.close()
            conn.close()
            
            self.logger.info(f"Monitor registered: {self.monitor_name} (ID: {monitor_id})")
            return monitor_id
            
        except Error as e:
            self.logger.error(f"Error registering monitor: {e}")
            raise
    
    def _try_claim_processor_role(self) -> bool:
        """Try to claim the interval processor role. Returns True if successful."""
        if not self.config['monitor'].getboolean('process_intervals', False):
            self.logger.info("This monitor is not configured to process intervals")
            return False
        
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            # Check for existing active processor (claimed within last 10 minutes)
            cursor.execute("""
                SELECT monitor_name, processor_claimed_at 
                FROM monitors 
                WHERE is_processor = TRUE 
                AND processor_claimed_at > DATE_SUB(NOW(), INTERVAL 10 MINUTE)
                AND monitor_name != %s
            """, (self.monitor_name,))
            
            existing = cursor.fetchone()
            
            if existing:
                self.logger.error(
                    f"Another monitor '{existing[0]}' is already the interval processor "
                    f"(claimed at {existing[1]}). Only ONE monitor can process intervals. "
                    f"Please set process_intervals=false in config.ini or stop the other processor."
                )
                cursor.close()
                conn.close()
                return False
            
            # Clear any stale processor claims (older than 10 minutes = dead processor)
            cursor.execute("""
                UPDATE monitors 
                SET is_processor = FALSE, processor_claimed_at = NULL
                WHERE is_processor = TRUE 
                AND (processor_claimed_at IS NULL OR processor_claimed_at <= DATE_SUB(NOW(), INTERVAL 10 MINUTE))
            """)
            
            if cursor.rowcount > 0:
                self.logger.warning(f"Cleared {cursor.rowcount} stale processor claim(s)")
            
            # Claim processor role for this monitor
            cursor.execute("""
                UPDATE monitors 
                SET is_processor = TRUE, processor_claimed_at = NOW()
                WHERE monitor_name = %s
            """, (self.monitor_name,))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            self.logger.info(f"✓ Successfully claimed interval processor role")
            return True
            
        except Error as e:
            self.logger.error(f"Error claiming processor role: {e}")
            return False
    
    def _refresh_processor_claim(self):
        """Refresh processor claim timestamp (heartbeat) to show we're still active"""
        if not self.is_processor:
            return
        
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE monitors 
                SET processor_claimed_at = NOW()
                WHERE monitor_name = %s AND is_processor = TRUE
            """, (self.monitor_name,))
            conn.commit()
            cursor.close()
            conn.close()
            self.logger.debug("Refreshed processor claim timestamp")
        except Error as e:
            self.logger.warning(f"Error refreshing processor claim: {e}")
    
    def _release_processor_role(self):
        """Release the processor role (called on shutdown)"""
        if not self.is_processor:
            return
        
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE monitors 
                SET is_processor = FALSE, processor_claimed_at = NULL
                WHERE monitor_name = %s
            """, (self.monitor_name,))
            conn.commit()
            cursor.close()
            conn.close()
            self.logger.info("Released interval processor role")
        except Error as e:
            self.logger.warning(f"Error releasing processor role: {e}")
    
    def _get_interval_start(self) -> datetime:
        """Get the start of the current 5-minute interval"""
        now = datetime.now()
        # Round down to nearest 5-minute interval
        minutes = (now.minute // 5) * 5
        interval_start = now.replace(minute=minutes, second=0, microsecond=0)
        return interval_start
    
    async def scan_ble_devices_async(self) -> List[Dict]:
        """Scan for BLE devices using bleak (async)"""
        devices = []
        try:
            self.logger.info(f"Starting BLE scan for {self.scan_duration} seconds...")
            discovered = await BleakScanner.discover(timeout=self.scan_duration, return_adv=True)
            
            for device, adv_data in discovered.values():
                device_info = {
                    'mac_address': device.address,
                    'name': device.name or 'Unknown',
                    'rssi': adv_data.rssi
                }
                devices.append(device_info)
                self.logger.debug(f"Found: {device_info['mac_address']} - {device_info['name']} (RSSI: {device_info['rssi']})")
            
            self.logger.info(f"Scan complete. Found {len(devices)} devices")
            return devices
            
        except Exception as e:
            self.logger.error(f"Error during BLE scan: {e}")
            return []
    
    def scan_ble_devices_sync(self) -> List[Dict]:
        """Wrapper for synchronous execution of async scan"""
        if USE_BLEAK:
            import asyncio
            return asyncio.run(self.scan_ble_devices_async())
        else:
            # Simulation mode for testing without BLE hardware
            self.logger.warning("Running in simulation mode - generating test data")
            import random
            devices = []
            for i in range(random.randint(3, 8)):
                mac = f"AA:BB:CC:DD:EE:{i:02X}"
                devices.append({
                    'mac_address': mac,
                    'name': f'Device_{i}',
                    'rssi': random.randint(-90, -30)
                })
            return devices
    
    def _ensure_device_exists(self, mac_address: str, device_name: str, cursor) -> int:
        """Ensure device exists in ble_devices table and return device_id"""
        # Insert or update device
        query = """
            INSERT INTO ble_devices (mac_address, device_name)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                device_name = COALESCE(VALUES(device_name), device_name),
                last_seen = CURRENT_TIMESTAMP
        """
        cursor.execute(query, (mac_address, device_name))
        
        # Get device_id
        cursor.execute("SELECT device_id FROM ble_devices WHERE mac_address = %s", (mac_address,))
        result = cursor.fetchone()
        return result[0]
    
    def _store_sightings_staging(self, devices: List[Dict], interval_start: datetime):
        """Store device sightings in staging table"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            query = """
                INSERT INTO sighting_staging 
                (mac_address, device_name, monitor_id, rssi, interval_start, scan_timestamp)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """
            
            for device in devices:
                cursor.execute(query, (
                    device['mac_address'],
                    device['name'],
                    self.monitor_id,
                    device['rssi'],
                    interval_start
                ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            self.logger.info(f"Stored {len(devices)} sightings in staging for interval {interval_start}")
            
        except Error as e:
            self.logger.error(f"Error storing sightings to staging: {e}")
            raise
    
    def _process_interval(self, interval_start: datetime):
        """Process staging data to select best RSSI per device"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            # First, ensure all devices exist in ble_devices table
            cursor.execute("""
                SELECT DISTINCT mac_address, device_name 
                FROM sighting_staging 
                WHERE interval_start = %s AND processed = FALSE
            """, (interval_start,))
            
            for mac_address, device_name in cursor.fetchall():
                self._ensure_device_exists(mac_address, device_name, cursor)
            
            conn.commit()
            
            # Call stored procedure to process best RSSI
            cursor.callproc('process_interval_best_rssi', [interval_start])
            conn.commit()
            
            cursor.close()
            conn.close()
            
            self.logger.info(f"Processed interval {interval_start} - selected best RSSI per device")
            
        except Error as e:
            self.logger.error(f"Error processing interval: {e}")
            raise
    
    def run_scan_cycle(self):
        """Run one complete scan cycle"""
        interval_start = self._get_interval_start()
        self.logger.info(f"Starting scan cycle for interval: {interval_start}")
        
        # Scan for BLE devices
        devices = self.scan_ble_devices_sync()
        
        if devices:
            # Store in staging table (ALL monitors do this)
            self._store_sightings_staging(devices, interval_start)
            
            # Only the designated processor runs the stored procedure
            if self.is_processor:
                # Wait for other monitors to finish their scans and writes
                wait_time = int(self.config['monitor'].get('processor_wait_seconds', 60))
                self.logger.info(f"Processor: waiting {wait_time}s for other monitors to complete their scans...")
                time.sleep(wait_time)
                
                # Now process the interval to select best RSSI
                self._process_interval(interval_start)
                
                # Refresh our processor claim heartbeat
                self._refresh_processor_claim()
            else:
                self.logger.debug("Not processor - skipping interval processing")
        else:
            self.logger.warning("No devices found in this scan")
    
    def run_continuous(self):
        """Run continuous monitoring loop"""
        self.logger.info("Starting BLE Monitor in continuous mode")
        self.logger.info(f"Monitor: {self.monitor_name}")
        self.logger.info(f"Scan interval: {self.scan_interval} seconds")
        
        # Register monitor
        self.monitor_id = self._register_monitor()
        
        # Try to claim processor role if configured
        self.is_processor = self._try_claim_processor_role()
        
        if self.is_processor:
            self.logger.info("This monitor will process intervals (select best RSSI)")
        else:
            self.logger.info("This monitor will only scan and write to staging table")
        
        try:
            while True:
                try:
                    cycle_start = time.time()
                    
                    # Run scan cycle
                    self.run_scan_cycle()
                    
                    # Calculate sleep time to maintain interval
                    cycle_duration = time.time() - cycle_start
                    sleep_time = max(0, self.scan_interval - cycle_duration)
                    
                    if sleep_time > 0:
                        self.logger.info(f"Sleeping for {sleep_time:.1f} seconds until next scan")
                        time.sleep(sleep_time)
                    else:
                        self.logger.warning(f"Scan cycle took longer than interval ({cycle_duration:.1f}s)")
                    
                except KeyboardInterrupt:
                    self.logger.info("Received shutdown signal")
                    break
                except Exception as e:
                    self.logger.error(f"Error in scan cycle: {e}", exc_info=True)
                    self.logger.info("Waiting 60 seconds before retry...")
                    time.sleep(60)
        finally:
            # Always release processor role on shutdown
            self._release_processor_role()
            self.logger.info("BLE Monitor stopped")
    
    def run_single_scan(self):
        """Run a single scan (useful for testing)"""
        self.logger.info("Running single scan mode")
        self.monitor_id = self._register_monitor()
        
        # Try to claim processor role if configured
        self.is_processor = self._try_claim_processor_role()
        
        try:
            self.run_scan_cycle()
        finally:
            # Release processor role
            self._release_processor_role()
            self.logger.info("Single scan complete")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='BLE Monitor Scanner')
    parser.add_argument('-c', '--config', default='config.ini', help='Configuration file path')
    parser.add_argument('--single', action='store_true', help='Run single scan and exit')
    args = parser.parse_args()
    
    try:
        monitor = BLEMonitor(config_file=args.config)
        
        if args.single:
            monitor.run_single_scan()
        else:
            monitor.run_continuous()
            
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
