def access_decision(role: str, hour: int, emergency: bool) -> str:
    """Decide whether a role may enter at the given hour.

    Admin is always allowed. Staff may enter during an emergency, or during
    office hours without one. Guests get limited access in a shorter window.
    """
    if hour < 0 or hour > 23:
        raise ValueError("hour out of range")
    if role == "admin":
        return "allow"
    if emergency:
        if role == "staff":
            return "allow"
        return "deny"
    if role == "staff" and hour >= 9 and hour <= 18:
        return "allow"
    if role == "guest" and hour >= 10 and hour <= 16:
        return "limited"
    return "deny"
