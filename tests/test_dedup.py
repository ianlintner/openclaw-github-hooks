from openclaw_github_hooks.dedup import DeliveryDedup


def test_first_delivery_is_new():
    d = DeliveryDedup()
    assert d.seen_before("abc-123") is False


def test_repeat_delivery_is_duplicate():
    d = DeliveryDedup()
    d.seen_before("abc-123")
    assert d.seen_before("abc-123") is True


def test_distinct_deliveries_are_new():
    d = DeliveryDedup()
    d.seen_before("abc-123")
    assert d.seen_before("def-456") is False


def test_capacity_eviction_keeps_working():
    d = DeliveryDedup(max_entries=10)
    for i in range(50):
        assert d.seen_before(f"id-{i}") is False
    # Most recent entry still remembered after evictions
    assert d.seen_before("id-49") is True
