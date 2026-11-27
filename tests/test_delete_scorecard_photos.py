"""Nov 25 2026 (Dhruvika: deleted the 28 Jun 2026 scorecard; uploading it again said "This looks like the same photo
as '5d4be7f92d.jpeg'"): deleting a scorecard deletes all its photos, except a photo another scorecard still uses."""

from app import main


def test_every_photo_of_a_deleted_scorecard_is_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)
    for name in ("card.jpg", "page2.jpg", "older.jpg", "shared.jpg"):
        (tmp_path / name).write_bytes(b"x")
    gone = {"id": "a1", "file_path": str(tmp_path / "card.jpg"), "file_name": "card.jpg", "second_photo_file": "page2.jpg",
            "earlier_second_photos": [{"second_photo_file": "older.jpg"}, {"second_photo_file": "shared.jpg"}]}
    other = {"id": "b2", "file_name": "other.jpg", "second_photo_file": "shared.jpg"}
    removed = main._delete_upload_photos({"archive_uploads": [gone, other]}, gone)
    assert sorted(removed) == ["card.jpg", "older.jpg", "page2.jpg"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["shared.jpg"]


def test_windows_style_paths_are_matched(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)
    (tmp_path / "a.jpg").write_bytes(b"x")
    upload = {"id": "a1", "file_path": "C:\\data\\uploads\\a.jpg"}
    assert main._delete_upload_photos({"archive_uploads": [upload]}, upload) == ["a.jpg"]
