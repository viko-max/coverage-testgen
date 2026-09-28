import pytest
from subjects.shipping import shipping_fee

def test_shipping_fee():
    assert shipping_fee(5.0, "remote", False) == 20.0
    assert shipping_fee(5.0, "remote", True) == pytest.approx(18.0)
    assert shipping_fee(5.0, "local", False) == 8.0
    assert shipping_fee(5.0, "local", True) == pytest.approx(7.2)
    assert shipping_fee(5.0, "other", False) == 12.0
    assert shipping_fee(5.0, "other", True) == pytest.approx(10.8)
    assert shipping_fee(15.0, "local", False) == 22.0
    assert shipping_fee(15.0, "local", True) == pytest.approx(19.8)
    assert shipping_fee(10.0, "remote", False) == 20.0
    assert shipping_fee(10.0, "remote", True) == pytest.approx(18.0)
    with pytest.raises(ValueError):
        shipping_fee(0, "local", False)
    with pytest.raises(ValueError):
        shipping_fee(-1.0, "local", False)
