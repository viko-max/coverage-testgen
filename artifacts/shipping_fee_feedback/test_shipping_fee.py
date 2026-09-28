import pytest
from subjects.shipping import shipping_fee

def test_iter0_1_shipping_fee():
    assert shipping_fee(1, 'remote', False) == 20.0

def test_iter1_1_shipping_fee():
    assert shipping_fee(11, 'local', True) == 9.0

def test_iter2_1_shipping_fee():
    with pytest.raises(ValueError):
        shipping_fee(0, 'other', False)

def test_iter3_1_shipping_fee():
    assert shipping_fee(11, 'other', True) == 12.6
