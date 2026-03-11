import time
import random
from prometheus_client import start_http_server, Gauge, Counter, Histogram

# Define some sample Prometheus metrics
REQUEST_COUNT = Counter('fake_requests_total', 'Total number of requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('fake_request_latency_seconds', 'Request latency in seconds', ['method', 'endpoint'])
CPU_USAGE = Gauge('fake_cpu_usage_percent', 'Current CPU usage percentage')
MEMORY_USAGE = Gauge('fake_memory_usage_bytes', 'Current memory usage in bytes')
ACTIVE_SESSIONS = Gauge('fake_active_sessions', 'Number of active user sessions')
ERROR_COUNT = Counter('fake_errors_total', 'Total number of errors', ['type'])

def generate_metrics():
    """Simulate dynamically changing metrics over time"""
    print("Simulating metrics generation... Press Ctrl+C to stop.")
    
    endpoints = ['/api/v1/users', '/api/v1/products', '/api/v1/auth', '/api/v1/checkout']
    methods = ['GET', 'POST', 'PUT', 'DELETE']
    
    while True:
        # 1. Simulate API Traffic
        endpoint = random.choice(endpoints)
        method = random.choice(methods)
        
        # Mostly 200s, some 400s/500s
        status_roll = random.random()
        if status_roll > 0.95:
            status = '500'
        elif status_roll > 0.85:
            status = '400'
        else:
            status = '200'
            
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
        
        # 2. Record simulated latency (higher latency for 500s)
        base_latency = random.uniform(0.01, 0.3)
        if status == '500':
            base_latency += random.uniform(1.0, 3.0)
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(base_latency)
        
        # 3. Update system resources gauges
        CPU_USAGE.set(random.uniform(15.0, 95.0))
        # Memory between 500MB and 4GB
        MEMORY_USAGE.set(random.uniform(500 * 1024 * 1024, 4000 * 1024 * 1024))
        
        # 4. Update active sessions (fluctuates up and down)
        current_sessions = max(0, int(ACTIVE_SESSIONS._value.get() + random.randint(-5, 5)))
        if current_sessions == 0:
            current_sessions = random.randint(10, 50) # reset if it drops to 0
        ACTIVE_SESSIONS.set(current_sessions)
        
        # 5. Occasional system errors
        if random.random() < 0.1:
            error_types = ['db_timeout', 'cache_miss', 'api_rate_limit', 'auth_failure']
            ERROR_COUNT.labels(type=random.choice(error_types)).inc()

        # Update every 2 to 5 seconds
        time.sleep(random.uniform(2.0, 5.0))

if __name__ == '__main__':
    # Start the Prometheus HTTP server
    PORT = 8001
    print(f"Starting fake Prometheus endpoint on port {PORT}...")
    print(f"View metrics at: http://localhost:{PORT}/metrics")
    
    start_http_server(PORT)
    
    try:
        generate_metrics()
    except KeyboardInterrupt:
        print("\nStopping fake endpoint.")
# host.docker.internal:8001