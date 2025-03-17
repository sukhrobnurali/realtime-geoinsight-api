#!/usr/bin/env python3
"""
Performance benchmark script for GeoInsight API.
"""

import asyncio
import aiohttp
import time
import json
import random
import statistics
from dataclasses import dataclass
from typing import List, Dict, Any
import argparse
import sys


@dataclass
class BenchmarkResult:
    """Benchmark result data."""
    operation: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_response_time: float
    min_response_time: float
    max_response_time: float
    p95_response_time: float
    p99_response_time: float
    requests_per_second: float
    error_rate: float
    errors: List[str]


class GeoInsightBenchmark:
    """Benchmark suite for GeoInsight API."""
    
    def __init__(self, base_url: str, api_key: str, concurrent_users: int = 10):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.concurrent_users = concurrent_users
        self.session = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            headers={
                'X-API-Key': self.api_key,
                'Content-Type': 'application/json'
            },
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def make_request(self, method: str, path: str, data: Dict = None) -> Dict:
        """Make a single API request and measure response time."""
        start_time = time.time()
        error = None
        status_code = 0
        
        try:
            url = f"{self.base_url}{path}"
            
            if method.upper() == 'GET':
                async with self.session.get(url, params=data) as response:
                    status_code = response.status
                    result = await response.json()
            elif method.upper() == 'POST':
                async with self.session.post(url, json=data) as response:
                    status_code = response.status
                    result = await response.json()
            elif method.upper() == 'PUT':
                async with self.session.put(url, json=data) as response:
                    status_code = response.status
                    result = await response.json()
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
                
        except Exception as e:
            error = str(e)
            result = {}
            
        end_time = time.time()
        response_time = end_time - start_time
        
        return {
            'response_time': response_time,
            'status_code': status_code,
            'error': error,
            'success': status_code == 200 and error is None,
            'result': result
        }
    
    async def benchmark_device_creation(self, num_requests: int = 100) -> BenchmarkResult:
        """Benchmark device creation endpoint."""
        print(f"Benchmarking device creation ({num_requests} requests)...")
        
        async def create_device():
            device_data = {
                'device_name': f'Benchmark Device {random.randint(1000, 9999)}',
                'device_type': random.choice(['smartphone', 'tablet', 'tracker']),
                'metadata': {
                    'benchmark': True,
                    'timestamp': time.time()
                }
            }
            return await self.make_request('POST', '/api/v1/devices', device_data)
        
        return await self._run_benchmark('device_creation', create_device, num_requests)
    
    async def benchmark_location_updates(self, num_requests: int = 1000) -> BenchmarkResult:
        """Benchmark location update endpoint."""
        print(f"Benchmarking location updates ({num_requests} requests)...")
        
        # Create a test device first
        device_data = {
            'device_name': 'Benchmark Location Device',
            'device_type': 'smartphone',
            'metadata': {'benchmark': True}
        }
        
        device_result = await self.make_request('POST', '/api/v1/devices', device_data)
        if not device_result['success']:
            raise Exception("Failed to create test device for location updates")
        
        device_id = device_result['result']['id']
        
        async def update_location():
            location_data = {
                'latitude': 52.520008 + random.uniform(-0.01, 0.01),
                'longitude': 13.404954 + random.uniform(-0.01, 0.01),
                'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'accuracy': random.uniform(1.0, 10.0),
                'speed': random.uniform(0, 50),
                'heading': random.uniform(0, 360)
            }
            return await self.make_request('PUT', f'/api/v1/devices/{device_id}/location', location_data)
        
        return await self._run_benchmark('location_updates', update_location, num_requests)
    
    async def benchmark_nearby_search(self, num_requests: int = 500) -> BenchmarkResult:
        """Benchmark nearby device search endpoint."""
        print(f"Benchmarking nearby search ({num_requests} requests)...")
        
        async def search_nearby():
            params = {
                'latitude': 52.520008 + random.uniform(-0.05, 0.05),
                'longitude': 13.404954 + random.uniform(-0.05, 0.05),
                'radius_meters': random.randint(500, 5000)
            }
            return await self.make_request('GET', '/api/v1/devices/nearby', params)
        
        return await self._run_benchmark('nearby_search', search_nearby, num_requests)
    
    async def benchmark_geofence_creation(self, num_requests: int = 200) -> BenchmarkResult:
        """Benchmark geofence creation endpoint."""
        print(f"Benchmarking geofence creation ({num_requests} requests)...")
        
        async def create_geofence():
            center_lat = 52.520008 + random.uniform(-0.1, 0.1)
            center_lng = 13.404954 + random.uniform(-0.1, 0.1)
            size = random.uniform(0.01, 0.05)
            
            geofence_data = {
                'name': f'Benchmark Geofence {random.randint(1000, 9999)}',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[
                        [center_lng - size, center_lat - size],
                        [center_lng - size, center_lat + size],
                        [center_lng + size, center_lat + size],
                        [center_lng + size, center_lat - size],
                        [center_lng - size, center_lat - size]
                    ]]
                },
                'trigger_type': random.choice(['enter', 'exit', 'both']),
                'metadata': {'benchmark': True}
            }
            return await self.make_request('POST', '/api/v1/geofences', geofence_data)
        
        return await self._run_benchmark('geofence_creation', create_geofence, num_requests)
    
    async def benchmark_route_optimization(self, num_requests: int = 100) -> BenchmarkResult:
        """Benchmark route optimization endpoint."""
        print(f"Benchmarking route optimization ({num_requests} requests)...")
        
        async def optimize_route():
            # Generate random waypoints around Berlin
            waypoints = []
            for _ in range(random.randint(3, 8)):
                waypoints.append({
                    'latitude': 52.520008 + random.uniform(-0.05, 0.05),
                    'longitude': 13.404954 + random.uniform(-0.05, 0.05)
                })
            
            route_data = {
                'start_location': waypoints[0],
                'end_location': waypoints[-1],
                'waypoints': waypoints[1:-1],
                'optimization_type': random.choice(['shortest_time', 'shortest_distance']),
                'constraints': {
                    'max_distance_km': 50,
                    'vehicle_type': 'car'
                }
            }
            return await self.make_request('POST', '/api/v1/routes/optimize', route_data)
        
        return await self._run_benchmark('route_optimization', optimize_route, num_requests)
    
    async def benchmark_recommendations(self, num_requests: int = 300) -> BenchmarkResult:
        """Benchmark location recommendations endpoint."""
        print(f"Benchmarking recommendations ({num_requests} requests)...")
        
        async def get_recommendations():
            request_data = {
                'latitude': 52.520008 + random.uniform(-0.02, 0.02),
                'longitude': 13.404954 + random.uniform(-0.02, 0.02),
                'radius_km': random.randint(1, 5),
                'categories': random.choice([
                    ['restaurant'],
                    ['hotel'],
                    ['shopping'],
                    ['tourist_attraction'],
                    ['restaurant', 'shopping']
                ]),
                'limit': random.randint(10, 50)
            }
            return await self.make_request('POST', '/api/v1/recommendations/nearby', request_data)
        
        return await self._run_benchmark('recommendations', get_recommendations, num_requests)
    
    async def _run_benchmark(self, operation: str, request_func, num_requests: int) -> BenchmarkResult:
        """Run a benchmark for a specific operation."""
        start_time = time.time()
        
        # Create semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(self.concurrent_users)
        
        async def limited_request():
            async with semaphore:
                return await request_func()
        
        # Execute all requests concurrently
        tasks = [limited_request() for _ in range(num_requests)]
        results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        total_duration = end_time - start_time
        
        # Process results
        response_times = []
        successful_requests = 0
        failed_requests = 0
        errors = []
        
        for result in results:
            response_times.append(result['response_time'])
            if result['success']:
                successful_requests += 1
            else:
                failed_requests += 1
                if result['error']:
                    errors.append(result['error'])
        
        # Calculate statistics
        avg_response_time = statistics.mean(response_times)
        min_response_time = min(response_times)
        max_response_time = max(response_times)
        
        sorted_times = sorted(response_times)
        p95_response_time = sorted_times[int(0.95 * len(sorted_times))]
        p99_response_time = sorted_times[int(0.99 * len(sorted_times))]
        
        requests_per_second = num_requests / total_duration
        error_rate = failed_requests / num_requests
        
        return BenchmarkResult(
            operation=operation,
            total_requests=num_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            avg_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            p95_response_time=p95_response_time,
            p99_response_time=p99_response_time,
            requests_per_second=requests_per_second,
            error_rate=error_rate,
            errors=list(set(errors))  # Remove duplicates
        )
    
    async def run_full_benchmark(self) -> Dict[str, BenchmarkResult]:
        """Run complete benchmark suite."""
        print("Starting GeoInsight API Benchmark Suite")
        print("=" * 50)
        
        results = {}
        
        # Run individual benchmarks
        benchmarks = [
            ('device_creation', self.benchmark_device_creation, 100),
            ('location_updates', self.benchmark_location_updates, 1000),
            ('nearby_search', self.benchmark_nearby_search, 500),
            ('geofence_creation', self.benchmark_geofence_creation, 200),
            ('route_optimization', self.benchmark_route_optimization, 100),
            ('recommendations', self.benchmark_recommendations, 300),
        ]
        
        for name, benchmark_func, num_requests in benchmarks:
            try:
                result = await benchmark_func(num_requests)
                results[name] = result
                print(f"✓ {name} completed")
            except Exception as e:
                print(f"✗ {name} failed: {str(e)}")
                results[name] = None
        
        return results
    
    def generate_report(self, results: Dict[str, BenchmarkResult]) -> str:
        """Generate a comprehensive benchmark report."""
        report = []
        report.append("GeoInsight API Benchmark Report")
        report.append("=" * 50)
        report.append(f"Test Configuration:")
        report.append(f"  - Base URL: {self.base_url}")
        report.append(f"  - Concurrent Users: {self.concurrent_users}")
        report.append(f"  - Test Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        for operation, result in results.items():
            if result is None:
                report.append(f"{operation.replace('_', ' ').title()}: FAILED")
                continue
                
            report.append(f"{operation.replace('_', ' ').title()}:")
            report.append(f"  Total Requests: {result.total_requests}")
            report.append(f"  Successful: {result.successful_requests}")
            report.append(f"  Failed: {result.failed_requests}")
            report.append(f"  Error Rate: {result.error_rate:.2%}")
            report.append(f"  Requests/Second: {result.requests_per_second:.2f}")
            report.append(f"  Response Times (ms):")
            report.append(f"    - Average: {result.avg_response_time * 1000:.2f}")
            report.append(f"    - Min: {result.min_response_time * 1000:.2f}")
            report.append(f"    - Max: {result.max_response_time * 1000:.2f}")
            report.append(f"    - 95th Percentile: {result.p95_response_time * 1000:.2f}")
            report.append(f"    - 99th Percentile: {result.p99_response_time * 1000:.2f}")
            
            if result.errors:
                report.append(f"  Errors:")
                for error in result.errors[:5]:  # Show first 5 errors
                    report.append(f"    - {error}")
                if len(result.errors) > 5:
                    report.append(f"    ... and {len(result.errors) - 5} more")
            
            report.append("")
        
        # Summary
        total_requests = sum(r.total_requests for r in results.values() if r)
        total_successful = sum(r.successful_requests for r in results.values() if r)
        total_failed = sum(r.failed_requests for r in results.values() if r)
        overall_error_rate = total_failed / total_requests if total_requests > 0 else 0
        
        report.append("Overall Summary:")
        report.append(f"  Total Requests: {total_requests}")
        report.append(f"  Successful: {total_successful}")
        report.append(f"  Failed: {total_failed}")
        report.append(f"  Overall Error Rate: {overall_error_rate:.2%}")
        
        return "\n".join(report)
    
    def export_results(self, results: Dict[str, BenchmarkResult], filename: str):
        """Export results to JSON file."""
        exportable_results = {}
        
        for operation, result in results.items():
            if result is None:
                exportable_results[operation] = None
                continue
                
            exportable_results[operation] = {
                'operation': result.operation,
                'total_requests': result.total_requests,
                'successful_requests': result.successful_requests,
                'failed_requests': result.failed_requests,
                'avg_response_time': result.avg_response_time,
                'min_response_time': result.min_response_time,
                'max_response_time': result.max_response_time,
                'p95_response_time': result.p95_response_time,
                'p99_response_time': result.p99_response_time,
                'requests_per_second': result.requests_per_second,
                'error_rate': result.error_rate,
                'errors': result.errors
            }
        
        with open(filename, 'w') as f:
            json.dump(exportable_results, f, indent=2)
        
        print(f"Results exported to {filename}")


async def main():
    """Main benchmark execution."""
    parser = argparse.ArgumentParser(description='GeoInsight API Benchmark Tool')
    parser.add_argument('--url', required=True, help='Base URL of the API')
    parser.add_argument('--api-key', required=True, help='API key for authentication')
    parser.add_argument('--concurrent-users', type=int, default=10, help='Number of concurrent users')
    parser.add_argument('--operation', help='Specific operation to benchmark')
    parser.add_argument('--requests', type=int, default=100, help='Number of requests for single operation')
    parser.add_argument('--export', help='Export results to JSON file')
    parser.add_argument('--report', help='Save report to text file')
    
    args = parser.parse_args()
    
    try:
        async with GeoInsightBenchmark(args.url, args.api_key, args.concurrent_users) as benchmark:
            if args.operation:
                # Run specific operation
                operation_map = {
                    'device_creation': benchmark.benchmark_device_creation,
                    'location_updates': benchmark.benchmark_location_updates,
                    'nearby_search': benchmark.benchmark_nearby_search,
                    'geofence_creation': benchmark.benchmark_geofence_creation,
                    'route_optimization': benchmark.benchmark_route_optimization,
                    'recommendations': benchmark.benchmark_recommendations,
                }
                
                if args.operation not in operation_map:
                    print(f"Unknown operation: {args.operation}")
                    print(f"Available operations: {list(operation_map.keys())}")
                    return
                
                print(f"Running {args.operation} benchmark...")
                result = await operation_map[args.operation](args.requests)
                results = {args.operation: result}
            else:
                # Run full benchmark suite
                results = await benchmark.run_full_benchmark()
            
            # Generate and display report
            report = benchmark.generate_report(results)
            print("\n" + report)
            
            # Export results if requested
            if args.export:
                benchmark.export_results(results, args.export)
            
            # Save report if requested
            if args.report:
                with open(args.report, 'w') as f:
                    f.write(report)
                print(f"Report saved to {args.report}")
    
    except Exception as e:
        print(f"Benchmark failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())