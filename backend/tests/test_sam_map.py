import live


def test_payload_derives_each_room_map_from_its_source_frame():
    listing = {"id": "listing", "published": {}, "rooms": [
        {"id": "a", "source_frame": "f1"}, {"id": "b", "source_frame": "f2"},
        {"id": "c", "source_frame": "missing"},
    ], "frames": [
        {"id": "f1", "width": 100, "height": 100, "sam": {"structure": [
            {"concept": "window", "box": [10, 10, 30, 50]},
            {"concept": "door", "box": [70, 20, 90, 90]},
        ]}},
        {"id": "f2", "width": 200, "height": 100, "sam": {"structure": [
            {"concept": "window", "box": [80, 10, 120, 60]},
        ]}},
    ], "live": {"status": "ready", "rooms": [
        {"id": "a", "styles": {}}, {"id": "b", "styles": {}}, {"id": "c", "styles": {}},
    ]}}
    rooms = live.payload(listing)["rooms"]
    assert [(d["concept"], d["wall"], d["x_center"]) for d in rooms[0]["sam_map"]["detections"]] == [
        ("window", "left", 0.2), ("door", "right", 0.8)]
    assert rooms[1]["sam_map"]["detections"][0]["wall"] == "back"
    assert rooms[2]["sam_map"] is None
