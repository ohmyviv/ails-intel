from ails_intel.signal_keys import make_signal_key, make_signal_id, make_coverage_id

def test_signal_key_deterministic_and_url_query_ignored():
    a=make_signal_key("SRC-1","", "https://EXAMPLE.org/a/?utm=x"," Title  Here ","2026-08-09")
    b=make_signal_key("SRC-1","", "https://example.org/a","title here","2026-08-09")
    assert a == b

def test_signal_id_format():
    key=make_signal_key("SRC","ID","","T","2026-08-09")
    sid=make_signal_id("20260809",key)
    assert sid.startswith("SIG-20260809-")
    assert len(sid.split("-")[-1]) == 12

def test_coverage_id_deterministic():
    assert make_coverage_id("r","p","","C5","route","s") == make_coverage_id("r","p","","C5","route","s")
