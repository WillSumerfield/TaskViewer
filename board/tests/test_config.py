from taskviewer_board.config import Config, load, pick_output, place

RECT = (100, 0, 1000, 800)  # x, y, w, h
SIZE = (300, 200)


def write(tmp_path, text):
    p = tmp_path / "board.toml"
    p.write_text(text)
    return p


def test_missing_file_gives_defaults(tmp_path):
    assert load(tmp_path / "nope.toml") == Config()


def test_overrides(tmp_path):
    cfg = load(write(tmp_path, 'monitor = "DP-0"\ncorner = "bottom-left"\noffset = [4, 6]\nwidth = 400\n'
                               "max_height = 0.5\nopacity = 1\nfont_size = 12\n"))
    assert cfg == Config("DP-0", "bottom-left", (4, 6), 400, 0.5, 1.0, 12)


def test_bad_values_fall_back(tmp_path, capsys):
    cfg = load(write(tmp_path, 'corner = "middle"\nwidth = "wide"\nopacity = 2\nbogus = 1\nfont_size = 14\n'))
    assert cfg == Config(font_size=14)
    err = capsys.readouterr().err
    assert "corner" in err and "width" in err and "opacity" in err and "bogus" in err


def test_broken_toml_gives_defaults(tmp_path):
    assert load(write(tmp_path, "width = = 3")) == Config()


def test_place_corners():
    at = lambda corner: place(RECT, SIZE, Config(corner=corner, offset=(8, 10)))
    assert at("top-left") == (108, 10)
    assert at("top-right") == (100 + 1000 - 300 - 8, 10)
    assert at("bottom-left") == (108, 800 - 200 - 10)
    assert at("bottom-right") == (792, 590)
    assert at("center") == (450, 300)


def test_pick_output():
    outs = {"DP-0": RECT, "HDMI-0": RECT}
    assert pick_output("DP-0", outs, "HDMI-0") == "DP-0"
    assert pick_output("DP-9", outs, "HDMI-0") == "HDMI-0"  # unplugged → focused
    assert pick_output("focused", outs, "HDMI-0") == "HDMI-0"
