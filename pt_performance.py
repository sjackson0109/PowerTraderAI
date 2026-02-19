"""
PowerTrader AI Performance Monitoring Module
Advanced performance tracking, metrics collection, and optimisation tools.
"""

import time
import threading
import psutil
import logging
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque, defaultdict
from statistics import mean, median, stdev
import json

@dataclass
class PerformanceMetric:
    """Individual performance metric with statistical tracking."""
    name: str
    values: deque = field(default_factory=lambda: deque(maxlen=1000))
    timestamps: deque = field(default_factory=lambda: deque(maxlen=1000))
    unit: str = "ms"
    description: str = ""
    
    def add_value(self, value: float, timestamp: Optional[datetime] = None) -> None:
        """Add a new value to the metric."""
        if timestamp is None:
            timestamp = datetime.now()
        
        self.values.append(value)
        self.timestamps.append(timestamp)
    
    @property
    def latest(self) -> Optional[float]:
        """Get the most recent value."""
        return self.values[-1] if self.values else None
    
    @property
    def average(self) -> Optional[float]:
        """Get average value."""
        return mean(self.values) if self.values else None
    
    @property
    def median_value(self) -> Optional[float]:
        """Get median value."""
        return median(self.values) if self.values else None
    
    @property
    def std_deviation(self) -> Optional[float]:
        """Get standard deviation."""
        return stdev(self.values) if len(self.values) > 1 else None
    
    @property
    def min_value(self) -> Optional[float]:
        """Get minimum value."""
        return min(self.values) if self.values else None
    
    @property
    def max_value(self) -> Optional[float]:
        """Get maximum value."""
        return max(self.values) if self.values else None
    
    def get_recent_average(self, seconds: int = 60) -> Optional[float]:
        """Get average for recent time period."""
        cutoff_time = datetime.now() - timedelta(seconds=seconds)
        recent_values = [
            value for value, timestamp in zip(self.values, self.timestamps)
            if timestamp >= cutoff_time
        ]
        return mean(recent_values) if recent_values else None

@dataclass
class SystemMetrics:
    """System resource utilization metrics."""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_available_mb: float = 0.0
    disk_usage_percent: float = 0.0
    network_sent_mb: float = 0.0
    network_recv_mb: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

class PerformanceMonitor:
    """Advanced performance monitoring and metrics collection system."""
    
    def __init__(self, collection_interval: float = 1.0, enable_system_metrics: bool = True):
        """
        Initialize performance monitor.
        
        Args:
            collection_interval: How often to collect system metrics (seconds)
            enable_system_metrics: Whether to collect system resource metrics
        """
        self.collection_interval = collection_interval
        self.enable_system_metrics = enable_system_metrics
        self.logger = logging.getLogger(__name__)
        
        # Metrics storage
        self.metrics: Dict[str, PerformanceMetric] = {}
        self.system_metrics: deque = deque(maxlen=1000)
        self.operation_metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # Threading for background collection
        self._collection_thread: Optional[threading.Thread] = None
        self._stop_collection = threading.Event()
        self._lock = threading.RLock()
        
        # Performance counters
        self.counters: Dict[str, int] = defaultdict(int)
        self.timers: Dict[str, float] = {}
        
        # Initialize system metrics
        if self.enable_system_metrics:
            self.start_system_monitoring()
    
    def start_system_monitoring(self) -> None:
        """Start background system metrics collection."""
        if self._collection_thread and self._collection_thread.is_alive():
            return
        
        self._stop_collection.clear()
        self._collection_thread = threading.Thread(
            target=self._collect_system_metrics,
            daemon=True,
            name="PerformanceMonitor"
        )
        self._collection_thread.start()
        self.logger.info("Started system metrics collection")
    
    def stop_system_monitoring(self) -> None:
        """Stop background system metrics collection."""
        self._stop_collection.set()
        if self._collection_thread:
            self._collection_thread.join(timeout=2.0)
        self.logger.info("Stopped system metrics collection")
    
    def _collect_system_metrics(self) -> None:
        """Background thread function for collecting system metrics."""
        while not self._stop_collection.wait(self.collection_interval):
            try:
                # CPU and memory metrics
                cpu_percent = psutil.cpu_percent(interval=None)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                
                # Network metrics (if available)
                try:
                    network = psutil.net_io_counters()
                    network_sent = network.bytes_sent / (1024 * 1024)  # MB
                    network_recv = network.bytes_recv / (1024 * 1024)  # MB
                except:
                    network_sent = network_recv = 0.0
                
                metrics = SystemMetrics(
                    cpu_percent=cpu_percent,
                    memory_percent=memory.percent,
                    memory_used_mb=memory.used / (1024 * 1024),
                    memory_available_mb=memory.available / (1024 * 1024),
                    disk_usage_percent=disk.percent,
                    network_sent_mb=network_sent,
                    network_recv_mb=network_recv,
                    timestamp=datetime.now()
                )
                
                with self._lock:
                    self.system_metrics.append(metrics)
                
                # Update performance metrics
                self.add_metric_value("system.cpu_percent", cpu_percent, "%")
                self.add_metric_value("system.memory_percent", memory.percent, "%")
                self.add_metric_value("system.memory_used_mb", memory.used / (1024 * 1024), "MB")
                
            except Exception as e:
                self.logger.error(f"Error collecting system metrics: {e}")
    
    def add_metric(self, name: str, description: str = "", unit: str = "ms") -> None:
        """Add a new performance metric for tracking."""
        with self._lock:
            if name not in self.metrics:
                self.metrics[name] = PerformanceMetric(
                    name=name,
                    description=description,
                    unit=unit
                )
    
    def add_metric_value(self, name: str, value: float, unit: str = "ms", 
                        description: str = "") -> None:
        """Add a value to a performance metric."""
        with self._lock:
            if name not in self.metrics:
                self.add_metric(name, description, unit)
            
            self.metrics[name].add_value(value)
    
    def start_timer(self, operation: str) -> None:
        """Start timing an operation."""
        self.timers[operation] = time.time()
    
    def end_timer(self, operation: str) -> Optional[float]:
        """End timing an operation and record the duration."""
        if operation not in self.timers:
            return None
        
        duration = (time.time() - self.timers[operation]) * 1000  # Convert to ms
        del self.timers[operation]
        
        self.add_metric_value(f"operation.{operation}", duration, "ms", f"Duration of {operation}")
        
        with self._lock:
            self.operation_metrics[operation].append(duration)
        
        return duration
    
    def increment_counter(self, counter_name: str, amount: int = 1) -> None:
        """Increment a performance counter."""
        with self._lock:
            self.counters[counter_name] += amount
    
    def get_counter(self, counter_name: str) -> int:
        """Get current counter value."""
        with self._lock:
            return self.counters.get(counter_name, 0)
    
    def reset_counter(self, counter_name: str) -> None:
        """Reset a counter to zero."""
        with self._lock:
            self.counters[counter_name] = 0
    
    def get_metric_summary(self, metric_name: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive summary of a metric."""
        with self._lock:
            metric = self.metrics.get(metric_name)
            if not metric:
                return None
            
            return {
                "name": metric.name,
                "description": metric.description,
                "unit": metric.unit,
                "count": len(metric.values),
                "latest": metric.latest,
                "average": metric.average,
                "median": metric.median_value,
                "std_dev": metric.std_deviation,
                "min": metric.min_value,
                "max": metric.max_value,
                "recent_1m": metric.get_recent_average(60),
                "recent_5m": metric.get_recent_average(300)
            }
    
    def get_system_summary(self) -> Dict[str, Any]:
        """Get current system metrics summary."""
        with self._lock:
            if not self.system_metrics:
                return {}
            
            latest = self.system_metrics[-1]
            recent_cpu = [m.cpu_percent for m in list(self.system_metrics)[-10:]]
            recent_memory = [m.memory_percent for m in list(self.system_metrics)[-10:]]
            
            return {
                "timestamp": latest.timestamp.isoformat(),
                "cpu_percent": latest.cpu_percent,
                "memory_percent": latest.memory_percent,
                "memory_used_mb": latest.memory_used_mb,
                "memory_available_mb": latest.memory_available_mb,
                "disk_usage_percent": latest.disk_usage_percent,
                "network_sent_mb": latest.network_sent_mb,
                "network_recv_mb": latest.network_recv_mb,
                "cpu_average_10s": mean(recent_cpu) if recent_cpu else 0,
                "memory_average_10s": mean(recent_memory) if recent_memory else 0
            }
    
    def get_operation_summary(self, operation: str) -> Dict[str, Any]:
        """Get summary statistics for an operation."""
        with self._lock:
            values = list(self.operation_metrics.get(operation, []))
            
            if not values:
                return {"operation": operation, "count": 0}
            
            return {
                "operation": operation,
                "count": len(values),
                "latest_ms": values[-1] if values else 0,
                "average_ms": mean(values),
                "median_ms": median(values),
                "min_ms": min(values),
                "max_ms": max(values),
                "std_dev_ms": stdev(values) if len(values) > 1 else 0
            }
    
    def get_full_report(self) -> Dict[str, Any]:
        """Get comprehensive performance report."""
        with self._lock:
            report = {
                "timestamp": datetime.now().isoformat(),
                "system_metrics": self.get_system_summary(),
                "counters": dict(self.counters),
                "metrics": {
                    name: self.get_metric_summary(name) 
                    for name in self.metrics.keys()
                },
                "operations": {
                    op: self.get_operation_summary(op)
                    for op in self.operation_metrics.keys()
                }
            }
            
            return report
    
    def export_metrics(self, file_path: str) -> bool:
        """Export performance metrics to JSON file."""
        try:
            report = self.get_full_report()
            with open(file_path, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            return True
        except Exception as e:
            self.logger.error(f"Failed to export metrics: {e}")
            return False

class PerformanceProfiler:
    """Context manager for profiling code blocks and functions."""
    
    def __init__(self, monitor: PerformanceMonitor, operation_name: str, 
                 enable_logging: bool = True):
        self.monitor = monitor
        self.operation_name = operation_name
        self.enable_logging = enable_logging
        self.logger = logging.getLogger(__name__)
        self.start_time = None
        self.duration = None
    
    def __enter__(self):
        self.start_time = time.time()
        self.monitor.start_timer(self.operation_name)
        if self.enable_logging:
            self.logger.debug(f"Started profiling: {self.operation_name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration = self.monitor.end_timer(self.operation_name)
        
        if self.enable_logging:
            status = "completed" if exc_type is None else "failed"
            self.logger.debug(f"Profiling {status}: {self.operation_name} - {self.duration:.2f}ms")
        
        # Increment counter for this operation
        counter_name = f"operation.{self.operation_name}.count"
        self.monitor.increment_counter(counter_name)
        
        if exc_type is not None:
            error_counter = f"operation.{self.operation_name}.errors"
            self.monitor.increment_counter(error_counter)

# Decorator for automatic function profiling
def profile_performance(monitor: PerformanceMonitor, operation_name: str = None):
    """Decorator for automatic function performance profiling."""
    def decorator(func):
        nonlocal operation_name
        if operation_name is None:
            operation_name = f"{func.__module__}.{func.__name__}"
        
        def wrapper(*args, **kwargs):
            with PerformanceProfiler(monitor, operation_name):
                return func(*args, **kwargs)
        
        return wrapper
    return decorator

# Global performance monitor instance
performance_monitor = PerformanceMonitor()

# Cleanup function
def cleanup_performance_monitoring():
    """Clean up performance monitoring resources."""
    performance_monitor.stop_system_monitoring()