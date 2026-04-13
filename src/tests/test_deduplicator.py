import pytest
import redis
from unittest.mock import MagicMock
from src.ingestion.deduplicator import RedisDeduplicator

@pytest.fixture
def mock_redis():
    """Mock the Redis client and its Bloom Filter operations."""
    class MockBfCommand:
        def __init__(self):
            # A simple set to mimic Bloom Filter storage conceptually
            self.store = set()
            self.reserved = set()

        def reserve(self, key, error_rate, capacity):
            if key in self.reserved:
                raise redis.exceptions.ResponseError("ERR item exists")
            self.reserved.add(key)
            return True

        def add(self, key, item):
            full_key = f"{key}:{item}"
            if full_key in self.store:
                return 0
            self.store.add(full_key)
            return 1
            
    client = MagicMock(spec=redis.Redis)
    client.bf = MagicMock(return_value=MockBfCommand())
    
    client.exists.side_effect = lambda key: key in client.bf().reserved
    return client

def test_bloom_filter_happy_path(mock_redis):
    # Setup
    dedup = RedisDeduplicator(redis_client=mock_redis)
    tenant_id = "tenant_xyz"
    trace_id = "trace-1234"
    item1 = "https://example.com/article/1"
    item2 = "https://example.com/article/2"

    # Given an valid input
    # When injected it indicates it's new
    assert dedup.is_new_item(item1, tenant_id, trace_id) is True
    
    # And duplicate is rejected
    assert dedup.is_new_item(item1, tenant_id, trace_id) is False
    
    # And a different input is accepted
    assert dedup.is_new_item(item2, tenant_id, trace_id) is True

def test_bloom_filter_tenant_isolation(mock_redis):
    dedup = RedisDeduplicator(redis_client=mock_redis)
    item = "https://example.com/article/1"
    
    # Different tenants, same item
    assert dedup.is_new_item(item, "Tenant_A", "t-001") is True
    assert dedup.is_new_item(item, "Tenant_B", "t-002") is True
    
    # Tenant A again should fail
    assert dedup.is_new_item(item, "Tenant_A", "t-003") is False

def test_bloom_filter_redis_down_triggers_dlq():
    # Setup failing redis client
    mock_failing_redis = MagicMock(spec=redis.Redis)
    error = redis.exceptions.ConnectionError("Connection refused")
    mock_failing_redis.bf.side_effect = error
    
    # mock DLQ callback
    dlq_triggered = False
    
    def my_dlq_callback(item, tenant_id, trace_id, _exc):
        nonlocal dlq_triggered
        dlq_triggered = True
        
    dedup = RedisDeduplicator(
        redis_client=mock_failing_redis, 
        dlq_callback=my_dlq_callback
    )
    
    # Execution
    is_new = dedup.is_new_item("https://example.com/broken", "Tenant_C", "t-004")
    
    # Validation
    assert dlq_triggered is True
    assert is_new is False

def test_bloom_filter_redis_down_fallback():
    # Setup failing redis client WITH NO DLQ (fail-open)
    mock_failing_redis = MagicMock(spec=redis.Redis)
    error = redis.exceptions.ConnectionError("Connection refused")
    mock_failing_redis.bf.side_effect = error
    
    dedup = RedisDeduplicator(redis_client=mock_failing_redis, dlq_callback=None)
    
    # Let it pass so pipeline doesn't choke completely
    is_new = dedup.is_new_item("https://example.com/broken", "Tenant_C", "t-005")
    assert is_new is True
