def shipping_fee(weight: float, region: str, member: bool) -> float:
    """Return the shipping fee in yuan.

    Remote, local, and other regions use different base fees. Weight above
    10 kg adds 2 yuan per extra kilogram. Members pay 90 percent.
    """
    if weight <= 0:
        raise ValueError("weight must be positive")
    if region == "remote":
        base = 20.0
    elif region == "local":
        base = 8.0
    else:
        base = 12.0
    if weight > 10:
        extra = (weight - 10) * 2
    else:
        extra = 0.0
    fee = base + extra
    if member:
        fee = round(fee * 0.9, 2)
    else:
        fee = round(float(fee), 2)
    return fee
