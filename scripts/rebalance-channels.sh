#!/bin/bash

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then 
    echo "Script must be run with sudo. Elevating privileges..."
    exec sudo "$0" "$@"
    exit $?
fi

echo "================================"
echo "  Lightning Network Rebalancing 🔄"
echo "================================"
echo ""
echo "This script will rebalance channels to create a realistic distribution."
echo ""

# Generate some blocks to ensure transactions confirm
echo "Generating blocks to ensure transaction confirmation..."
docker exec bitcoind bitcoin-cli -regtest -rpcuser=bitcoinuser -rpcpassword=bitcoinpassword generatetoaddress 6 $(docker exec bitcoind bitcoin-cli -regtest -rpcuser=bitcoinuser -rpcpassword=bitcoinpassword getnewaddress)

# Function to show progress
show_progress() {
    local duration=$1
    local message=$2
    local start_time=$(date +%s)
    local end_time=$((start_time + duration))
    local current_time
    
    echo -n "$message ["
    while true; do
        current_time=$(date +%s)
        if [ $current_time -ge $end_time ]; then
            break
        fi
        
        local elapsed=$((current_time - start_time))
        local progress=$((elapsed * 20 / duration))
        
        echo -n "="
        sleep 0.5
    done
    echo "] Done!"
}

# Rebalance channels by making payments in both directions
echo "Starting channel rebalancing..."

# Define all channel pairs to balance with target percentages
# Format: "node1:node2:target_percentage"
# Where target_percentage is how much of the capacity node1 should have (0-100)
pairs=(
    "lnd-alice:lnd-bob:60"      # Alice has 60%, Bob has 40%
    "lnd-bob:lnd-carol:45"      # Bob has 45%, Carol has 55%
    "lnd-carol:lnd-dave:70"     # Carol has 70%, Dave has 30%
    "lnd-dave:lnd-eve:40"       # Dave has 40%, Eve has 60%
    "lnd-eve:lnd-alice:55"      # Eve has 55%, Alice has 45%
    "lnd-alice:lnd-carol:65"    # Alice has 65%, Carol has 35%
    "lnd-bob:lnd-eve:50"        # Bob has 50%, Eve has 50%
)

# Process each pair
for pair in "${pairs[@]}"; do
    IFS=':' read -r node1 node2 target_pct <<< "$pair"
    
    # Calculate the inverse percentage for the other node
    target_pct_inv=$((100 - target_pct))
    
    echo "Rebalancing channel between $node1 and $node2 (target: $target_pct% / ${target_pct_inv}%)..."
    
    # Get channel info
    echo "Checking current balance..."
    channel_info=$(docker exec $node1 lncli --network=regtest listchannels | jq -c '.channels[]')
    remote_pubkey=$(docker exec $node2 lncli --network=regtest getinfo | jq -r '.identity_pubkey')
    
    # Find the specific channel
    channel=$(echo "$channel_info" | grep -F "$remote_pubkey")
    
    if [ -z "$channel" ]; then
        echo "No channel found between $node1 and $node2, skipping"
        continue
    fi
    
    # Extract channel details
    capacity=$(echo "$channel" | jq -r '.capacity')
    local_balance=$(echo "$channel" | jq -r '.local_balance')
    remote_balance=$(echo "$channel" | jq -r '.remote_balance')
    
    # Calculate current percentages
    local_pct=$(echo "scale=1; $local_balance * 100 / $capacity" | bc)
    remote_pct=$(echo "scale=1; $remote_balance * 100 / $capacity" | bc)
    
    echo "  Current balance: $node1 has $local_balance sats ($local_pct%), $node2 has $remote_balance sats ($remote_pct%)"
    
    # Calculate target balance
    target_balance=$(echo "scale=0; $capacity * $target_pct / 100" | bc)
    
    # Determine direction and amount to transfer
    if (( $(echo "$local_balance < $target_balance" | bc -l) )); then
        # Node1 needs more funds, so node2 sends to node1
        amount=$(echo "scale=0; $target_balance - $local_balance" | bc)
        sender=$node2
        receiver=$node1
        echo "  $node1 needs more funds. $node2 will send $amount sats to $node1"
    else
        # Node1 has excess funds, so node1 sends to node2
        amount=$(echo "scale=0; $local_balance - $target_balance" | bc)
        sender=$node1
        receiver=$node2
        echo "  $node1 has excess funds. $node1 will send $amount sats to $node2"
    fi
    
    # Cap the amount to avoid failures
    if [ "$amount" -gt 300000 ]; then
        amount=300000
        echo "  Capping amount to $amount sats to avoid failures"
    fi
    
    # Only proceed if there's a significant amount to transfer
    if [ "$amount" -lt 10000 ]; then
        echo "  Amount too small, skipping this rebalance"
        continue
    fi
    
    # Create invoice on receiver
    echo "  Creating invoice on $receiver..."
    invoice=$(docker exec $receiver lncli --network=regtest addinvoice --amt=$amount --memo="Rebalance" | jq -r '.payment_request')
    
    # Pay invoice from sender
    echo "  Paying from $sender..."
    payment_result=$(docker exec $sender lncli --network=regtest payinvoice --force "$invoice" 2>&1) || echo "  Payment failed"
    
    if echo "$payment_result" | grep -q "SUCCEEDED"; then
        echo "  Payment succeeded!"
    else
        echo "  Payment failed or partial. This is normal if channels are imbalanced."
    fi
    
    show_progress 3 "Processing payment"
    
    # Check new balance
    echo "  Checking new balance..."
    new_channel_info=$(docker exec $node1 lncli --network=regtest listchannels | jq -c '.channels[]')
    new_channel=$(echo "$new_channel_info" | grep -F "$remote_pubkey")
    
    if [ -n "$new_channel" ]; then
        new_local_balance=$(echo "$new_channel" | jq -r '.local_balance')
        new_remote_balance=$(echo "$new_channel" | jq -r '.remote_balance')
        new_local_pct=$(echo "scale=1; $new_local_balance * 100 / $capacity" | bc)
        new_remote_pct=$(echo "scale=1; $new_remote_balance * 100 / $capacity" | bc)
        
        echo "  New balance: $node1 has $new_local_balance sats ($new_local_pct%), $node2 has $new_remote_balance sats ($new_remote_pct%)"
    else
        echo "  Could not retrieve updated channel information"
    fi
    
    echo ""
done

# Generate blocks to help with settlement
echo "Generating blocks to confirm transactions..."
docker exec bitcoind bitcoin-cli -regtest -rpcuser=bitcoinuser -rpcpassword=bitcoinpassword generatetoaddress 6 $(docker exec bitcoind bitcoin-cli -regtest -rpcuser=bitcoinuser -rpcpassword=bitcoinpassword getnewaddress)

echo ""
echo "Rebalancing complete! Channels now have a realistic distribution of liquidity."
echo "Run the simulation script to test payments with the new channel balances."
echo "================================" 