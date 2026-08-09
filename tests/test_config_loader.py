import pytest
from ails_intel.config_loader import parse_active_config

def test_parses_types():
    rows = [
        ["config_key","config_value","value_type","active"],
        ["n","3","number","TRUE"],
        ["b","TRUE","boolean","TRUE"],
        ["j",'{"a":1}',"json","TRUE"],
        ["off","x","string","FALSE"],
    ]
    cfg = parse_active_config(rows)
    assert cfg["n"].value == 3.0
    assert cfg["b"].value is True
    assert cfg["j"].value == {"a":1}
    assert "off" not in cfg

def test_duplicate_active_rejected():
    rows = [
        ["config_key","config_value","value_type","active"],
        ["x","1","number","TRUE"],
        ["x","2","number","TRUE"],
    ]
    with pytest.raises(ValueError):
        parse_active_config(rows)
