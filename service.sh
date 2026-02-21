#!/bin/bash
# Service management script for BLE Monitor

SERVICE_NAME="ble-monitor.service"
SERVICE_FILE="ble-monitor.service"
INSTALL_PATH="/etc/systemd/system/$SERVICE_NAME"

show_usage() {
    echo "BLE Monitor Service Manager"
    echo ""
    echo "Usage: $0 {install|uninstall|start|stop|restart|status|logs|enable|disable}"
    echo ""
    echo "Commands:"
    echo "  install   - Install the service (requires sudo)"
    echo "  uninstall - Remove the service (requires sudo)"
    echo "  start     - Start the service"
    echo "  stop      - Stop the service"
    echo "  restart   - Restart the service"
    echo "  status    - Show service status"
    echo "  logs      - Show service logs (live)"
    echo "  enable    - Enable service to start on boot"
    echo "  disable   - Disable service from starting on boot"
    echo ""
}

install_service() {
    echo "Installing BLE Monitor service..."
    
    if [ ! -f "$SERVICE_FILE" ]; then
        echo "Error: $SERVICE_FILE not found in current directory"
        exit 1
    fi
    
    # Update paths in service file based on current directory
    CURRENT_DIR=$(pwd)
    TEMP_SERVICE=$(mktemp)
    
    sed "s|/home/pi/ble_monitor|$CURRENT_DIR|g" "$SERVICE_FILE" > "$TEMP_SERVICE"
    
    # Update user if not 'pi'
    CURRENT_USER=$(whoami)
    sed -i "s|User=pi|User=$CURRENT_USER|g" "$TEMP_SERVICE"
    sed -i "s|Group=pi|Group=$CURRENT_USER|g" "$TEMP_SERVICE"
    
    sudo cp "$TEMP_SERVICE" "$INSTALL_PATH"
    rm "$TEMP_SERVICE"
    
    sudo systemctl daemon-reload
    
    echo "Service installed successfully!"
    echo "Use '$0 enable' to enable auto-start on boot"
    echo "Use '$0 start' to start the service now"
}

uninstall_service() {
    echo "Uninstalling BLE Monitor service..."
    
    sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    sudo systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    sudo rm -f "$INSTALL_PATH"
    sudo systemctl daemon-reload
    
    echo "Service uninstalled successfully!"
}

case "$1" in
    install)
        install_service
        ;;
    uninstall)
        uninstall_service
        ;;
    start)
        sudo systemctl start "$SERVICE_NAME"
        echo "Service started"
        ;;
    stop)
        sudo systemctl stop "$SERVICE_NAME"
        echo "Service stopped"
        ;;
    restart)
        sudo systemctl restart "$SERVICE_NAME"
        echo "Service restarted"
        ;;
    status)
        sudo systemctl status "$SERVICE_NAME"
        ;;
    logs)
        echo "Showing live logs (Ctrl+C to exit)..."
        sudo journalctl -u "$SERVICE_NAME" -f
        ;;
    enable)
        sudo systemctl enable "$SERVICE_NAME"
        echo "Service enabled for auto-start on boot"
        ;;
    disable)
        sudo systemctl disable "$SERVICE_NAME"
        echo "Service disabled from auto-start"
        ;;
    *)
        show_usage
        exit 1
        ;;
esac

exit 0
