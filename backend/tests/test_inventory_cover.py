import db
import listings


def test_inventory_prefers_staged_cover_and_falls_back(client):
    listing = listings.new_listing("cover-test", source="upload", facts={}, uploads=[], status="draft")
    listing["frames"] = [{"id": "frame"}]
    listing["rooms"] = [{"source_frame": "frame", "before": "before.jpg", "after": "after.jpg"}]
    with db.connect() as conn:
        db.insert_listing(conn, listing)

    def cover():
        return next(item["cover"] for item in client.get("/api/listings").json() if item["id"] == "cover-test")

    assert cover() == "after.jpg"
    listing["rooms"][0]["after"] = None
    db.save_listing(listing)
    assert cover() == "before.jpg"
