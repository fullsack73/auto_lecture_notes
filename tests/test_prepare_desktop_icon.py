import importlib.util
from pathlib import Path

from PIL import Image


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "prepare_desktop_icon.py"
SPEC = importlib.util.spec_from_file_location("prepare_desktop_icon", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_prepare_desktop_icon_creates_square_png(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    destination = tmp_path / "icon.png"
    Image.new("RGB", (700, 500), "red").save(source)

    MODULE.prepare(source, destination, 512)

    with Image.open(destination) as icon:
        assert icon.size == (512, 512)
        assert icon.mode == "RGBA"
