import pytest
import time
import psutil
import threading
from memory_profiler import profile

class TestPerformance:
    """Performance and load testing"""
    
    def test_memory_usage_baseline(self):
        """Test baseline memory usage"""
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Simulate some work
        data = [i for i in range(10000)]
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        # Should not increase memory by more than 50MB for basic operations
        assert memory_increase < 50, f"Memory increased by {memory_increase}MB"
    
    @pytest.mark.benchmark(group="api_calls")
    def test_api_call_performance(self, benchmark):
        """Benchmark API call performance"""
        def mock_api_call():
            # Simulate API processing time
            time.sleep(0.1)
            return {'status': 'success', 'data': [1, 2, 3]}
        
        result = benchmark(mock_api_call)
        assert result['status'] == 'success'
    
    @pytest.mark.benchmark(group="data_processing")
    def test_data_processing_speed(self, benchmark):
        """Benchmark data processing performance"""
        def process_market_data():
            # Simulate market data processing
            data = list(range(1000))
            processed = [x * 1.02 for x in data if x % 2 == 0]
            return len(processed)
        
        result = benchmark(process_market_data)
        assert result == 500
    
    def test_concurrent_operations(self):
        """Test system under concurrent load"""
        results = []
        
        def worker_task(task_id):
            # Simulate trading operation
            time.sleep(0.05)
            results.append(f"Task {task_id} completed")
        
        threads = []
        start_time = time.time()
        
        # Create 10 concurrent workers
        for i in range(10):
            thread = threading.Thread(target=worker_task, args=(i,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        end_time = time.time()
        
        assert len(results) == 10
        assert end_time - start_time < 1.0  # Should complete within 1 second
    
    def test_cpu_usage_under_load(self):
        """Test CPU usage during intensive operations"""
        initial_cpu = psutil.cpu_percent(interval=0.1)
        
        # Simulate CPU-intensive task
        start_time = time.time()
        while time.time() - start_time < 0.5:
            _ = [x**2 for x in range(1000)]
        
        peak_cpu = psutil.cpu_percent(interval=0.1)
        
        # CPU usage should be reasonable (less than 90%)
        assert peak_cpu < 90, f"CPU usage too high: {peak_cpu}%"