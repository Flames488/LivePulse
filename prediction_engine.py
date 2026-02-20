
def calculate_points(event_type, prediction, streak=0):
    multipliers = {"Goal": 3, "Corner": 2, "Yellow Card": 1}
    if prediction == event_type:
        base = 10 * multipliers.get(event_type, 1)
        bonus = streak * 2
        return base + bonus
    return 0
