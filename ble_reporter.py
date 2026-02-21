#!/usr/bin/env python3
"""
BLE Monitor Hourly Report Generator
Generates reports showing the number of devices seen each hour by each monitor.
"""

import sys
import argparse
import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta
from typing import Optional
import configparser
from tabulate import tabulate


class BLEReporter:
    """Generate reports from BLE monitoring data"""
    
    def __init__(self, config_file: str = 'config.ini'):
        """Initialize reporter with database configuration"""
        self.config = self._load_config(config_file)
        self.db_config = {
            'host': self.config['database']['host'],
            'port': int(self.config['database']['port']),
            'user': self.config['database']['user'],
            'password': self.config['database']['password'],
            'database': self.config['database']['database']
        }
    
    def _load_config(self, config_file: str) -> configparser.ConfigParser:
        """Load configuration from INI file"""
        config = configparser.ConfigParser()
        config.read(config_file)
        
        if 'database' not in config:
            raise ValueError("Missing required configuration section: database")
        
        return config
    
    def _get_db_connection(self):
        """Create and return a database connection"""
        try:
            connection = mysql.connector.connect(**self.db_config)
            return connection
        except Error as e:
            print(f"Database connection error: {e}")
            raise
    
    def generate_hourly_report(self, start_date: Optional[str] = None, 
                               end_date: Optional[str] = None,
                               monitor_name: Optional[str] = None,
                               output_format: str = 'table'):
        """
        Generate hourly device count report
        
        Args:
            start_date: Start date (YYYY-MM-DD format), defaults to 24 hours ago
            end_date: End date (YYYY-MM-DD format), defaults to now
            monitor_name: Filter by specific monitor name
            output_format: 'table', 'csv', or 'json'
        """
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Build query
            query = """
                SELECT 
                    monitor_name,
                    location,
                    hour_start,
                    unique_devices,
                    total_sightings,
                    ROUND(avg_rssi, 1) as avg_rssi,
                    min_rssi,
                    max_rssi
                FROM hourly_device_counts
                WHERE 1=1
            """
            params = []
            
            # Apply date filters
            if start_date:
                query += " AND hour_start >= %s"
                params.append(start_date)
            else:
                # Default to last 24 hours
                query += " AND hour_start >= DATE_SUB(NOW(), INTERVAL 24 HOUR)"
            
            if end_date:
                query += " AND hour_start <= %s"
                params.append(end_date)
            
            # Apply monitor filter
            if monitor_name:
                query += " AND monitor_name = %s"
                params.append(monitor_name)
            
            query += " ORDER BY hour_start DESC, monitor_name"
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            if not results:
                print("No data found for the specified criteria")
                return
            
            # Output based on format
            if output_format == 'table':
                self._print_table(results)
            elif output_format == 'csv':
                self._print_csv(results)
            elif output_format == 'json':
                self._print_json(results)
            else:
                print(f"Unknown output format: {output_format}")
            
        except Error as e:
            print(f"Error generating report: {e}")
            raise
    
    def _print_table(self, results):
        """Print results as formatted table"""
        headers = ['Monitor', 'Location', 'Hour', 'Unique Devices', 
                   'Total Sightings', 'Avg RSSI', 'Min RSSI', 'Max RSSI']
        
        rows = []
        for row in results:
            rows.append([
                row['monitor_name'],
                row['location'] or '',
                row['hour_start'],
                row['unique_devices'],
                row['total_sightings'],
                row['avg_rssi'],
                row['min_rssi'],
                row['max_rssi']
            ])
        
        print("\n" + "="*100)
        print("BLE Monitor Hourly Device Report")
        print("="*100)
        print(tabulate(rows, headers=headers, tablefmt='grid'))
        print(f"\nTotal records: {len(results)}")
    
    def _print_csv(self, results):
        """Print results as CSV"""
        import csv
        import io
        
        output = io.StringIO()
        if results:
            writer = csv.DictWriter(output, fieldnames=results[0].keys())
            writer.writeheader()
            for row in results:
                # Convert datetime to string for CSV output
                row_copy = row.copy()
                if 'hour_start' in row_copy and row_copy['hour_start']:
                    row_copy['hour_start'] = str(row_copy['hour_start'])
                writer.writerow(row_copy)
        
        print(output.getvalue())
    
    def _print_json(self, results):
        """Print results as JSON"""
        import json
        
        # Convert datetime objects to strings for JSON serialization
        json_results = []
        for row in results:
            row_copy = row.copy()
            if 'hour_start' in row_copy and row_copy['hour_start']:
                row_copy['hour_start'] = str(row_copy['hour_start'])
            json_results.append(row_copy)
        
        print(json.dumps(json_results, indent=2))
    
    def generate_monitor_summary(self):
        """Generate summary of all monitors"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            query = """
                SELECT 
                    m.monitor_name,
                    m.location,
                    m.is_active,
                    m.last_seen,
                    COUNT(DISTINCT ds.device_id) as total_unique_devices,
                    COUNT(ds.sighting_id) as total_sightings,
                    MIN(ds.interval_start) as first_sighting,
                    MAX(ds.interval_start) as last_sighting
                FROM monitors m
                LEFT JOIN device_sightings ds ON m.monitor_id = ds.monitor_id
                GROUP BY m.monitor_id, m.monitor_name, m.location, m.is_active, m.last_seen
                ORDER BY m.monitor_name
            """
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            if not results:
                print("No monitors found")
                return
            
            headers = ['Monitor', 'Location', 'Active', 'Last Seen', 
                      'Total Devices', 'Total Sightings', 'First Sighting', 'Last Sighting']
            
            rows = []
            for row in results:
                rows.append([
                    row['monitor_name'],
                    row['location'] or '',
                    'Yes' if row['is_active'] else 'No',
                    row['last_seen'],
                    row['total_unique_devices'] or 0,
                    row['total_sightings'] or 0,
                    row['first_sighting'] or 'N/A',
                    row['last_sighting'] or 'N/A'
                ])
            
            print("\n" + "="*120)
            print("BLE Monitor Summary")
            print("="*120)
            print(tabulate(rows, headers=headers, tablefmt='grid'))
            print(f"\nTotal monitors: {len(results)}")
            
        except Error as e:
            print(f"Error generating monitor summary: {e}")
            raise
    
    def generate_device_summary(self, hours: int = 24):
        """Generate summary of devices seen in the last N hours"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            query = """
                SELECT 
                    bd.mac_address,
                    bd.device_name,
                    COUNT(DISTINCT ds.monitor_id) as seen_by_monitors,
                    COUNT(*) as total_sightings,
                    MAX(ds.rssi) as best_rssi,
                    AVG(ds.rssi) as avg_rssi,
                    MAX(ds.sighting_timestamp) as last_seen
                FROM ble_devices bd
                JOIN device_sightings ds ON bd.device_id = ds.device_id
                WHERE ds.sighting_timestamp >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                GROUP BY bd.device_id, bd.mac_address, bd.device_name
                ORDER BY total_sightings DESC
            """
            
            cursor.execute(query, (hours,))
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            if not results:
                print(f"No devices found in the last {hours} hours")
                return
            
            headers = ['MAC Address', 'Device Name', 'Monitors', 'Sightings', 
                      'Best RSSI', 'Avg RSSI', 'Last Seen']
            
            rows = []
            for row in results:
                rows.append([
                    row['mac_address'],
                    row['device_name'] or 'Unknown',
                    row['seen_by_monitors'],
                    row['total_sightings'],
                    row['best_rssi'],
                    f"{row['avg_rssi']:.1f}",
                    row['last_seen']
                ])
            
            print("\n" + "="*100)
            print(f"BLE Devices Summary (Last {hours} hours)")
            print("="*100)
            print(tabulate(rows, headers=headers, tablefmt='grid'))
            print(f"\nTotal devices: {len(results)}")
            
        except Error as e:
            print(f"Error generating device summary: {e}")
            raise


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='BLE Monitor Report Generator')
    parser.add_argument('-c', '--config', default='config.ini', 
                       help='Configuration file path')
    parser.add_argument('-r', '--report', choices=['hourly', 'monitors', 'devices'],
                       default='hourly', help='Report type to generate')
    parser.add_argument('-s', '--start-date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('-e', '--end-date', help='End date (YYYY-MM-DD)')
    parser.add_argument('-m', '--monitor', help='Filter by monitor name')
    parser.add_argument('-f', '--format', choices=['table', 'csv', 'json'],
                       default='table', help='Output format')
    parser.add_argument('--hours', type=int, default=24,
                       help='Hours to look back (for device summary)')
    
    args = parser.parse_args()
    
    try:
        reporter = BLEReporter(config_file=args.config)
        
        if args.report == 'hourly':
            reporter.generate_hourly_report(
                start_date=args.start_date,
                end_date=args.end_date,
                monitor_name=args.monitor,
                output_format=args.format
            )
        elif args.report == 'monitors':
            reporter.generate_monitor_summary()
        elif args.report == 'devices':
            reporter.generate_device_summary(hours=args.hours)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
