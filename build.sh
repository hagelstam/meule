#!/bin/bash

set -e

echo "=== building filesystem ==="

echo "Building directory service..."
cd cmd/directory
go build -o ../../meule-directory .
cd ../..

echo "Building store service..."
cd cmd/store
go build -o ../../meule-store .
cd ../..

echo "✓ Build complete!"
echo "Executables created:"
echo "  - meule-directory"
echo "  - meule-store"

chmod +x setup_cluster.sh

echo ""
echo "Usage:"
echo "1. Run './build.sh' (this script) to build the binaries"
echo "2. Run './setup_cluster.sh' to start the cluster"
echo "3. In another terminal, run 'python3 run_cluster_test.py' to test the system"
