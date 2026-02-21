#!/usr/bin/env python3
"""
Database initialization and test script
Use this to verify database connection and setup
"""

import sys
import configparser
import mysql.connector
from mysql.connector import Error


def load_config(config_file='config.ini'):
    """Load configuration"""
    config = configparser.ConfigParser()
    config.read(config_file)
    return config


def test_connection(config):
    """Test database connection"""
    db_config = {
        'host': config['database']['host'],
        'port': int(config['database']['port']),
        'user': config['database']['user'],
        'password': config['database']['password'],
        'database': config['database']['database']
    }
    
    print("Testing database connection...")
    print(f"  Host: {db_config['host']}:{db_config['port']}")
    print(f"  Database: {db_config['database']}")
    print(f"  User: {db_config['user']}")
    
    try:
        conn = mysql.connector.connect(**db_config)
        print("✓ Connection successful!")
        
        cursor = conn.cursor()
        
        # Check tables
        print("\nChecking tables...")
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        
        required_tables = ['monitors', 'ble_devices', 'device_sightings', 'sighting_staging']
        found_tables = [table[0] for table in tables]
        
        for table in required_tables:
            if table in found_tables:
                print(f"  ✓ {table}")
            else:
                print(f"  ✗ {table} - MISSING!")
        
        # Get row counts
        print("\nTable row counts:")
        for table in required_tables:
            if table in found_tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  {table}: {count} rows")
        
        cursor.close()
        conn.close()
        
        print("\n✓ Database check complete!")
        return True
        
    except Error as e:
        print(f"\n✗ Connection failed: {e}")
        return False


def create_test_monitor(config):
    """Create a test monitor entry"""
    db_config = {
        'host': config['database']['host'],
        'port': int(config['database']['port']),
        'user': config['database']['user'],
        'password': config['database']['password'],
        'database': config['database']['database']
    }
    
    monitor_name = config['monitor']['name']
    location = config['monitor'].get('location', '')
    description = config['monitor'].get('description', '')
    
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        query = """
            INSERT INTO monitors (monitor_name, location, description, is_active)
            VALUES (%s, %s, %s, TRUE)
            ON DUPLICATE KEY UPDATE
                location = VALUES(location),
                description = VALUES(description),
                is_active = TRUE
        """
        
        cursor.execute(query, (monitor_name, location, description))
        conn.commit()
        
        cursor.execute("SELECT monitor_id FROM monitors WHERE monitor_name = %s", (monitor_name,))
        monitor_id = cursor.fetchone()[0]
        
        print(f"\n✓ Test monitor created/updated:")
        print(f"  Name: {monitor_name}")
        print(f"  ID: {monitor_id}")
        print(f"  Location: {location}")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Error as e:
        print(f"\n✗ Failed to create test monitor: {e}")
        return False


def main():
    """Main function"""
    print("="*60)
    print("BLE Monitor Database Test Utility")
    print("="*60)
    print()
    
    try:
        config = load_config()
    except Exception as e:
        print(f"Error loading config.ini: {e}")
        print("Make sure config.ini exists and is properly configured.")
        sys.exit(1)
    
    # Test connection
    if not test_connection(config):
        print("\nPlease check your database configuration and ensure:")
        print("1. MySQL server is running")
        print("2. Database exists (run schema.sql)")
        print("3. User has proper permissions")
        print("4. Connection details in config.ini are correct")
        sys.exit(1)
    
    # Create test monitor
    print()
    response = input("Create/update test monitor entry? (y/n): ")
    if response.lower() == 'y':
        create_test_monitor(config)
    
    print("\nDatabase test complete!")


if __name__ == '__main__':
    main()
