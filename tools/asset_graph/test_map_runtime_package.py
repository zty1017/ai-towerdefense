from tools.asset_graph import map_runtime_package


def test_derived_build_slots_are_distributed_along_full_route():
    grid = {"width_cells": 16, "height_cells": 9}
    routes = [
        {
            "route_id": "route_main",
            "waypoints": [
                {"x": 15, "y": 4},
                {"x": 11, "y": 4},
                {"x": 11, "y": 2},
                {"x": 6, "y": 2},
                {"x": 6, "y": 6},
                {"x": 1, "y": 6},
            ],
        }
    ]
    objectives = {
        "core_target": {"position": {"x": 0, "y": 6}},
        "optional_targets": [{"position": {"x": 4, "y": 2}}],
    }

    slots = map_runtime_package._derive_build_slots(grid, routes, objectives)
    x_positions = [slot["position"]["x"] for slot in slots]

    assert 6 <= len(slots) <= 10
    assert min(x_positions) <= 5
    assert max(x_positions) >= 12
    assert len({(slot["position"]["x"], slot["position"]["y"]) for slot in slots}) == len(slots)
    assert all(slot["position"] not in routes[0]["waypoints"] for slot in slots)
