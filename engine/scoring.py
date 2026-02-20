
def calculate_points(event_type: str, streak: int):
    base = {"Goal": 10, "Corner": 5, "Yellow Card": 3, "Nothing": 1}
    multiplier = 3 if event_type == "Goal" else 2 if event_type == "Corner" else 1
    return (base.get(event_type, 0) * multiplier) + (streak * 2)
