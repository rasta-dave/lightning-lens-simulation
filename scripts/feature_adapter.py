#!/usr/bin/env python3
"""
Feature Adapter for Lightning Network Data

This script transforms raw Lightning Network data into features
expected by the ML model.
"""

import json
import sys
import requests
import datetime
from datetime import datetime
import traceback

# Configuration
HTTP_SERVER_URL = "http://localhost:5050/api/update"
DEBUG = True  # Set to False in production

def adapt_channel_state(channel_data):
    """
    Adapt channel state data to ensure it has all required fields
    
    Args:
        channel_data: The channel data dictionary
        
    Returns:
        Modified channel data with additional fields
    """
    # Create a new dictionary with only the expected features
    adapted_data = {
        "event_type": channel_data.get("event_type", "channel_state"),
        "timestamp": channel_data.get("timestamp", datetime.now().isoformat()),
        "node": channel_data.get("node", ""),
        "remote_pubkey": channel_data.get("remote_pubkey", ""),
        "capacity": channel_data.get("capacity", 1000000),
        "local_balance": channel_data.get("local_balance", 500000),
        "remote_balance": channel_data.get("remote_balance", 500000),
        "avg_amount": 1000,  # Default value
        "success_rate": 0.9,  # Default value
    }
    
    # Calculate balance_ratio if not present
    if 'balance_ratio' not in channel_data:
        try:
            capacity = float(adapted_data['capacity'])
            if capacity > 0:
                adapted_data['balance_ratio'] = float(adapted_data['local_balance']) / capacity
            else:
                adapted_data['balance_ratio'] = 0.0
        except (ValueError, TypeError):
            adapted_data['balance_ratio'] = 0.0
    else:
        adapted_data['balance_ratio'] = channel_data['balance_ratio']
    
    # Create channel_id if not present
    if 'channel_id' not in channel_data:
        adapted_data['channel_id'] = f"{adapted_data['node']}_{adapted_data['remote_pubkey'][:8]}"
    else:
        adapted_data['channel_id'] = channel_data['channel_id']
    
    return adapted_data

def adapt_transaction_data(transaction_data):
    """
    Adapt transaction data to ensure it has all required fields
    
    Args:
        transaction_data: The transaction data dictionary
        
    Returns:
        Modified transaction data with additional fields
    """
    # Create a new dictionary with only the expected features
    adapted_data = {
        "event_type": transaction_data.get("event_type", "transaction"),
        "timestamp": transaction_data.get("timestamp", datetime.now().isoformat()),
        "sender": transaction_data.get("sender", ""),
        "receiver": transaction_data.get("receiver", ""),
        "amount": transaction_data.get("amount", 0),
        "success": transaction_data.get("success", True),
        "capacity": 1000000,  # Default value
        "local_balance": 500000,  # Default value
        "remote_balance": 500000,  # Default value
        "avg_amount": 1000,  # Default value
        "success_rate": 0.9,  # Default value
    }
    
    return adapted_data

def send_to_server(data):
    """
    Send adapted data to the HTTP server
    
    Args:
        data: The data dictionary to send
    """
    # Adapt data based on event type
    if data.get('event_type') == 'channel_state':
        adapted_data = adapt_channel_state(data)
    elif data.get('event_type') == 'transaction':
        adapted_data = adapt_transaction_data(data)
    else:
        adapted_data = data  # No adaptation for unknown event types
    
    # Print the adapted data for debugging
    print(f"Sending data to HTTP server: {json.dumps(adapted_data)[:200]}...")
    
    # Send to server
    try:
        response = requests.post(HTTP_SERVER_URL, json=adapted_data, timeout=2)
        if response.status_code == 200:
            print(f"✅ Data sent successfully to HTTP server")
        else:
            print(f"⚠️ HTTP server returned status code: {response.status_code}")
            print(f"Response: {response.text[:200]}...")
    except Exception as e:
        print(f"❌ Error sending data to HTTP server: {str(e)}")

if __name__ == "__main__":
    # Check if data was provided as command line argument
    if len(sys.argv) > 1:
        try:
            # Parse the JSON data from command line
            data = json.loads(sys.argv[1])
            
            if DEBUG:
                print(f"Original data: {json.dumps(data)[:200]}...")
                
                # Show what the adapted data would look like
                if data.get('event_type') == 'channel_state':
                    adapted = adapt_channel_state(data)
                    print(f"Adapted channel state: {json.dumps(adapted)[:200]}...")
                elif data.get('event_type') == 'transaction':
                    adapted = adapt_transaction_data(data)
                    print(f"Adapted transaction: {json.dumps(adapted)[:200]}...")
            
            send_to_server(data)
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON data: {sys.argv[1][:100]}...")
        except Exception as e:
            print(f"❌ Error processing data: {str(e)}")
            traceback.print_exc()
    else:
        print("No data provided. Usage: python feature_adapter.py '{\"event_type\": \"channel_state\", ...}'") 