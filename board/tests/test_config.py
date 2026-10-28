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


def test_parse_hotkey():
    from taskviewer_board.config import parse_hotkey

    assert parse_hotkey("ctrl+alt+t") == (0x3, ord("T"))
    assert parse_hotkey("Ctrl+Alt+Shift+T") == (0x7, ord("T"))
    assert parse_hotkey("win+f12") == (0x8, 0x7B)
    assert parse_hotkey("ctrl+5") == (0x2, ord("5"))
    for bad in ("t", "ctrl+", "hyper+t", "ctrl+ctrl+t", "ctrl+f25", "ctrl+space"):
        assert parse_hotkey(bad) is None, bad


def test_hotkey_keys_load(tmp_path, capsys):
    p = tmp_path / "board.toml"
    p.write_text('hotkey_toggle = "win+alt+b"\nhotkey_collapse = "nope"\n')
    cfg = load(p)
    assert cfg.hotkey_toggle == "win+alt+b"
    assert cfg.hotkey_collapse == Config().hotkey_collapse
    assert "bad hotkey_collapse" in capsys.readouterr().err


def test_app_state_dir_loads(tmp_path):
    p = tmp_path / "board.toml"
    p.write_text("app_state_dir = '\\\\wsl.localhost\\Ubuntu\\home\\me\\.local\\state\\taskviewer'\n")
    assert load(p).app_state_dir == r"\\wsl.localhost\Ubuntu\home\me\.local\state\taskviewer"
    assert Config().app_state_dir == ""
