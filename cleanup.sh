#!/bin/bash

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then 
    echo "Script must be run with sudo. Elevating privileges..."
    exec sudo "$0" "$@"
    exit $?
fi

echo "================================"
echo "    Lightning Network Cleanup 🧹"
echo "================================"
echo ""
echo "This script will:"
echo " • Stop all containers"
echo " • Remove all containers"
echo " • Delete all data directories"
echo " • Prepare for a fresh start"
echo ""
echo "⚠️  WARNING: All data will be lost! ⚠️"
echo ""
read -p "Are you sure you want to continue? (y/n): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Operation cancelled."
    exit 1
fi

echo "Stopping and removing containers..."
docker-compose down

echo "Removing data directories with proper permissions..."
# Use sudo to ensure we have permissions to delete everything
sudo rm -rf lnd-*-data
sudo rm -rf bitcoin-data

echo "Cleanup complete! ✅"
echo ""
echo "To start fresh, run:"
echo "  docker-compose up -d"
echo "  sudo ./setup-nodes.sh"
echo ""
echo "================================" 