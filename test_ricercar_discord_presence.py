from ricercar_discord_presence import track_from_metadata


def test_track_from_mpris_metadata_unwraps_variants_like_values():
    track = track_from_metadata(
        {
            "xesam:title": "No Ordinary Love",
            "xesam:artist": ["Sade"],
            "xesam:album": "Love Deluxe",
            "mpris:artUrl": "https://example.test/cover.jpg",
            "xesam:url": "https://example.test/track",
            "mpris:length": 270_000_000,
        },
        12_000_000,
    )

    assert track.title == "No Ordinary Love"
    assert track.artist == "Sade"
    assert track.album == "Love Deluxe"
    assert track.art_url == "https://example.test/cover.jpg"
    assert track.track_url == "https://example.test/track"
    assert track.duration_us == 270_000_000
    assert track.position_us == 12_000_000


def test_missing_mpris_fields_have_useful_defaults():
    track = track_from_metadata({})

    assert track.title == "Unknown track"
    assert track.artist == "Unknown artist"
    assert track.album == ""
    assert track.art_url == ""
    assert track.track_url == ""