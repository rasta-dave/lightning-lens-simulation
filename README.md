# Lightning Network Testnet

A Docker-based Lightning Network testnet for development and testing.

## Overview

This project sets up a local Lightning Network testnet with:

- 1 Bitcoin node (regtest mode)
- 5 Lightning Network nodes (Alice, Bob, Carol, Dave, Eve)
- Automated channel setup and funding
- Simulation tools for testing and analysis

## Getting Started

### Prerequisites

- Docker and Docker Compose
- jq (for JSON processing)
- Python 3.6+ (for simulation scripts)

## Real-Time ML Integration

The Lightning Network simulation supports real-time integration with machine learning models through a WebSocket server.

### Setup

1. Install required dependencies:

   ```bash
   pip install websockets requests flask
   ```

2. Start the WebSocket server:

   ```bash
   python scripts/websocket_server.py
   ```

3. Run the simulation with ML integration:

   ```bash
   python scripts/simulate_network.py
   ```

4. Connect your ML model to receive real-time updates and provide rebalancing suggestions.

### How It Works

- The WebSocket server provides a real-time data stream of channel states and transactions
- ML models can connect to `ws://localhost:6789` to receive updates
- Models can send rebalancing suggestions back through the same connection
- The simulation will check for and apply ML-suggested rebalancing operations

### Data Format

The WebSocket server sends JSON messages with the following structure:

```json
{
  "type": "transaction",
  "data": {
    "sender": "lnd-alice",
    "receiver": "lnd-bob",
    "amount": 1000,
    "success": true,
    "description": "Coffee purchase"
  }
}
```

For channel updates:

```json
{
  "type": "channel_update",
  "data": {
    "lnd-alice": [
      {
        "remote_pubkey": "02b115e8f3...",
        "capacity": 1000000,
        "local_balance": 590000,
        "remote_balance": 406530
      }
    ]
  }
}
```

ML models can send rebalancing suggestions in this format:

```json
{
  "type": "rebalance_suggestion",
  "suggestion": {
    "from_node": "lnd-alice",
    "to_node": "lnd-bob",
    "amount": 200000,
    "confidence": 0.85
  }
}
```

### Setup

1. Start the network:

   ```bash
   docker-compose up -d
   ```

2. Initialize the network:

   ```bash
   sudo ./setup-nodes.sh
   ```

3. If needed, unlock the wallets:
   ```bash
   sudo ./unlock-wallets.sh
   ```

## Testing and Simulation

### Basic Testing

Run the basic test script to verify node connectivity:

```bash
sudo ./test-lightning.sh
```

### Channel Rebalancing

The `rebalance-channels.sh` script is provided as a utility for:

- **Initial setup**: Creating a baseline balanced state before starting experiments
- **Development testing**: Quickly fixing severely imbalanced channels during development
- **Benchmark comparison**: Providing a reference point for comparing ML-based rebalancing strategies

```bash
sudo ./scripts/rebalance-channels.sh
```

**Note for ML model development**: If you're developing an ML model to optimize channel liquidity, you may want to:

1. Use this script only for initial setup or between experiments
2. Modify the simulation script to disable automatic rebalancing
3. Let your ML model observe natural imbalances and propose its own rebalancing strategies

### Network Simulation

Run the simulation script to generate realistic payment patterns:

```bash
sudo ./scripts/simulate_network.py
```

The simulation will:

- Create random payments between nodes
- Log transaction data to a CSV file
- Display real-time statistics
- Periodically rebalance channels (can be disabled for ML model development)

#### For ML Model Development

If you're developing an ML model to optimize channel liquidity:

1. Edit `scripts/simulate_network.py` and set `REBALANCE_FREQUENCY = 0` to disable automatic rebalancing
2. Let your ML model observe the channel states as they evolve naturally
3. Have your model propose rebalancing actions based on its learning
4. Compare your model's performance against the baseline rebalancing script

### Cleanup and Reset

The cleanup script allows you to reset your Lightning Network testnet to a clean state. Use it when:

- You want to start fresh with new channels and balances
- You encounter issues with channel states or node connectivity
- You've completed a simulation and want to reset for a new experiment
- Your channels have become too imbalanced for effective testing

To reset the network:

```bash
sudo ./cleanup.sh
```

This script will:

1. Stop all Docker containers
2. Remove all data directories (bitcoin-data, lnd-\*-data)
3. Reset all channel states and balances
4. Optionally back up your simulation data

**Note:** Running this script will delete all channel information and wallet data. Make sure to save any important simulation results before running it.

After cleanup, you'll need to run the setup process again:

```bash
docker-compose up -d
sudo ./setup-nodes.sh
```

## Data Analysis

The simulation generates a CSV file (`lightning_simulation_data.csv`) with detailed transaction data, including:

- Timestamps
- Sender and receiver nodes
- Payment amounts and fees
- Success/failure status
- Route information
- Transaction duration

This data can be used for:

- Analyzing payment patterns
- Optimizing channel liquidity
- Training AI models for routing optimization
- Visualizing network activity

### Data Persistence

Simulation data is stored in the CSV file and is not affected by the cleanup script. If you want to preserve multiple simulation runs, consider renaming or moving the CSV file before running a new simulation:

```bash
# Save simulation results before cleanup
mv lightning_simulation_data.csv simulation_run1_$(date +%Y%m%d).csv
```

## Network Structure

```
Alice ---- Bob ---- Carol
  |         |         |
  |         |         |
 Eve ------ | ----- Dave
```

Each node has channels with its neighbors, allowing for multi-hop payments across the network.

## Troubleshooting

If you encounter issues with your Lightning Network testnet:

1. **Check node status**:

   ```bash
   docker exec lnd-alice lncli --network=regtest getinfo
   ```

2. **View logs for errors**:

   ```bash
   docker logs lnd-alice
   ```

3. **Restart specific nodes**:

   ```bash
   docker restart lnd-alice
   ```

4. **If all else fails**, use the cleanup script and set up again:
   ```bash
   sudo ./cleanup.sh
   docker-compose up -d
   sudo ./setup-nodes.sh
   ```

## License

[Your License Here]
