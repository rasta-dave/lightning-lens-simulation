#!/bin/bash

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then 
    echo "Script must be run with sudo. Elevating privileges..."
    exec sudo "$0" "$@"
    exit $?
fi

set -e

# Print welcome message with password information
echo "================================"
echo "    Lightning Wallet Unlock 🔓"
echo "================================"
echo ""
echo "Default wallet password for all nodes: 'password'"
echo ""

# Install expect if not already installed
if ! command -v expect &> /dev/null; then
    echo "Installing expect..."
    DEBIAN_FRONTEND=noninteractive apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y expect
fi

# Function to unlock a wallet
unlock_wallet() {
    local node=$1
    echo "Unlocking wallet for $node 🔑"
    
    # Check if node is running
    if ! docker ps | grep -q $node; then
        echo "$node is not running! Attempting to start..."
        docker start $node
        sleep 5
    fi
    
    # Create an expect script to handle the unlock
    cat > /tmp/unlock_wallet.exp << EOF
#!/usr/bin/expect -f
set timeout 60
spawn docker exec -it $node lncli --network=regtest unlock
expect "Input wallet password: "
send "password\r"
expect eof
EOF
    
    # Make the script executable
    chmod +x /tmp/unlock_wallet.exp
    
    # Run the expect script
    /tmp/unlock_wallet.exp
    
    # Clean up
    rm /tmp/unlock_wallet.exp
    
    echo "[========================================] 100%"
    echo "Wallet unlocked for $node ✅"
    echo "--------------------------------"
    
    # Wait for wallet to fully initialize
    sleep 5
}

# Function to verify a node is ready
verify_node_ready() {
    local node=$1
    echo "Verifying $node is ready..."
    
    local attempt=1
    local max_attempts=30
    
    while [ $attempt -le $max_attempts ]; do
        if docker exec $node lncli --network=regtest getinfo &>/dev/null; then
            echo "$node is ready! ✅"
            return 0
        fi
        
        echo "Waiting for $node to be ready... (Attempt $attempt/$max_attempts)"
        sleep 5
        attempt=$((attempt + 1))
    done
    
    echo "$node failed to initialize properly ❌"
    echo "Checking logs for $node:"
    docker logs $node | tail -n 30
    return 1
}

# Unlock all nodes
NODES=("lnd-alice" "lnd-bob" "lnd-carol" "lnd-dave" "lnd-eve")
echo "Unlocking LND nodes..."
for node in "${NODES[@]}"; do
    unlock_wallet "$node"
    verify_node_ready "$node"
done

echo ""
echo "All wallets unlocked! 🚀✅"
echo "================================" 