import pytest
from subjects.access_control import access_decision

def test_iter0_1_access_decision():
    assert access_decision('admin', 0, False) == 'allow'

def test_iter1_1_access_decision():
    assert access_decision('guest', 10, False) == 'limited'

def test_iter2_1_access_decision():
    assert access_decision('staff', 0, True) == 'allow'

def test_iter3_1_access_decision():
    with pytest.raises(ValueError):
        access_decision('other', -1, False)

def test_iter4_1_access_decision():
    assert access_decision('other', 0, True) == 'deny'

def test_iter5_1_access_decision():
    assert access_decision('staff', 9, False) == 'allow'

def test_iter6_1_access_decision():
    assert access_decision('other', 0, False) == 'deny'
