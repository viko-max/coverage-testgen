import pytest
from subjects.shipping import shipping_fee

def test_iter0_1_shipping_fee():
    assert shipping_fee(1, 'remote', False) == 20.0

def test_iter1_1_shipping_fee():
    with pytest.raises(ValueError):
        shipping_fee(0, 'other', False)

def test_iter2_1_shipping_fee():
    assert shipping_fee(1, 'remote', True) == 18.0

def test_iter3_1_shipping_fee():
    assert shipping_fee(11, 'remote', False) == 22.0

def test_iter4_1_shipping_fee():
    assert shipping_fee(11, 'remote', True) == 19.8

def test_iter5_1_shipping_fee():
    assert shipping_fee(1, 'local', False) == 8.0

def test_iter6_1_shipping_fee():
    assert shipping_fee(1, 'local', True) == 7.2

def test_iter7_1_shipping_fee():
    assert shipping_fee(1, 'other', False) == 12.0
