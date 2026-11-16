#!/usr/bin/env python3

import requests
import json
import time
import random
import string
import sys
import uuid
from typing import Dict, List, Optional


class MeuleClient:
    def __init__(self, directory_urls: List[str]):
        self.directory_urls = directory_urls
        self.session = requests.Session()

    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make request to directory cluster with failover"""
        last_exception = None

        for url in self.directory_urls:
            try:
                full_url = f"{url}{endpoint}"
                response = self.session.request(method, full_url, timeout=30, **kwargs)
                return response
            except requests.exceptions.RequestException as e:
                last_exception = e
                continue

        raise last_exception or Exception("All directory nodes failed")

    def get_cluster_status(self) -> Dict:
        """Get cluster status"""
        response = self._make_request("GET", "/api/v1/status")
        response.raise_for_status()
        return response.json()

    def assign_write_locations(self, file_id: str, file_size: int) -> Dict:
        """Assign write locations for a file"""
        data = {"file_id": file_id, "file_size": file_size}
        response = self._make_request(
            "POST", "/api/v1/files/write-locations", json=data
        )
        response.raise_for_status()
        return response.json()

    def get_read_locations(self, file_id: str) -> Dict:
        """Get read locations for a file"""
        response = self._make_request("GET", f"/api/v1/files/{file_id}/read-locations")
        response.raise_for_status()
        return response.json()

    def write_file_to_store(
        self, store_address: str, logical_volume_id: str, file_id: str, data: bytes
    ) -> bool:
        """Write file to a specific store"""
        try:
            file_response = requests.post(
                f"http://{store_address}/api/v1/{logical_volume_id}/{file_id}/create_file",
                data=data,
                headers={"Content-Type": "application/octet-stream"},
                timeout=30,
            )

            if file_response.status_code == 200:
                return True
            else:
                print(
                    f"Failed to write to store {store_address}: {file_response.status_code} - {file_response.text}"
                )
                return False

        except Exception as e:
            print(f"Error writing to store {store_address}: {e}")
            return False

    def read_file_from_store(
        self, store_address: str, logical_volume_id: str, file_id: str
    ) -> Optional[bytes]:
        """Read file from a specific store"""
        try:
            response = requests.get(
                f"http://{store_address}/api/v1/{logical_volume_id}/{file_id}/read_file",
                timeout=30,
            )

            if response.status_code == 200:
                return response.content
            else:
                print(
                    f"Failed to read from store {store_address}: {response.status_code}"
                )
                return None

        except Exception as e:
            print(f"Error reading from store {store_address}: {e}")
            return None


def generate_random_data(size: int) -> bytes:
    """Generate random data of specified size"""
    return "".join(
        random.choices(string.ascii_letters + string.digits, k=size)
    ).encode()


def test_comprehensive(client: MeuleClient):
    print("\n=== Testing comprehensive test ===")
    n = 1000

    try:
        files = {}

        print(f"creating {n} files")
        successful_writes = 0
        for i in range(0, n):
            file_id = str(uuid.uuid4())
            test_data = generate_random_data(1024)
            write_locations = client.assign_write_locations(file_id, len(test_data))

            logical_volume_id = write_locations.get("logical_volume_id")
            files[file_id] = (logical_volume_id, test_data)
            locations = write_locations.get("locations", [])

            if not logical_volume_id:
                print("✗ No logical volume ID returned from directory")
                return False

            if not locations:
                print("✗ No write locations available")
                return False

            print(f"Directory assigned logical volume: {logical_volume_id}")
            print(f"Write locations count: {len(locations)}")

            for i, location in enumerate(locations):
                store_address = location.get("store_address")
                if store_address:
                    print(f"Writing to store {i+1}/{len(locations)}: {store_address}")
                    success = client.write_file_to_store(
                        store_address, logical_volume_id, file_id, test_data
                    )
                    if success:
                        successful_writes += 1
                        print(f"  ✓ Successfully wrote to {store_address}")
                    else:
                        print(f"  ✗ Failed to write to {store_address}")

        successful_reads = 0
        for file_id, (logical_volume_id, test_data) in files.items():
            read_locations = client.get_read_locations(file_id)
            print(
                f"Directory returned read locations: {json.dumps(read_locations, indent=2)}"
            )

            for i, location in enumerate(read_locations.get("locations", [])):
                store_address = location.get("store_address")
                if store_address:
                    print(f"Reading from store {i+1}: {store_address}")
                    read_data = client.read_file_from_store(
                        store_address, logical_volume_id, file_id
                    )

                    if read_data is not None:
                        if read_data == test_data:
                            successful_reads += 1
                            print(f"  ✓ Data verified from {store_address}")
                        else:
                            print(
                                f"  ✗ Data mismatch from {store_address} (expected {len(test_data)} bytes, got {len(read_data)} bytes)"
                            )
                    else:
                        print(f"  ✗ Failed to read from {store_address}")
        print(f"successful reads ({successful_reads}/{len(files)*3})")
        print(f"successful writes ({successful_writes}/{len(files)*3})")

        return successful_reads == successful_writes == n * 3

    except Exception as e:
        print(f"comprehensive test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Main test function"""
    print("Meule Distributed File System Test")
    print("=" * 50)

    directory_urls = [
        "http://127.0.0.1:8001",
        "http://127.0.0.1:8002",
        "http://127.0.0.1:8003",
    ]

    client = MeuleClient(directory_urls)

    print("Waiting for cluster to be ready...")
    max_retries = 30
    for i in range(max_retries):
        try:
            status = client.get_cluster_status()
            if status.get("is_leader") or status.get("leader_addr"):
                print("✓ Cluster is ready")
                break
        except Exception as e:
            if i == max_retries - 1:
                print(f"✗ Cluster not ready after {max_retries} attempts: {e}")
                return 1
            time.sleep(2)

    if test_comprehensive(client):
        print("passed comprehensive test")
        return 0
    else:
        print("failed comprehensive test")
        return 1


if __name__ == "__main__":
    sys.exit(main())
