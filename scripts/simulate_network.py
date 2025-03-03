#!/usr/bin/env python3
"""
Lightning Network Transaction Simulator

This script simulates realistic payment patterns between Lightning Network nodes
and logs transaction data to a CSV file for analysis by AI liquidity optimization tools.
"""

import subprocess
import json
import random
import time
import csv
import os
import signal
import sys
from datetime import datetime
import requests

# Configuration
NODES = ["lnd-alice", "lnd-bob", "lnd-carol", "lnd-dave", "lnd-eve"]
current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
CSV_OUTPUT = f"lightning_simulation_{current_time}.csv"
SIMULATION_DURATION = 3600  # in seconds (default: 1 hour)
MIN_PAYMENT_AMOUNT = 500    # Reduced minimum amount
MAX_PAYMENT_AMOUNT = 3000   # Reduced maximum amount
PAYMENT_INTERVAL_MIN = 10   # Increased to give more time between payments
PAYMENT_INTERVAL_MAX = 30   # maximum seconds between payments
REBALANCE_FREQUENCY = 0     # Disable automatic rebalancing for ML model learning
FAILURE_THRESHOLD = 1          # Trigger rebalancing after just 1 failure
AUTO_RECOVERY_DELAY = 30       # Seconds to wait after failures before rebalancing
RECOVERY_REBALANCE_AMOUNT = 0.2  # Percentage of capacity to rebalance during recovery

# Transaction patterns - weights determine likelihood
TRANSACTION_PATTERNS = {
    "direct_payment": 70,       # Simple A->B payment
    "multi_hop": 25,            # Payment requiring multiple hops
    "circular_payment": 5,      # Payment that goes in a circle (testing rebalancing)
}

# Define some realistic payment descriptions
PAYMENT_DESCRIPTIONS = [
    "Coffee purchase",
    "Lunch payment",
    "Digital content",
    "Subscription renewal",
    "Donation",
    "Service fee",
    "Microtask payment",
    "Content creator tip",
    "App purchase",
    "Game credits",
    "Podcast support",
    "Newsletter subscription",
    "Digital art purchase",
    "Online course access",
    "E-book purchase"
]

# CSV headers
CSV_HEADERS = [
    "timestamp",
    "type",              # New field: "payment" or "rebalance"
    "sender",
    "receiver", 
    "amount",
    "fee",
    "route_length",
    "success",
    "payment_hash",
    "description",
    "duration_ms",
    "channel_before",    # New field: channel state before operation
    "channel_after"      # New field: channel state after operation
]

# Global variables for statistics
stats = {
    "total_payments": 0,
    "successful_payments": 0,
    "failed_payments": 0,
    "total_amount": 0,
    "total_fees": 0,
    "start_time": None,
    "node_payments": {node: {"sent": 0, "received": 0} for node in NODES},
    "rebalance_operations": 0,
    "rebalance_successes": 0,
    "consecutive_failures": 0,
    "auto_rebalance_events": 0,
    "auto_rebalance_successes": 0
}

def run_command(cmd):
    """Run a shell command and return the output"""
    try:
        # Add timeout to prevent hanging
        result = subprocess.run(cmd, shell=True, check=True, 
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=30)  # 30 second timeout
        return result.stdout.decode('utf-8')
    except subprocess.TimeoutExpired:
        print(f"Command timed out: {cmd}")
        return None
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e}")
        print(f"Error output: {e.stderr.decode('utf-8')}")
        return None

def get_node_info(node):
    """Get basic information about a node"""
    cmd = f"docker exec {node} lncli --network=regtest getinfo"
    output = run_command(cmd)
    if output:
        return json.loads(output)
    return None

def get_node_channels(node):
    """Get channels for a node"""
    cmd = f"docker exec {node} lncli --network=regtest listchannels"
    output = run_command(cmd)
    if output:
        return json.loads(output)
    return None

def create_invoice(node, amount, memo):
    """Create an invoice on a node"""
    cmd = f"docker exec {node} lncli --network=regtest addinvoice --amt={amount} --memo=\"{memo}\""
    output = run_command(cmd)
    if output:
        return json.loads(output)
    return None

def pay_invoice(node, invoice):
    """Pay an invoice from a node"""
    cmd = f"docker exec {node} lncli --network=regtest payinvoice --force {invoice}"
    start_time = time.time()
    output = run_command(cmd)
    duration_ms = int((time.time() - start_time) * 1000)
    
    if output:
        try:
            return json.loads(output), duration_ms
        except json.JSONDecodeError:
            # Handle case where output is not valid JSON
            return {"status": "failed", "raw_output": output}, duration_ms
    return {"status": "failed"}, duration_ms

def find_route(source, target, amount):
    """Find a route from source to target"""
    # Get target's pubkey
    target_info = get_node_info(target)
    if not target_info:
        return None
    
    target_pubkey = target_info.get("identity_pubkey")
    if not target_pubkey:
        return None
    
    cmd = f"docker exec {source} lncli --network=regtest queryroutes --dest={target_pubkey} --amt={amount}"
    output = run_command(cmd)
    if output:
        return json.loads(output)
    return None

def select_nodes_for_pattern(pattern):
    """Select nodes based on the transaction pattern"""
    if pattern == "direct_payment":
        # Choose nodes that have a direct channel
        sender = random.choice(NODES)
        channels = get_node_channels(sender)
        if not channels or not channels.get("channels"):
            # Fallback if we can't get channel info
            receiver = random.choice([n for n in NODES if n != sender])
        else:
            # Get a node that has a direct channel
            channel_peers = []
            for channel in channels.get("channels", []):
                peer_pubkey = channel.get("remote_pubkey")
                # Find which node this pubkey belongs to
                for node in NODES:
                    node_info = get_node_info(node)
                    if node_info and node_info.get("identity_pubkey") == peer_pubkey:
                        channel_peers.append(node)
                        break
            
            if channel_peers:
                receiver = random.choice(channel_peers)
            else:
                receiver = random.choice([n for n in NODES if n != sender])
    
    elif pattern == "multi_hop":
        # Choose sender and receiver that likely need multiple hops
        sender = random.choice(NODES)
        # Try to find a node that's not directly connected
        channels = get_node_channels(sender)
        directly_connected = []
        
        if channels and channels.get("channels"):
            for channel in channels.get("channels", []):
                peer_pubkey = channel.get("remote_pubkey")
                for node in NODES:
                    node_info = get_node_info(node)
                    if node_info and node_info.get("identity_pubkey") == peer_pubkey:
                        directly_connected.append(node)
                        break
        
        potential_receivers = [n for n in NODES if n != sender and n not in directly_connected]
        if potential_receivers:
            receiver = random.choice(potential_receivers)
        else:
            # Fallback
            receiver = random.choice([n for n in NODES if n != sender])
    
    elif pattern == "circular_payment":
        # Create a circular payment path (A->B->C->A is not possible directly)
        # Instead, we'll pick three different nodes to form a path
        if len(NODES) >= 3:
            # Pick three different nodes
            three_nodes = random.sample(NODES, 3)
            # First node sends to second, which will later send to third
            sender = three_nodes[0]
            receiver = three_nodes[1]
            # We'll add a note about the circular intent
            description = f"{random.choice(PAYMENT_DESCRIPTIONS)} (Circular: {sender}->{receiver}->{three_nodes[2]})"
            return sender, receiver, description
        else:
            # Fallback to direct payment if we don't have enough nodes
            sender = random.choice(NODES)
            receiver = random.choice([n for n in NODES if n != sender])
    
    return sender, receiver, random.choice(PAYMENT_DESCRIPTIONS)

def check_payment_feasibility(sender, receiver, amount):
    """Check if a payment is likely to succeed based on channel balances"""
    # Get sender's channels
    channels = get_node_channels(sender)
    if not channels or not channels.get("channels"):
        return False
    
    # For direct payments, check if there's enough local balance
    for channel in channels.get("channels", []):
        remote_pubkey = channel.get("remote_pubkey")
        local_balance = int(channel.get("local_balance", 0))
        
        # Check if this channel connects to the receiver
        receiver_info = get_node_info(receiver)
        if receiver_info and receiver_info.get("identity_pubkey") == remote_pubkey:
            # Direct channel exists, check balance
            if local_balance >= amount:
                return True
    
    # For multi-hop payments, we'll be more lenient
    # Just check if sender has any channel with sufficient balance
    for channel in channels.get("channels", []):
        local_balance = int(channel.get("local_balance", 0))
        if local_balance >= amount:
            return True
    
    return False

def notify_ml_model(event_type, data):
    """Send data to ML model via REST API"""
    try:
        response = requests.post('http://localhost:5000/api/update', json={
            'event_type': event_type,
            'timestamp': datetime.now().isoformat(),
            **data
        }, timeout=1)  # Short timeout to avoid blocking simulation
        return response.status_code == 200
    except Exception as e:
        print(f"Failed to notify ML model: {e}")
        return False

def simulate_transaction():
    """Simulate a transaction between nodes"""
    # Choose transaction pattern based on weights
    patterns = list(TRANSACTION_PATTERNS.keys())
    weights = list(TRANSACTION_PATTERNS.values())
    pattern = random.choices(patterns, weights=weights, k=1)[0]
    
    # Select nodes based on pattern
    sender, receiver, description = select_nodes_for_pattern(pattern)
    
    # Choose a random amount
    amount = random.randint(MIN_PAYMENT_AMOUNT, MAX_PAYMENT_AMOUNT)
    
    # Check if payment is feasible
    if not check_payment_feasibility(sender, receiver, amount):
        # If not feasible, try to find a better pair or reduce amount
        attempts = 0
        while attempts < 3 and not check_payment_feasibility(sender, receiver, amount):
            # Try a different pair or reduce amount
            if random.choice([True, False]) or attempts > 1:
                # Reduce amount
                amount = max(MIN_PAYMENT_AMOUNT, amount // 2)
            else:
                # Try different nodes
                sender, receiver, description = select_nodes_for_pattern(pattern)
            attempts += 1
    
    # Log the transaction attempt
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{timestamp}] Simulating {pattern}: {sender} -> {receiver} for {amount} sats ({description})")
    
    # Capture channel state before transaction
    sender_channels_before = get_node_channels(sender)
    receiver_channels_before = get_node_channels(receiver)
    channel_before = {
        "sender": extract_channel_summary(sender_channels_before),
        "receiver": extract_channel_summary(receiver_channels_before)
    }
    
    # Create invoice
    invoice_result = create_invoice(receiver, amount, description)
    if not invoice_result:
        print(f"Failed to create invoice on {receiver}")
        return None
    
    payment_request = invoice_result.get("payment_request")
    if not payment_request:
        print(f"No payment request in invoice result")
        return None
    
    # Pay invoice
    print(f"Paying invoice from {sender}...")
    payment_result, duration_ms = pay_invoice(sender, payment_request)
    
    # Process result
    success = False
    fee = 0
    payment_hash = invoice_result.get("r_hash", "unknown")
    route_length = 1  # Default for direct payments
    
    if payment_result:
        if "payment_error" in payment_result and payment_result["payment_error"]:
            stats["consecutive_failures"] += 1
            print(f"❌ Payment failed: {payment_result['payment_error']}")
            print(f"⚠️ Consecutive failures: {stats['consecutive_failures']}/{FAILURE_THRESHOLD}")
            
            # Add message about pending rebalancing with clearer instructions
            if stats["consecutive_failures"] >= FAILURE_THRESHOLD:
                print(f"🔄 PENDING: Auto-recovery will begin shortly")
                print(f"⏱️ The system will wait {AUTO_RECOVERY_DELAY} seconds before rebalancing")
            elif stats["consecutive_failures"] > 0:
                remaining = FAILURE_THRESHOLD - stats["consecutive_failures"]
                print(f"⚠️ Auto-recovery will trigger after {remaining} more failed payment(s)")
        elif "status" in payment_result and payment_result["status"] == "SUCCEEDED":
            success = True
            stats["consecutive_failures"] = 0  # Reset consecutive failures
            print(f"✅ Payment succeeded!")
            
            # Extract fee and route information
            if "payment_route" in payment_result:
                route = payment_result["payment_route"]
                fee = route.get("total_fees", "0")
                hops = route.get("hops", [])
                route_length = len(hops)
                
                # Show route if it's multi-hop
                if route_length > 1:
                    hop_str = " -> ".join([hop.get("pub_key", "")[:6] + "..." for hop in hops])
                    print(f"Route: {hop_str} ({route_length} hops)")
                    print(f"Fee: {fee} sats")
            elif "fee" in payment_result:
                fee = payment_result["fee"]
                print(f"Fee: {fee} sats")
        else:
            stats["consecutive_failures"] += 1
            print(f"❌ Payment status: {payment_result.get('status', 'unknown')}")
            print(f"⚠️ Consecutive failures: {stats['consecutive_failures']}/{FAILURE_THRESHOLD}")
            
            # Add message about pending rebalancing with clearer instructions
            if stats["consecutive_failures"] >= FAILURE_THRESHOLD:
                print(f"🔄 PENDING: Auto-recovery will begin shortly")
                print(f"⏱️ The system will wait {AUTO_RECOVERY_DELAY} seconds before rebalancing")
            elif stats["consecutive_failures"] > 0:
                remaining = FAILURE_THRESHOLD - stats["consecutive_failures"]
                print(f"⚠️ Auto-recovery will trigger after {remaining} more failed payment(s)")
    else:
        stats["consecutive_failures"] += 1
        print("❌ No payment result returned")
        print(f"⚠️ Consecutive failures: {stats['consecutive_failures']}/{FAILURE_THRESHOLD}")
        
        # Add message about pending rebalancing with clearer instructions
        if stats["consecutive_failures"] >= FAILURE_THRESHOLD:
            print(f"🔄 PENDING: Auto-recovery will begin shortly")
            print(f"⏱️ The system will wait {AUTO_RECOVERY_DELAY} seconds before rebalancing")
        elif stats["consecutive_failures"] > 0:
            remaining = FAILURE_THRESHOLD - stats["consecutive_failures"]
            print(f"⚠️ Auto-recovery will trigger after {remaining} more failed payment(s)")
    
    # Update statistics
    stats["total_payments"] += 1
    if success:
        stats["successful_payments"] += 1
        stats["total_amount"] += amount
        try:
            stats["total_fees"] += int(fee)
        except (ValueError, TypeError):
            pass
        
        # Update node statistics
        stats["node_payments"][sender]["sent"] += amount
        stats["node_payments"][receiver]["received"] += amount
    else:
        stats["failed_payments"] += 1
    
    # Capture channel state after transaction
    sender_channels_after = get_node_channels(sender)
    receiver_channels_after = get_node_channels(receiver)
    channel_after = {
        "sender": extract_channel_summary(sender_channels_after),
        "receiver": extract_channel_summary(receiver_channels_after)
    }
    
    # Notify ML model about the transaction
    notify_ml_model('transaction', {
        'transaction': {
            'sender': sender,
            'receiver': receiver,
            'amount': amount,
            'success': success,
            'description': description
        },
        'channels': {
            sender: extract_channel_summary(get_node_channels(sender)),
            receiver: extract_channel_summary(get_node_channels(receiver))
        }
    })
    
    # Return transaction data with channel state
    return {
        "timestamp": datetime.now().isoformat(),
        "type": "payment",
        "sender": sender,
        "receiver": receiver,
        "amount": amount,
        "fee": fee,
        "route_length": route_length,
        "success": success,
        "payment_hash": payment_hash,
        "description": description,
        "duration_ms": duration_ms,
        "channel_before": json.dumps(channel_before),
        "channel_after": json.dumps(channel_after)
    }

# Helper function to extract channel summary
def extract_channel_summary(channels_data):
    """Extract a summary of channel balances"""
    if not channels_data or "channels" not in channels_data:
        return {}
    
    summary = []
    for channel in channels_data["channels"]:
        summary.append({
            "remote_pubkey": channel.get("remote_pubkey", "")[:10],
            "capacity": channel.get("capacity", 0),
            "local_balance": channel.get("local_balance", 0),
            "remote_balance": channel.get("remote_balance", 0)
        })
    return summary

def rebalance_channels():
    """Perform rebalancing payments to redistribute liquidity"""
    print("\n" + "="*70)
    print("REBALANCING CHANNELS")
    print("="*70)
    
    stats["rebalance_operations"] += 1
    
    # Define pairs to rebalance
    pairs = []
    for i, sender in enumerate(NODES):
        receiver = NODES[(i + 1) % len(NODES)]  # Next node in the list
        pairs.append((sender, receiver))
    
    for sender, receiver in pairs:
        print(f"Rebalancing {sender} -> {receiver}...")
        
        # Check if there's a direct channel
        sender_channels = get_node_channels(sender)
        if not sender_channels or "channels" not in sender_channels:
            print(f"  ❌ No channels found for {sender}")
            continue
        
        # Find the channel to the receiver
        receiver_info = get_node_info(receiver)
        if not receiver_info:
            print(f"  ❌ Could not get info for {receiver}")
            continue
            
        receiver_pubkey = receiver_info.get("identity_pubkey")
        
        # Find the channel
        channel = None
        for ch in sender_channels["channels"]:
            if ch.get("remote_pubkey") == receiver_pubkey:
                channel = ch
                break
        
        if not channel:
            print(f"  ❌ No direct channel from {sender} to {receiver}")
            continue
        
        # Check channel balance
        local_balance = int(channel.get("local_balance", 0))
        capacity = int(channel.get("capacity", 0))
        
        # Only rebalance if sender has more than 60% of capacity
        if local_balance < capacity * 0.6:
            print(f"  ⏩ Skipping: {sender} has only {local_balance} sats ({local_balance/capacity*100:.1f}% of capacity)")
            continue
        
        # Calculate amount to rebalance (10% of capacity)
        amount = min(5000, int(capacity * 0.1))
        
        # Create invoice
        invoice_result = create_invoice(receiver, amount, "Rebalance")
        if not invoice_result:
            print(f"  ❌ Failed to create invoice on {receiver}")
            continue
            
        payment_request = invoice_result.get("payment_request")
        if not payment_request:
            print(f"  ❌ No payment request in invoice result")
            continue
            
        # Pay invoice
        print(f"  💸 Sending {amount} sats from {sender} to {receiver}...")
        payment_result, _ = pay_invoice(sender, payment_request)
        
        if payment_result:
            if "payment_error" in payment_result and payment_result["payment_error"]:
                print(f"  ❌ Rebalancing failed: {payment_result['payment_error']}")
            elif "status" in payment_result and payment_result["status"] == "SUCCEEDED":
                print(f"  ✅ Rebalancing succeeded!")
                stats["rebalance_successes"] += 1
            else:
                print(f"  ❌ Rebalancing failed: {payment_result.get('status', 'unknown')}")
        else:
            print(f"  ❌ Rebalancing failed: No payment result returned")
    
    print("="*70)

def validate_transaction_data(transaction):
    """Validate transaction data before writing to CSV"""
    # Ensure all required fields are present
    for field in CSV_HEADERS:
        if field not in transaction:
            transaction[field] = ""
    
    # Ensure channel data is properly formatted
    for field in ["channel_before", "channel_after"]:
        if field in transaction and transaction[field] and not isinstance(transaction[field], str):
            try:
                transaction[field] = json.dumps(transaction[field])
            except:
                transaction[field] = "{}"
    
    return transaction

def log_transaction(transaction, csv_writer):
    """Log transaction data to CSV file"""
    # Validate data before writing
    transaction = validate_transaction_data(transaction)
    
    # Write the row
    csv_writer.writerow([
        transaction.get("timestamp", ""),
        transaction.get("type", "payment"),
        transaction.get("sender", ""),
        transaction.get("receiver", ""),
        transaction.get("amount", 0),
        transaction.get("fee", 0),
        transaction.get("route_length", 1),
        transaction.get("success", False),
        transaction.get("payment_hash", ""),
        transaction.get("description", ""),
        transaction.get("duration_ms", 0),
        transaction.get("channel_before", ""),
        transaction.get("channel_after", "")
    ])

def visualize_channel(local_pct, remote_pct):
    """Create a visual representation of channel balance"""
    width = 30
    local_width = int(width * local_pct / 100)
    remote_width = int(width * remote_pct / 100)
    
    local_bar = "█" * local_width + " " * (width - local_width)
    remote_bar = "█" * remote_width + " " * (width - remote_width)
    
    return f"Local:  [{local_bar}] {local_pct:.1f}%\nRemote: [{remote_bar}] {remote_pct:.1f}%"

def print_statistics():
    """Print current simulation statistics"""
    # Calculate runtime in minutes
    runtime = (time.time() - stats["start_time"]) / 60
    
    print("\n" + "="*70)
    print("LIGHTNING NETWORK SIMULATION STATISTICS")
    print("="*70)
    print(f"Runtime: {runtime:.2f} minutes")
    print(f"Total payments: {stats['total_payments']}")
    
    if stats["total_payments"] > 0:
        success_rate = stats["successful_payments"] / stats["total_payments"] * 100
        print(f"Successful: {stats['successful_payments']} ({success_rate:.1f}%)")
    else:
        print(f"Successful: {stats['successful_payments']} (0.0%)")
        
    print(f"Failed: {stats['failed_payments']}")
    
    # Add consecutive failures counter
    if stats["consecutive_failures"] > 0:
        print(f"⚠️ Consecutive failures: {stats['consecutive_failures']}/{FAILURE_THRESHOLD}")
        if stats["consecutive_failures"] >= FAILURE_THRESHOLD:
            print(f"🔄 AUTO-RECOVERY PENDING: Rebalancing will begin soon...")
    
    print(f"Total amount: {stats['total_amount']} sats")
    print(f"Total fees: {stats['total_fees']} sats")
    
    if stats["successful_payments"] > 0:
        avg_fee = stats["total_fees"] / stats["successful_payments"]
        print(f"Average fee: {avg_fee:.2f} sats per payment")
        
        if stats["total_amount"] > 0:
            fee_pct = stats["total_fees"] / stats["total_amount"] * 100
            print(f"Fee percentage: {fee_pct:.4f}%")
        else:
            print("Fee percentage: 0.0000%")
    else:
        print("Average fee: 0.00 sats per payment")
        print("Fee percentage: 0.0000%")
    
    # Calculate payments per minute
    if runtime > 0:
        rate = stats["total_payments"] / runtime
        print(f"Payments per minute: {rate:.2f}")
    else:
        print("Payments per minute: 0.00")
    
    # Add rebalancing statistics
    if stats["rebalance_operations"] > 0:
        print(f"Rebalance operations: {stats['rebalance_operations']}")
        rebalance_rate = stats["rebalance_successes"] / stats["rebalance_operations"] * 100
        print(f"Rebalance successes: {stats['rebalance_successes']} ({rebalance_rate:.1f}%)")
    
    # Add auto-recovery statistics
    if stats["auto_rebalance_events"] > 0:
        print(f"Auto-recovery events: {stats['auto_rebalance_events']}")
        recovery_rate = stats["auto_rebalance_successes"] / stats["auto_rebalance_events"] * 100
        print(f"Auto-recovery success rate: {recovery_rate:.1f}%")
    
    print("\nNode Activity:")
    print("-"*70)
    print(f"{'Node':<10} | {'Sent (sats)':<15} | {'Received (sats)':<15} | {'Net Flow':<15}")
    print("-"*70)
    
    for node, data in stats["node_payments"].items():
        sent = data["sent"]
        received = data["received"]
        net_flow = received - sent
        print(f"{node:<10} | {sent:<15} | {received:<15} | {net_flow:<15}")
    
    print("="*70)

def check_channel_balances():
    """Check and display current channel balances"""
    print("\n" + "="*70)
    print("CURRENT CHANNEL BALANCES")
    print("="*70)
    
    for node in NODES:
        print(f"\n{node} Channels:")
        print("-"*70)
        
        channels = get_node_channels(node)
        if channels and "channels" in channels:
            for i, channel in enumerate(channels["channels"]):
                remote_pubkey = channel.get("remote_pubkey", "Unknown")[:10] + "..."
                capacity = channel.get("capacity", 0)
                local_balance = channel.get("local_balance", 0)
                remote_balance = channel.get("remote_balance", 0)
                
                # Convert to integers for calculation
                try:
                    capacity_int = int(capacity)
                    local_balance_int = int(local_balance)
                    remote_balance_int = int(remote_balance)
                except (ValueError, TypeError):
                    # If conversion fails, use 0 for percentage calculation
                    capacity_int = 1  # Avoid division by zero
                    local_balance_int = 0
                    remote_balance_int = 0
                
                # Calculate percentages
                local_pct = local_balance_int / capacity_int * 100
                remote_pct = remote_balance_int / capacity_int * 100
                
                # Find remote node name
                remote_node = "Unknown"
                for n in NODES:
                    if n == node:
                        continue
                    info = get_node_info(n)
                    if info and info.get("identity_pubkey", "").startswith(remote_pubkey[:10]):
                        remote_node = n
                        break
                
                print(f"Channel {i+1} with {remote_node}:")
                print(f"  Capacity: {capacity} sats")
                print(f"  {visualize_channel(local_pct, remote_pct)}")
        else:
            print("  No channels found or error retrieving channel data")
    
    print("="*70)

def signal_handler(sig, frame):
    """Handle Ctrl+C to gracefully exit the simulation"""
    print("\nSimulation interrupted. Exiting immediately...")
    # Force immediate exit
    os._exit(0)

# Add a second signal handler for SIGTERM
signal.signal(signal.SIGTERM, signal_handler)

def targeted_rebalance():
    """Perform targeted rebalancing to fix failing payment paths"""
    print("\n" + "="*70)
    print("AUTO-RECOVERY REBALANCING")
    print("="*70)
    
    stats["auto_rebalance_events"] += 1
    rebalance_success = False
    
    # Get all channels and identify the most imbalanced ones
    imbalanced_channels = []
    
    for node in NODES:
        channels = get_node_channels(node)
        if not channels or "channels" not in channels:
            continue
            
        for channel in channels["channels"]:
            capacity = int(channel.get("capacity", 0))
            local_balance = int(channel.get("local_balance", 0))
            remote_pubkey = channel.get("remote_pubkey", "")
            
            # Calculate imbalance percentage (0 = balanced, 100 = completely imbalanced)
            local_pct = local_balance / capacity * 100
            imbalance = abs(50 - local_pct)
            
            # Find remote node name
            remote_node = "unknown"
            for n in NODES:
                if n == node:
                    continue
                info = get_node_info(n)
                if info and info.get("identity_pubkey", "") == remote_pubkey:
                    remote_node = n
                    break
            
            imbalanced_channels.append({
                "node": node,
                "remote_node": remote_node,
                "local_pct": local_pct,
                "imbalance": imbalance,
                "capacity": capacity,
                "local_balance": local_balance,
                "remote_pubkey": remote_pubkey
            })
    
    # Sort channels by imbalance (most imbalanced first)
    imbalanced_channels.sort(key=lambda x: x["imbalance"], reverse=True)
    
    # Rebalance the top 3 most imbalanced channels
    for idx, channel in enumerate(imbalanced_channels[:3]):
        node = channel["node"]
        remote_node = channel["remote_node"]
        local_pct = channel["local_pct"]
        capacity = channel["capacity"]
        
        print(f"Rebalancing {node} <-> {remote_node} (current balance: {local_pct:.1f}% local)")
        
        # Determine direction and amount
        if local_pct > 50:
            # Node has too much local balance, send to remote
            sender = node
            receiver = remote_node
            target_pct = max(40, local_pct - 20)  # Aim for more balanced, but not completely
        else:
            # Node has too little local balance, receive from remote
            sender = remote_node
            receiver = node
            target_pct = min(60, local_pct + 20)  # Aim for more balanced, but not completely
        
        # Calculate amount to transfer (percentage of capacity)
        amount = int(capacity * RECOVERY_REBALANCE_AMOUNT)
        if amount < 10000:
            amount = min(10000, int(capacity * 0.1))  # Ensure minimum effective amount
        
        print(f"  💸 Transferring {amount} sats from {sender} to {receiver}...")
        
        # Capture channel state before rebalancing
        node_channels_before = get_node_channels(node)
        remote_channels_before = get_node_channels(remote_node)
        channel_before = {
            "sender": extract_channel_summary(node_channels_before),
            "receiver": extract_channel_summary(remote_channels_before)
        }
        
        # Create invoice for rebalancing
        invoice_result = create_invoice(receiver, amount, "Auto-recovery rebalance")
        if not invoice_result:
            print(f"  ❌ Failed to create invoice on {receiver}")
            continue
            
        payment_request = invoice_result.get("payment_request")
        if not payment_request:
            print(f"  ❌ No payment request in invoice result")
            continue
        
        # Pay invoice
        payment_result, _ = pay_invoice(sender, payment_request)
        
        if payment_result:
            if "payment_error" in payment_result and payment_result["payment_error"]:
                print(f"  ❌ Rebalancing failed: {payment_result['payment_error']}")
            elif "status" in payment_result and payment_result["status"] == "SUCCEEDED":
                print(f"  ✅ Rebalancing succeeded!")
                rebalance_success = True
                stats["auto_rebalance_successes"] += 1
            else:
                print(f"  ❌ Rebalancing failed: {payment_result.get('status', 'unknown')}")
        else:
            print(f"  ❌ Rebalancing failed: No payment result returned")
        
        # Capture channel state after rebalancing
        node_channels_after = get_node_channels(node)
        remote_channels_after = get_node_channels(remote_node)
        channel_after = {
            "sender": extract_channel_summary(node_channels_after),
            "receiver": extract_channel_summary(remote_channels_after)
        }
        
        # Log the rebalancing operation to CSV
        rebalance_data = {
            "timestamp": datetime.now().isoformat(),
            "type": "rebalance",
            "sender": sender,
            "receiver": receiver,
            "amount": amount,
            "fee": 0,
            "route_length": 1,
            "success": rebalance_success,
            "payment_hash": "",
            "description": f"Auto-recovery rebalance ({local_pct:.1f}% imbalance)",
            "duration_ms": 0,
            "channel_before": json.dumps(channel_before),
            "channel_after": json.dumps(channel_after)
        }
        
        # Add to CSV file - use a separate with block to ensure proper file handling
        try:
            with open(CSV_OUTPUT, 'a', newline='') as csvfile:
                csv_writer = csv.writer(csvfile)
                log_transaction(rebalance_data, csv_writer)
        except Exception as e:
            print(f"Error logging rebalance data: {e}")
    
    print("="*70)
    return rebalance_success

def log_channel_snapshot():
    """Log a snapshot of all channel states to CSV"""
    timestamp = datetime.now().isoformat()
    
    all_channels = {}
    for node in NODES:
        channels = get_node_channels(node)
        all_channels[node] = extract_channel_summary(channels)
    
    snapshot_data = {
        "timestamp": timestamp,
        "type": "snapshot",
        "sender": "",
        "receiver": "",
        "amount": 0,
        "fee": 0,
        "route_length": 0,
        "success": True,
        "payment_hash": "",
        "description": "Periodic channel state snapshot",
        "duration_ms": 0,
        "channel_before": "",
        "channel_after": json.dumps(all_channels)
    }
    
    # Add to CSV file
    with open(CSV_OUTPUT, 'a', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        log_transaction(snapshot_data, csv_writer)

# First, let's add a progress bar function
def show_progress_bar(duration, message):
    """Display a progress bar for the given duration"""
    print(f"{message} (please wait {duration} seconds)")
    bar_length = 30
    start_time = time.time()
    end_time = start_time + duration
    
    # Print the start of the progress bar
    print("[" + " " * bar_length + "]", end="\r")
    print("[", end="", flush=True)
    
    # Update the bar until duration is complete
    completed = 0
    while time.time() < end_time:
        elapsed = time.time() - start_time
        progress = int(elapsed / duration * bar_length)
        
        # Only update if progress has changed
        if progress > completed:
            # Print progress characters
            for i in range(completed, progress):
                print("=", end="", flush=True)
            completed = progress
        
        # Show remaining space
        remaining = bar_length - completed
        if remaining > 0:
            print(" " * remaining + "]", end="\r")
            print("[" + "=" * completed, end="", flush=True)
        
        time.sleep(0.1)  # More frequent updates for smoother display
    
    # Complete the bar
    print("=" * (bar_length - completed) + "] Done!")

def check_for_rebalance_suggestions():
    """Check if ML model has suggested any rebalancing operations"""
    try:
        response = requests.get('http://localhost:5000/api/get_suggestions', timeout=1)
        if response.status_code == 200:
            suggestions = response.json()
            if suggestions:
                print("\n🤖 ML MODEL SUGGESTIONS:")
                for suggestion in suggestions:
                    print(f"  - Rebalance {suggestion['from_node']} -> {suggestion['to_node']} ({suggestion['amount']} sats)")
                    # Optionally implement the suggestion
                return suggestions
    except Exception as e:
        print(f"Failed to get ML model suggestions: {e}")
    return []

def main():
    """Main simulation function"""
    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    print("="*70)
    print("LIGHTNING NETWORK TRANSACTION SIMULATOR")
    print("="*70)
    print(f"Simulating transactions between {len(NODES)} nodes")
    print(f"Output data will be saved to: {CSV_OUTPUT}")
    print(f"Simulation will run for: {SIMULATION_DURATION/60:.1f} minutes")
    print(f"Payment range: {MIN_PAYMENT_AMOUNT} to {MAX_PAYMENT_AMOUNT} sats")
    if REBALANCE_FREQUENCY > 0:
        print(f"Rebalancing frequency: Every {REBALANCE_FREQUENCY} transactions")
    else:
        print("Automatic rebalancing: Disabled")
    print(f"Auto-recovery: After {FAILURE_THRESHOLD} consecutive failures")
    print("="*70)
    print("Press Ctrl+C to stop the simulation early")
    print("Starting in 3 seconds...")
    time.sleep(3)
    
    # Initialize statistics
    stats["start_time"] = time.time()
    stats["consecutive_failures"] = 0
    
    # Create or open CSV file
    with open(CSV_OUTPUT, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(CSV_HEADERS)
        
        end_time = time.time() + SIMULATION_DURATION
        transaction_count = 0
        rebalance_count = 0
        
        # Initial channel balance check
        try:
            check_channel_balances()
        except Exception as e:
            print(f"Error checking initial channel balances: {e}")
        
        # Add snapshot timer
        last_snapshot_time = time.time()
        SNAPSHOT_INTERVAL = 300  # Take a snapshot every 5 minutes
        
        while time.time() < end_time:
            try:
                # Check if we need regular rebalancing
                if REBALANCE_FREQUENCY > 0:
                    rebalance_count += 1
                    if rebalance_count >= REBALANCE_FREQUENCY:
                        rebalance_channels()
                        rebalance_count = 0
                
                # Simulate a transaction
                transaction = simulate_transaction()
                
                # Process transaction result
                if transaction:
                    log_transaction(transaction, csv_writer)
                    csvfile.flush()  # Ensure data is written immediately
                    transaction_count += 1
                    
                    # Check if we need auto-recovery after a failed transaction
                    if stats["consecutive_failures"] >= FAILURE_THRESHOLD:
                        print(f"\n⚠️ Detected {stats['consecutive_failures']} consecutive failures!")
                        print(f"🔄 REBALANCING: Starting auto-recovery process...")
                        print(f"⏱️ Please wait while we rebalance the network to improve payment success rates.")
                        
                        # Show progress bar during waiting period
                        show_progress_bar(AUTO_RECOVERY_DELAY, "Preparing network for rebalancing")
                        
                        # Perform targeted rebalancing
                        if targeted_rebalance():
                            print("✅ Auto-recovery successful! Resuming normal operation.")
                            stats["consecutive_failures"] = 0
                        else:
                            print("⚠️ Auto-recovery partially successful. Continuing with caution.")
                            stats["consecutive_failures"] = max(0, stats["consecutive_failures"] - 2)
                        
                        # Check channel balances after rebalancing
                        try:
                            check_channel_balances()
                        except Exception as e:
                            print(f"Error checking channel balances: {e}")
                
                # Check if it's time for a channel snapshot
                current_time = time.time()
                if current_time - last_snapshot_time >= SNAPSHOT_INTERVAL:
                    log_channel_snapshot()
                    last_snapshot_time = current_time
                
                # Print statistics every 10 transactions
                if transaction_count % 10 == 0 and transaction_count > 0:
                    print_statistics()
                    try:
                        check_channel_balances()
                    except Exception as e:
                        print(f"Error checking channel balances: {e}")
                
                # Check for ML model suggestions every 5 transactions
                if transaction_count % 5 == 0:
                    suggestions = check_for_rebalance_suggestions()
                    # Optionally implement suggestions here
                
                # Random delay between payments
                delay = random.uniform(PAYMENT_INTERVAL_MIN, PAYMENT_INTERVAL_MAX)
                time.sleep(delay)
            except Exception as e:
                print(f"Error during simulation: {e}")
                time.sleep(5)  # Wait a bit before trying again
    
    # Final statistics
    print("\nSimulation complete!")
    print_statistics()
    try:
        check_channel_balances()
    except Exception as e:
        print(f"Error checking channel balances: {e}")
    print(f"Transaction data saved to {CSV_OUTPUT}")

if __name__ == "__main__":
    main() 