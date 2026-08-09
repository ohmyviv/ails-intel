from ails_intel.fingerprint import frozen_manifest_fingerprint, EMPTY_SHA256

def test_empty():
    assert frozen_manifest_fingerprint([]) == EMPTY_SHA256

def test_stable_order():
    a = [
        {"item_index":2,"event_key_v11":"e2","title":"t2","primary_url":"u2"},
        {"item_index":1,"event_key_v11":"e1","title":"t1","primary_url":"u1"},
    ]
    b = list(reversed(a))
    assert frozen_manifest_fingerprint(a) == frozen_manifest_fingerprint(b)

def test_content_change_changes_hash():
    a = [{"item_index":1,"event_key_v11":"e","title":"t","primary_url":"u"}]
    b = [{"item_index":1,"event_key_v11":"e","title":"t2","primary_url":"u"}]
    assert frozen_manifest_fingerprint(a) != frozen_manifest_fingerprint(b)
