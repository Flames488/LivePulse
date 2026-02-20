
from prediction_engine import calculate_points

def test_goal_points():
    assert calculate_points("Goal", "Goal") > 0
