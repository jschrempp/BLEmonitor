#!/usr/bin/env python3
"""
Simple dashboard to display current BLE monitoring status
Run this to see real-time statistics
"""

import sys
import time
import configparser
import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta


class BLEDashboard:
    """Simple text-based dashboard"""
    
    def __init__(self, config_file='config.ini'):
        """Initialize dashboard"""
        self.config = self._load_config(config_file)
        self.db_config = {
            'host': self.config['database']['host'],
            'port': int(self.config['database']['port']),
            'user': self.config['database']['user'],
            'password': self.config['database']['password'],
            'database': self.config['database']['database']
        }
    
    def _load_config(self, config_file):
        """Load configuration"""
        config = configparser.ConfigParser()
        config.read(config_file)
        return config
    
    def _get_db_connection(self):
        """Get database connection"""
        return mysql.connector.connect(**self.db_config)
    
    def get_monitor_stats(self):
        """Get monitor statistics"""
        conn = self._get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT 
                m.monitor_name,
                m.location,
                m.is_active,
                m.last_seen,
                COUNT(DISTINCT ds.device_id) as devices_24h,
                COUNT(ds.sighting_id) as sightings_24h
            FROM monitors m
            LEFT JOIN device_sightings ds ON m.monitor_id = ds.monitor_id 
                AND ds.sighting_timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            GROUP BY m.monitor_id
            ORDER BY m.monitor_name
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return results
    
    def get_recent_devices(self, limit=10):
        """Get recently seen devices"""
        conn = self._get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT 
                bd.mac_address,
                bd.device_name,
                m.monitor_name,
                ds.rssi,
                ds.sighting_timestamp
            FROM device_sightings ds
            JOIN ble_devices bd ON ds.device_id = bd.device_id
            JOIN monitors m ON ds.monitor_id = m.monitor_id
            ORDER BY ds.sighting_timestamp DESC
            LIMIT %s
        """
        
        cursor.execute(query, (limit,))
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return results
    
    def get_top_devices(self, hours=24, limit=10):
        """Get most frequently seen devices"""
        conn = self._get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT 
                bd.mac_address,
                bd.device_name,
                COUNT(*) as sightings,
                AVG(ds.rssi) as avg_rssi,
                MAX(ds.sighting_timestamp) as last_seen
            FROM device_sightings ds
            JOIN ble_devices bd ON ds.device_id = bd.device_id
            WHERE ds.sighting_timestamp >= DATE_SUB(NOW(), INTERVAL %s HOUR)
            GROUP BY bd.device_id
            ORDER BY sightings DESC
            LIMIT %s
        """
        
        cursor.execute(query, (hours, limit))
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return results
    
    def clear_screen(self):
        """Clear terminal screen"""
        import os
        os.system('clear' if os.name == 'posix' else 'cls')
    
    def display_dashboard(self):
        """Display the dashboard"""
        self.clear_screen()
        
        print("=" * 80)
        print(" " * 25 + "BLE MONITOR DASHBOARD")
        print("=" * 80)
        print(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Monitor Status
        print("MONITOR STATUS:")
        print("-" * 80)
        monitors = self.get_monitor_stats()
        
        if not monitors:
            print("  No monitors registered")
        else:
            for mon in monitors:
                status = "🟢 ACTIVE" if mon['is_active'] else "🔴 INACTIVE"
                time_diff = datetime.now() - mon['last_seen']
                minutes_ago = int(time_diff.total_seconds() / 60)
                
                print(f"  {status} {mon['monitor_name']}")
                print(f"    Location: {mon['location'] or 'N/A'}")
                print(f"    Last seen: {minutes_ago} minutes ago")
                print(f"    Devices (24h): {mon['devices_24h']} | Sightings: {mon['sightings_24h']}")
                print()
        
        # Top Devices
        print()
        print("TOP DEVICES (Last 24 Hours):")
        print("-" * 80)
        top_devices = self.get_top_devices(hours=24, limit=5)
        
        if not top_devices:
            print("  No devices seen")
        else:
            for i, dev in enumerate(top_devices, 1):
                name = dev['device_name'] or 'Unknown'
                print(f"  {i}. {name} ({dev['mac_address']})")
                print(f"     Sightings: {dev['sightings']} | Avg RSSI: {dev['avg_rssi']:.1f} dBm")
        
        # Recent Activity
        print()
        print("RECENT ACTIVITY:")
        print("-" * 80)
        recent = self.get_recent_devices(limit=5)
        
        if not recent:
            print("  No recent activity")
        else:
            for dev in recent:
                name = dev['device_name'] or 'Unknown'
                time_str = dev['sighting_timestamp'].strftime('%H:%M:%S')
                print(f"  [{time_str}] {name} - {dev['mac_address']}")
                print(f"    Monitor: {dev['monitor_name']} | RSSI: {dev['rssi']} dBm")
        
        print()
        print("=" * 80)
        print("Press Ctrl+C to exit | Updates every 30 seconds")
    
    def run(self, refresh_interval=30):
        """Run dashboard with auto-refresh"""
        try:
            while True:
                try:
                    self.display_dashboard()
                    time.sleep(refresh_interval)
                except Error as e:
                    print(f"\nDatabase error: {e}")
                    print("Retrying in 10 seconds...")
                    time.sleep(10)
        except KeyboardInterrupt:
            print("\n\nDashboard stopped.")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='BLE Monitor Dashboard')
    parser.add_argument('-c', '--config', default='config.ini',
                       help='Configuration file path')
    parser.add_argument('-r', '--refresh', type=int, default=30,
                       help='Refresh interval in seconds (default: 30)')
    parser.add_argument('--once', action='store_true',
                       help='Display once and exit (no auto-refresh)')
    
    args = parser.parse_args()
    
    try:
        dashboard = BLEDashboard(config_file=args.config)
        
        if args.once:
            dashboard.display_dashboard()
        else:
            dashboard.run(refresh_interval=args.refresh)
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
