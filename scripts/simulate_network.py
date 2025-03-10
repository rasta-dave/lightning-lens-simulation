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
import traceback

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
    "timestamp", "type", "sender", "receiver", "amount", "fee", 
    "route_length", "success", "payment_hash", "description", 
    "duration_ms", "channel_before", "channel_after",
    "sender_balance_before", "sender_balance_after",
    "receiver_balance_before", "receiver_balance_after"
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

def run_command(cmd, timeout=30):
    """Run a command and return the output"""
    try:
        # Use subprocess with timeout
        result = subprocess.run(
            cmd, 
            shell=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout  # Add timeout parameter
        )
        
        # Check for wallet locked error
        if result.returncode != 0:
            if "wallet locked" in result.stderr:
                # Extract node name from command
                if "docker exec" in cmd:
                    node_name = cmd.split("docker exec ")[1].split(" ")[0]
                    print(f"🔒 Wallet locked detected for {node_name}. Attempting to unlock...")
                    
                    # Try to unlock the wallet
                    if unlock_wallet(node_name):
                        # Retry the command after successful unlock
                        print(f"Retrying command after wallet unlock...")
                        retry_result = subprocess.run(
                            cmd,
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            timeout=timeout
                        )
                        
                        if retry_result.returncode == 0:
                            return retry_result.stdout.strip()
                        else:
                            print(f"Command failed even after wallet unlock: {cmd}")
                            print(f"Error: {retry_result.stderr}")
                            return None
            
            # Handle other errors
            print(f"Command failed: {cmd}")
            print(f"Error: {result.stderr}")
            return None
        
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        print(f"Command timed out: {cmd}")
        # Try to restart the problematic node
        if "lnd-" in cmd and "lncli" in cmd:
            node_name = cmd.split("docker exec ")[1].split(" ")[0]
            print(f"⚠️ Node {node_name} appears to be unresponsive. Attempting to recover...")
            
            try:
                # Check if wallet is locked
                unlock_check = subprocess.run(
                    f"docker exec {node_name} lncli --network=regtest getinfo",
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5
                )
                
                if "wallet locked" in unlock_check.stderr.lower() or "wallet not found" in unlock_check.stderr.lower():
                    print(f"🔒 Wallet appears to be locked on {node_name}.")
                    # Try to unlock the wallet using our new function
                    if unlock_wallet(node_name):
                        # Try the command again
                        print(f"Retrying command...")
                        retry_result = subprocess.run(
                            cmd,
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            timeout=timeout
                        )
                        
                        if retry_result.returncode == 0:
                            print(f"✅ Command succeeded after wallet unlock")
                            return retry_result.stdout.strip()
                        else:
                            print(f"❌ Command still failing after wallet unlock: {retry_result.stderr}")
                            return None
                else:
                    # Just restart the node
                    print(f"Restarting {node_name}...")
                    subprocess.run(f"docker restart {node_name}", shell=True, timeout=30)
                    print(f"Waiting for {node_name} to initialize...")
                    time.sleep(15)
                    
                    # Try to unlock the wallet after restart
                    unlock_wallet(node_name)
                    
                    # Try the command again
                    print(f"Retrying command...")
                    retry_result = subprocess.run(
                        cmd,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=timeout
                    )
                    
                    if retry_result.returncode == 0:
                        print(f"✅ Command succeeded after node restart")
                        return retry_result.stdout.strip()
                    else:
                        print(f"❌ Command still failing after restart: {retry_result.stderr}")
                        return None
                
            except Exception as e:
                print(f"❌ Error during recovery attempt: {e}")
                return None
        
        return None
    except Exception as e:
        print(f"Error executing command: {e}")
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
        try:
            # Parse the JSON output
            return json.loads(output)
        except json.JSONDecodeError as e:
            print(f"Error parsing channel data for {node}: {e}")
            print(f"Raw output: {output[:100]}...")  # Print first 100 chars of output
            return {"channels": []}  # Return empty channels list instead of None
    return {"channels": []}  # Return empty channels list instead of None

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

def notify_websocket(event_type, data):
    """Send data to WebSocket server for ML model consumption"""
    try:
        import websockets
        import asyncio
        
        async def send_message():
            uri = "ws://localhost:6789"
            async with websockets.connect(uri) as websocket:
                # Make sure data is a dictionary, not a string
                if isinstance(data, str):
                    try:
                        # Try to parse it as JSON
                        data_dict = json.loads(data)
                    except json.JSONDecodeError:
                        # If it's not valid JSON, wrap it in a dictionary
                        data_dict = {"message": data}
                else:
                    # Already a dictionary or other object
                    data_dict = data
                
                message = {
                    "type": event_type,
                    "data": data_dict
                }
                await websocket.send(json.dumps(message))
                # Wait briefly for acknowledgment
                await asyncio.sleep(0.1)
        
        # Run the async function in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send_message())
        loop.close()
        return True
    except Exception as e:
        print(f"Failed to notify WebSocket server: {e}")
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
    payment_error = None
    
    if "payment_error" in payment_result and payment_result["payment_error"]:
        payment_error = payment_result["payment_error"]
        print(f"❌ Payment status: failed")
        print(f"   Error: {payment_error}")
        stats["failed_payments"] += 1
        stats["consecutive_failures"] += 1
    else:
        success = True
        print(f"✅ Payment status: success")
        stats["successful_payments"] += 1
        stats["consecutive_failures"] = 0
    
    # Capture channel state after transaction
    sender_channels_after = get_node_channels(sender)
    receiver_channels_after = get_node_channels(receiver)
    channel_after = {
        "sender": extract_channel_summary(sender_channels_after),
        "receiver": extract_channel_summary(receiver_channels_after)
    }
    
    # Send transaction data to HTTP API
    send_transaction_data(sender, receiver, amount, success)
    
    # Send channel state data to HTTP API for each channel
    for node, channels_data in [(sender, sender_channels_after), (receiver, receiver_channels_after)]:
        if isinstance(channels_data, dict) and "channels" in channels_data:
            for channel in channels_data["channels"]:
                if isinstance(channel, dict):
                    remote_pubkey = channel.get("remote_pubkey", "")
                    capacity = int(channel.get("capacity", 0))
                    local_balance = int(channel.get("local_balance", 0))
                    if remote_pubkey and capacity > 0:
                        send_channel_state(node, remote_pubkey, capacity, local_balance)
    
    # Notify WebSocket server about the transaction
    notify_websocket('transaction', {
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
        "fee": 0,
        "route_length": 1,
        "success": success,
        "payment_hash": "",
        "description": description,
        "duration_ms": duration_ms,
        "channel_before": json.dumps(channel_before),
        "channel_after": json.dumps(channel_after)
    }

# Helper function to extract channel summary
def extract_channel_summary(channels_data):
    """Extract a summary of channel data for logging"""
    summary = {}
    
    if not isinstance(channels_data, dict):
        return summary
        
    channels = channels_data.get("channels", [])
    for channel in channels:
        if not isinstance(channel, dict):
            continue
            
        remote_pubkey = channel.get("remote_pubkey", "")
        if not remote_pubkey:
            continue
            
        channel_id = f"{remote_pubkey[:8]}"
        summary[channel_id] = {
            "remote_pubkey": remote_pubkey,
            "capacity": int(channel.get("capacity", 0)),
            "local_balance": int(channel.get("local_balance", 0)),
            "remote_balance": int(channel.get("remote_balance", 0))
        }
    
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
    """Log a transaction to the CSV file and notify WebSocket server"""
    # Extract transaction data
    
    # Calculate balance summaries
    sender_balance_before = 0
    sender_balance_after = 0
    receiver_balance_before = 0
    receiver_balance_after = 0
    
    # Safely extract channel data
    if isinstance(transaction.get("channel_before"), dict):
        sender_data = transaction.get("channel_before", {}).get("sender", {})
        if isinstance(sender_data, dict):
            sender_balance_before = sum_channel_balances(sender_data)
            
        receiver_data = transaction.get("channel_before", {}).get("receiver", {})
        if isinstance(receiver_data, dict):
            receiver_balance_before = sum_channel_balances(receiver_data)
    
    if isinstance(transaction.get("channel_after"), dict):
        sender_data = transaction.get("channel_after", {}).get("sender", {})
        if isinstance(sender_data, dict):
            sender_balance_after = sum_channel_balances(sender_data)
            
        receiver_data = transaction.get("channel_after", {}).get("receiver", {})
        if isinstance(receiver_data, dict):
            receiver_balance_after = sum_channel_balances(receiver_data)
    
    # Create row data
    row = [
        transaction["timestamp"],
        transaction["type"],
        transaction["sender"],
        transaction["receiver"],
        transaction["amount"],
        transaction["fee"],
        transaction["route_length"],
        transaction["success"],
        transaction["payment_hash"],
        transaction["description"],
        transaction["duration_ms"],
        json.dumps(transaction.get("channel_before", {})),
        json.dumps(transaction.get("channel_after", {})),
        sender_balance_before,
        sender_balance_after,
        receiver_balance_before,
        receiver_balance_after
    ]
    
    # Write to CSV
    csv_writer.writerow(row)
    
    # Notify WebSocket server
    try:
        notify_websocket("transaction", {
            "timestamp": transaction["timestamp"],
            "sender": transaction["sender"],
            "receiver": transaction["receiver"],
            "amount": transaction["amount"],
            "success": transaction["success"],
            "description": transaction["description"]
        })
    except Exception as e:
        print(f"Error notifying WebSocket server: {e}")
        
    # Send transaction data to HTTP API
    try:
        send_transaction_data(
            transaction["sender"],
            transaction["receiver"],
            transaction["amount"],
            transaction["success"]
        )
    except Exception as e:
        print(f"Error sending transaction data to HTTP API: {e}")

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
    """Check and display channel balances for all nodes"""
    print("\nCHANNEL BALANCES:")
    print("-----------------")
    
    all_channels = {}
    
    for node in NODES:
        channels_data = get_node_channels(node)
        if not isinstance(channels_data, dict):
            print(f"Warning: Invalid channel data for {node}")
            continue
            
        channels = channels_data.get("channels", [])
        if not channels:
            print(f"No channels found for {node}")
            continue
            
        node_channels = []
        for channel in channels:
            if not isinstance(channel, dict):
                continue
                
            remote_pubkey = channel.get("remote_pubkey", "")
            capacity = channel.get("capacity", "0")
            local_balance = channel.get("local_balance", "0")
            remote_balance = channel.get("remote_balance", "0")
            
            # Calculate percentages
            capacity_int = int(capacity)
            local_balance_int = int(local_balance)
            if capacity_int > 0:
                local_pct = local_balance_int / capacity_int * 100
                remote_pct = int(remote_balance) / capacity_int * 100
            else:
                local_pct = 0
                remote_pct = 0
            
            # Find remote node name
            remote_node = "unknown"
            for n in NODES:
                if n == node:
                    continue
                n_info = get_node_info(n)
                if n_info and n_info.get("identity_pubkey") == remote_pubkey:
                    remote_node = n
                    break
            
            print(f"  {node} <--> {remote_node}: {local_balance}/{capacity} sats ({local_pct:.1f}%)")
            
            # Add to node_channels list
            node_channels.append({
                "remote_pubkey": remote_pubkey,
                "capacity": capacity,
                "local_balance": local_balance,
                "remote_balance": remote_balance
            })
            
            # Send channel state to HTTP API
            send_channel_state(node, remote_pubkey, int(capacity), int(local_balance))
        
        # Add to all_channels dict
        all_channels[node] = node_channels
    
    # Send channel state to WebSocket server
    notify_websocket("channel_update", all_channels)
    
    print("-----------------")

def signal_handler(sig, frame):
    """Handle Ctrl+C to gracefully exit the simulation"""
    print("\nSimulation interrupted. Exiting immediately...")
    # Force immediate exit
    os._exit(0)

# Add a second signal handler for SIGTERM
signal.signal(signal.SIGTERM, signal_handler)

def targeted_rebalance():
    """Perform targeted rebalancing based on channel imbalances"""
    print("\n" + "="*70)
    print("AUTO-RECOVERY REBALANCING")
    print("="*70)
    
    try:
        # Get all channels and calculate imbalance
        imbalanced_channels = []
        for node in NODES:
            channels_data = get_node_channels(node)
            
            # Ensure we have valid channel data
            if not isinstance(channels_data, dict):
                print(f"Warning: Invalid channel data for {node}")
                continue
                
            channels = channels_data.get("channels", [])
            if not channels:
                print(f"No channels found for {node}")
                continue
                
            for channel in channels:
                # Skip if channel data is invalid
                if not isinstance(channel, dict):
                    continue
                    
                remote_pubkey = channel.get("remote_pubkey", "")
                capacity = int(channel.get("capacity", 0))
                local_balance = int(channel.get("local_balance", 0))
                remote_balance = int(channel.get("remote_balance", 0))
                
                # Skip channels with zero capacity
                if capacity == 0:
                    continue
                    
                # Calculate local percentage
                local_pct = local_balance / capacity * 100
                
                # Find remote node name
                remote_node = None
                for n in NODES:
                    if n == node:
                        continue
                    n_info = get_node_info(n)
                    if n_info and n_info.get("identity_pubkey") == remote_pubkey:
                        remote_node = n
                        break
                
                # Skip if we couldn't identify the remote node
                if not remote_node:
                    continue
                
                # Add to imbalanced list if significantly imbalanced
                if local_pct < 35 or local_pct > 65:
                    imbalanced_channels.append({
                        "node": node,
                        "remote_node": remote_node,
                        "capacity": capacity,
                        "local_balance": local_balance,
                        "remote_balance": remote_balance,
                        "local_pct": local_pct,
                        "imbalance": abs(50 - local_pct)  # Distance from balanced (50%)
                    })
        
        # Sort channels by imbalance (most imbalanced first)
        imbalanced_channels.sort(key=lambda x: x["imbalance"], reverse=True)
        
        # Attempt to rebalance the most imbalanced channels
        rebalance_success = False
        for channel in imbalanced_channels[:3]:  # Try top 3 most imbalanced
            node = channel["node"]
            remote_node = channel["remote_node"]
            local_pct = channel["local_pct"]
            
            # Skip if we don't have valid node names
            if not node or not remote_node:
                continue
                
            print(f"Rebalancing {node} <-> {remote_node} (current balance: {local_pct:.1f}% local)")
            
            # Determine direction and amount
            if local_pct < 35:
                # Local side is low, need to receive funds
                sender = remote_node
                receiver = node
                amount = int(channel["capacity"] * RECOVERY_REBALANCE_AMOUNT)
                print(f"  💸 Transferring {amount} sats from {sender} to {receiver}...")
            else:
                # Local side is high, need to send funds
                sender = node
                receiver = remote_node
                amount = int(channel["capacity"] * RECOVERY_REBALANCE_AMOUNT)
                print(f"  💸 Transferring {amount} sats from {sender} to {receiver}...")
            
            # Attempt direct rebalance
            success = rebalance_channel(sender, receiver, amount)
            if success:
                rebalance_success = True
        
        # If direct rebalancing failed, try circular rebalancing
        if not rebalance_success and len(imbalanced_channels) >= 2:
            print("\nTrying circular rebalancing strategy...")
            
            # Try to find two channels that can be balanced via a circular payment
            for i in range(min(3, len(imbalanced_channels))):
                channel1 = imbalanced_channels[i]
                
                # Skip if we don't have valid node names
                if not channel1["node"] or not channel1["remote_node"]:
                    continue
                    
                for j in range(i+1, min(5, len(imbalanced_channels))):
                    channel2 = imbalanced_channels[j]
                    
                    # Skip if we don't have valid node names
                    if not channel2["node"] or not channel2["remote_node"]:
                        continue
                    
                    # Find a common peer for circular rebalancing
                    middle_hop = find_common_peer(channel1["node"], channel2["node"])
                    
                    if middle_hop:
                        # Determine amount (smaller of the two imbalances)
                        amount = min(
                            int(channel1["capacity"] * RECOVERY_REBALANCE_AMOUNT),
                            int(channel2["capacity"] * RECOVERY_REBALANCE_AMOUNT)
                        )
                        
                        # Attempt circular rebalance
                        print(f"  Attempting circular rebalance: {channel1['node']} -> {middle_hop} -> {channel2['node']}")
                        success = circular_rebalance(channel1["node"], middle_hop, channel2["node"], amount)
                        if success:
                            rebalance_success = True
                            break
                
                if rebalance_success:
                    break
        
        print("="*70)
        return rebalance_success
    
    except Exception as e:
        print(f"Error during rebalancing: {e}")
        traceback.print_exc()
        return False

def find_common_peer(node1, node2):
    """Find a common peer between two nodes for circular rebalancing"""
    if not node1 or not node2 or node1 == node2:
        print(f"  ❌ Invalid nodes for finding common peer: {node1}, {node2}")
        return None
        
    try:
        # Get channels for both nodes
        node1_channels = get_node_channels(node1)
        node2_channels = get_node_channels(node2)
        
        # Ensure we have valid channel data
        if not isinstance(node1_channels, dict) or not isinstance(node2_channels, dict):
            print(f"  ❌ Invalid channel data for nodes")
            return None
            
        # Get peers of node1
        node1_peers = set()
        for channel in node1_channels.get("channels", []):
            if not isinstance(channel, dict):
                continue
                
            remote_pubkey = channel.get("remote_pubkey", "")
            if not remote_pubkey:
                continue
                
            # Find node name for this pubkey
            for node in NODES:
                if node == node1:
                    continue
                    
                node_info = get_node_info(node)
                if node_info and node_info.get("identity_pubkey") == remote_pubkey:
                    node1_peers.add(node)
                    break
        
        # Get peers of node2
        node2_peers = set()
        for channel in node2_channels.get("channels", []):
            if not isinstance(channel, dict):
                continue
                
            remote_pubkey = channel.get("remote_pubkey", "")
            if not remote_pubkey:
                continue
                
            # Find node name for this pubkey
            for node in NODES:
                if node == node2:
                    continue
                    
                node_info = get_node_info(node)
                if node_info and node_info.get("identity_pubkey") == remote_pubkey:
                    node2_peers.add(node)
                    break
        
        # Find common peers
        common_peers = node1_peers.intersection(node2_peers)
        if common_peers:
            common_peer = next(iter(common_peers))
            print(f"  ✅ Found common peer: {common_peer}")
            return common_peer
            
        print(f"  ❌ No common peers found between {node1} and {node2}")
        return None
    except Exception as e:
        print(f"  ❌ Error finding common peer: {e}")
        traceback.print_exc()
        return None

def circular_rebalance(first_hop, middle_hop, final_hop, amount):
    """Perform a circular rebalance payment"""
    try:
        # Create an invoice on the final hop
        invoice_cmd = f"docker exec {final_hop} lncli --network=regtest addinvoice --amt={amount}"
        invoice_result = json.loads(run_command(invoice_cmd))
        payment_hash = invoice_result.get("r_hash", "")
        payment_request = invoice_result.get("payment_request", "")
        
        # Send payment from first hop through middle hop to final hop
        payment_cmd = f"docker exec {first_hop} lncli --network=regtest payinvoice --force --amt={amount} {payment_request}"
        payment_result = json.loads(run_command(payment_cmd))
        
        if "payment_error" in payment_result and payment_result["payment_error"]:
            print(f"  ❌ Circular rebalancing failed: {payment_result['payment_error']}")
            return False
        
        print(f"  ✅ Circular rebalancing successful!")
        stats["rebalance_operations"] += 1
        stats["rebalance_successes"] += 1
        return True
    except Exception as e:
        print(f"  ❌ Circular rebalancing error: {e}")
        return False

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
    """Check for rebalance suggestions from the ML model"""
    try:
        response = requests.get("http://localhost:5050/api/suggestions", timeout=1)  # Changed from 5000 to 5050
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Error getting rebalance suggestions: {e}")
    return []

def rebalance_channel(sender, receiver, amount):
    """Perform a rebalancing payment between two nodes"""
    if not sender or not receiver:
        print(f"  ❌ Invalid nodes for rebalancing: {sender} -> {receiver}")
        return False
        
    try:
        # Create an invoice on the receiver
        invoice_cmd = f"docker exec {receiver} lncli --network=regtest addinvoice --amt={amount} --memo=\"Rebalance\""
        invoice_result = json.loads(run_command(invoice_cmd))
        payment_request = invoice_result.get("payment_request", "")
        
        if not payment_request:
            print(f"  ❌ Failed to create invoice on {receiver}")
            return False
        
        # Pay the invoice from the sender
        payment_cmd = f"docker exec {sender} lncli --network=regtest payinvoice --force {payment_request}"
        payment_result = run_command(payment_cmd)
        
        if not payment_result:
            print(f"  ❌ Payment command failed")
            return False
            
        try:
            payment_json = json.loads(payment_result)
            if "payment_error" in payment_json and payment_json["payment_error"]:
                print(f"  ❌ Payment failed: {payment_json['payment_error']}")
                return False
                
            print(f"  ✅ Rebalancing successful!")
            stats["rebalance_operations"] += 1
            stats["rebalance_successes"] += 1
            
            # Log the rebalance transaction
            transaction = {
                "timestamp": datetime.now().isoformat(),
                "type": "rebalance",
                "sender": sender,
                "receiver": receiver,
                "amount": amount,
                "fee": 0,
                "route_length": 1,
                "success": True,
                "payment_hash": "",
                "description": f"Auto-recovery rebalance",
                "duration_ms": 0,
                "channel_before": "",
                "channel_after": ""
            }
            
            # Get channel state after rebalancing
            sender_channels = get_node_channels(sender)
            receiver_channels = get_node_channels(receiver)
            
            # Add to transaction log
            with open(CSV_OUTPUT, 'a', newline='') as csvfile:
                csv_writer = csv.writer(csvfile)
                csv_writer.writerow([
                    transaction["timestamp"],
                    transaction["type"],
                    transaction["sender"],
                    transaction["receiver"],
                    transaction["amount"],
                    transaction["fee"],
                    transaction["route_length"],
                    transaction["success"],
                    transaction["payment_hash"],
                    transaction["description"],
                    transaction["duration_ms"],
                    transaction["channel_before"],
                    transaction["channel_after"]
                ])
            
            # Send transaction data to HTTP API
            send_transaction_data(sender, receiver, amount, True)
            
            # Send updated channel states
            for node, channels_data in [(sender, sender_channels), (receiver, receiver_channels)]:
                if isinstance(channels_data, dict) and "channels" in channels_data:
                    for channel in channels_data["channels"]:
                        if isinstance(channel, dict):
                            remote_pubkey = channel.get("remote_pubkey", "")
                            capacity = int(channel.get("capacity", 0))
                            local_balance = int(channel.get("local_balance", 0))
                            if remote_pubkey and capacity > 0:
                                send_channel_state(node, remote_pubkey, capacity, local_balance)
            
            return True
        except json.JSONDecodeError:
            # Check if the output contains "SUCCEEDED"
            if "SUCCEEDED" in payment_result:
                print(f"  ✅ Rebalancing successful!")
                stats["rebalance_operations"] += 1
                stats["rebalance_successes"] += 1
                return True
            else:
                print(f"  ❌ Payment failed with non-JSON response")
                print(f"  Response: {payment_result[:100]}...")
                return False
    except Exception as e:
        print(f"  ❌ Rebalancing error: {e}")
        return False

def send_transaction_data(sender, receiver, amount, success):
    """Send transaction data to the HTTP API using the feature adapter"""
    data = {
        "event_type": "transaction",
        "timestamp": datetime.now().isoformat(),
        "sender": sender,
        "receiver": receiver,
        "amount": amount,
        "success": success,
        "transaction_type": "payment"  # Add transaction type
    }
    
    # Use the feature adapter
    try:
        # Use direct import or sys.path modification
        import sys
        import os
        
        # Get the current directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        
        # Add the parent directory to sys.path if needed
        if parent_dir not in sys.path:
            sys.path.append(parent_dir)
        
        # Now import the feature adapter
        import feature_adapter
        feature_adapter.send_to_server(data)
        print(f"  ✅ Transaction data sent via feature adapter")
    except Exception as e:
        print(f"  ⚠️ Error using feature adapter: {str(e)}")
        
        # Fallback to direct HTTP call
        try:
            response = requests.post("http://localhost:5050/api/update", json=data, timeout=1)  # Changed from 5000 to 5050
            if response.status_code == 200:
                print(f"  ✅ Transaction data sent directly to HTTP API")
            else:
                print(f"  ⚠️ HTTP API returned status code: {response.status_code}")
        except Exception as e:
            print(f"  ⚠️ Error sending transaction data to HTTP API: {str(e)}")

def send_channel_state(node, remote_pubkey, capacity, local_balance):
    """Send channel state data to the HTTP API using the feature adapter"""
    data = {
        "event_type": "channel_state",
        "node": node,
        "remote_pubkey": remote_pubkey,
        "capacity": capacity,
        "local_balance": local_balance,
        "remote_balance": capacity - local_balance,
        "timestamp": datetime.now().isoformat(),
        "channel_id": f"{node}_{remote_pubkey[:8]}",
        "balance_ratio": local_balance / capacity if capacity > 0 else 0.0
    }
    
    # Use the feature adapter
    try:
        # Use direct import or sys.path modification
        import sys
        import os
        
        # Get the current directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        
        # Add the parent directory to sys.path if needed
        if parent_dir not in sys.path:
            sys.path.append(parent_dir)
        
        # Now import the feature adapter
        import feature_adapter
        feature_adapter.send_to_server(data)
        print(f"  ✅ Channel state data sent via feature adapter")
    except Exception as e:
        print(f"  ⚠️ Error using feature adapter: {str(e)}")
        traceback.print_exc()  # Print the full stack trace
        
        # Fallback to direct HTTP call
        try:
            response = requests.post("http://localhost:5050/api/update", json=data, timeout=1)  # Changed from 5000 to 5050
            if response.status_code == 200:
                print(f"  ✅ Channel state data sent directly to HTTP API")
            else:
                print(f"  ⚠️ HTTP API returned status code: {response.status_code}")
        except Exception as e:
            print(f"  ⚠️ Error sending channel state data to HTTP API: {str(e)}")

def capture_network_snapshot():
    """Capture and send a complete snapshot of all channels in the network"""
    print("\nCapturing network snapshot...")
    
    for node in NODES:
        channels_data = get_node_channels(node)
        if not isinstance(channels_data, dict):
            continue
            
        channels = channels_data.get("channels", [])
        if not channels:
            continue
            
        for channel in channels:
            if not isinstance(channel, dict):
                continue
                
            remote_pubkey = channel.get("remote_pubkey", "")
            capacity = int(channel.get("capacity", 0))
            local_balance = int(channel.get("local_balance", 0))
            
            if remote_pubkey and capacity > 0:
                # Send detailed channel state
                send_channel_state(node, remote_pubkey, capacity, local_balance)
    
    print("Network snapshot complete")

def sum_channel_balances(channels_data):
    """Sum the local balances of all channels"""
    total = 0
    if isinstance(channels_data, dict):
        for channel_id, channel in channels_data.items():
            if isinstance(channel, dict):
                total += int(channel.get("local_balance", 0))
    return total

def check_node_health():
    """Check the health of all nodes and attempt recovery if needed"""
    print("\nPerforming node health check...")
    
    for node in NODES:
        print(f"Checking {node}...")
        
        # Check if node is responsive
        result = run_command(f"docker exec {node} lncli --network=regtest getinfo", timeout=5)
        
        if result is None:
            print(f"⚠️ {node} appears to be unresponsive. Attempting recovery...")
            
            # Try to unlock wallet using our new function
            if unlock_wallet(node):
                print(f"✅ {node} recovered successfully")
            else:
                print(f"❌ {node} is still unresponsive after recovery attempt")
                
                # Try restarting the node as a last resort
                print(f"Attempting to restart {node}...")
                subprocess.run(f"docker restart {node}", shell=True, timeout=30)
                print(f"Waiting for {node} to initialize...")
                time.sleep(15)
                
                # Try unlocking again after restart
                if unlock_wallet(node):
                    print(f"✅ {node} recovered successfully after restart")
                else:
                    print(f"❌ {node} is still unresponsive after restart")
        else:
            print(f"✅ {node} is healthy")
    
    print("Node health check complete")

def unlock_wallet(node):
    """Unlock a node's wallet using expect script"""
    print(f"🔑 Unlocking wallet for {node}...")
    
    # Create expect script - note the double curly braces for expect script
    unlock_cmd = f"""
    expect -c '
    set timeout 30
    spawn docker exec -it {node} lncli --network=regtest unlock
    expect "Input wallet password: "
    send "password\\r"
    expect {{
        "lnd successfully unlocked!" {{ exit 0 }}
        timeout {{ exit 1 }}
        eof {{ exit 2 }}
    }}
    '
    """
    
    # Run the unlock command
    result = subprocess.run(unlock_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # Wait for wallet to initialize
    print(f"Waiting for {node} to initialize after unlock...")
    time.sleep(10)
    
    # Verify wallet is unlocked
    verify_cmd = f"docker exec {node} lncli --network=regtest getinfo"
    verify_result = subprocess.run(verify_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if verify_result.returncode == 0:
        print(f"✅ {node} wallet successfully unlocked")
        return True
    else:
        print(f"❌ Failed to unlock {node} wallet: {verify_result.stderr}")
        return False

def keep_wallets_unlocked():
    """Proactively check and unlock all node wallets"""
    print("\nProactively checking wallet status...")
    
    for node in NODES:
        # Check if wallet is locked
        check_cmd = f"docker exec {node} lncli --network=regtest getinfo"
        result = subprocess.run(check_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if result.returncode != 0 and "wallet locked" in result.stderr:
            print(f"🔒 {node} wallet is locked. Unlocking...")
            unlock_wallet(node)
        else:
            print(f"✓ {node} wallet is already unlocked")
    
    print("Wallet check complete")

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
        
        # Add health check timer
        last_health_check = time.time()
        HEALTH_CHECK_INTERVAL = 300  # Check node health every 5 minutes
        
        # Add wallet unlock timer
        last_wallet_check = time.time()
        WALLET_CHECK_INTERVAL = 120  # Check wallets every 2 minutes
        
        # Initial wallet check
        keep_wallets_unlocked()
        
        while time.time() < end_time:
            try:
                # Check if we need regular rebalancing
                if REBALANCE_FREQUENCY > 0:
                    rebalance_count += 1
                    if rebalance_count >= REBALANCE_FREQUENCY:
                        rebalance_channels()
                        rebalance_count = 0
                
                # Check if it's time for a network snapshot
                current_time = time.time()
                if current_time - last_snapshot_time >= SNAPSHOT_INTERVAL:
                    capture_network_snapshot()
                    last_snapshot_time = current_time
                
                # Check if it's time for a node health check
                if current_time - last_health_check >= HEALTH_CHECK_INTERVAL:
                    check_node_health()
                    last_health_check = current_time
                
                # Check if it's time for a wallet check
                if current_time - last_wallet_check >= WALLET_CHECK_INTERVAL:
                    keep_wallets_unlocked()
                    last_wallet_check = current_time
                
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
                print("Detailed error information:")
                traceback.print_exc()
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