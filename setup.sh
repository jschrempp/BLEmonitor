#!/bin/bash
# Setup script for BLE Monitor on Raspberry Pi

set -e  # Exit on error

echo "====================================="
echo "BLE Monitor Setup Script"
echo "====================================="
echo ""

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "Warning: This script is designed for Linux/Raspberry Pi"
    echo "Continue anyway? (y/n)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update system
echo "1. Updating system packages..."
sudo apt update
sudo apt upgrade -y

# Install system dependencies
echo "2. Installing system dependencies..."
sudo apt install -y bluetooth bluez libbluetooth-dev python3-pip python3-venv default-mysql-client

# Create virtual environment
echo "3. Creating Python virtual environment..."
python3 -m venv venv

# Activate and install Python packages
echo "4. Installing Python dependencies..."
source venv/bin/activate
pip3 install --upgrade pip
pip3 install -r requirements.txt

# Create config file if it doesn't exist
if [ ! -f config.ini ]; then
    echo "5. Creating configuration file..."
    cp config.ini.example config.ini
    echo "   Please edit config.ini with your settings!"
else
    echo "5. Configuration file already exists, skipping..."
fi

# Set up Bluetooth permissions
echo "6. Setting up Bluetooth permissions..."
sudo usermod -a -G bluetooth $USER

# Grant Python BLE scanning capabilities
PYTHON_PATH=$(readlink -f venv/bin/python3)
sudo setcap cap_net_raw,cap_net_admin+eip $PYTHON_PATH

echo ""
echo "====================================="
echo "Setup Complete!"
echo "====================================="
echo ""
echo "Next steps:"
echo "1. Edit config.ini with your database and monitor settings"
echo "2. Create the database on your MySQL server using schema.sql:"
echo "   mysql -u root -p < schema.sql"
echo "3. Test the installation:"
echo "   source venv/bin/activate"
echo "   python3 ble_monitor.py --single"
echo "4. Set up as a system service (see README.md)"
echo ""
echo "You may need to log out and back in for group permissions to take effect."
echo ""
