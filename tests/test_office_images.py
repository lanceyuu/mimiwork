"""Image editing: transforms, annotation, composition — and never clobbering the original."""

import pytest

from coworker.agents.base import AgentContext
from coworker.roots import RootDir
from coworker.tools.office.image_tools import image_tools

Image = pytest.importorskip("PIL.Image", reason="Pillow is an optional [office] extra")


@pytest.fixture
def tools(tmp_path):
    ws = tmp_path / "scratch"
    ws.mkdir()
    context = AgentContext(workspace=ws, roots=[RootDir(path=ws, writable=True)])
    return {t.__name__: t for t in image_tools(context)}, ws


def _png(path, size=(400, 200), color="blue", mode="RGB"):
    Image.new(mode, size, color).save(path)
    return path


# -- inspection -----------------------------------------------------------------


def test_info_reports_dimensions_and_format(tools):
    api, ws = tools
    _png(ws / "a.png", size=(400, 200))

    info = api["read_image_info"]("a.png")
    assert info["width"] == 400
    assert info["height"] == 200
    assert info["format"] == "PNG"
    assert info["aspect_ratio"] == 2.0
    assert info["bytes"] > 0


def test_info_flags_transparency(tools):
    api, ws = tools
    _png(ws / "a.png", mode="RGBA", color=(0, 0, 255, 128))
    assert api["read_image_info"]("a.png")["has_transparency"] is True


def test_info_on_a_non_image_errors_cleanly(tools):
    api, ws = tools
    (ws / "notanimage.png").write_text("nope")
    assert "error" in api["read_image_info"]("notanimage.png")


# -- transforms -----------------------------------------------------------------


def test_resize_to_an_explicit_size(tools):
    api, ws = tools
    _png(ws / "a.png", size=(400, 200))

    result = api["edit_image"]("a.png", "out.png", width=200, height=100)
    assert "error" not in result, result
    assert result["size"] == "200x100"
    assert Image.open(ws / "out.png").size == (200, 100)


def test_resize_by_width_preserves_aspect_ratio(tools):
    api, ws = tools
    _png(ws / "a.png", size=(400, 200))

    api["edit_image"]("a.png", "out.png", width=100)
    assert Image.open(ws / "out.png").size == (100, 50)


def test_max_width_shrinks_but_never_enlarges(tools):
    api, ws = tools
    _png(ws / "small.png", size=(100, 50))

    api["edit_image"]("small.png", "out.png", max_width=800)
    assert Image.open(ws / "out.png").size == (100, 50)


def test_the_original_is_never_modified(tools):
    """A destructive default would turn one wrong argument into lost work."""
    api, ws = tools
    _png(ws / "original.png", size=(400, 200))

    api["edit_image"]("original.png", "resized.png", width=50)
    assert Image.open(ws / "original.png").size == (400, 200)


def test_crop_extracts_the_requested_region(tools):
    api, ws = tools
    _png(ws / "a.png", size=(400, 200))

    api["edit_image"]("a.png", "out.png", crop=[0, 0, 100, 100])
    assert Image.open(ws / "out.png").size == (100, 100)


def test_crop_beyond_the_edge_is_clamped_not_rejected(tools):
    api, ws = tools
    _png(ws / "a.png", size=(400, 200))

    result = api["edit_image"]("a.png", "out.png", crop=[0, 0, 9999, 9999])
    assert "error" not in result, result
    assert Image.open(ws / "out.png").size == (400, 200)


def test_an_inverted_crop_box_is_refused(tools):
    api, ws = tools
    _png(ws / "a.png")
    assert "error" in api["edit_image"]("a.png", "out.png", crop=[300, 300, 10, 10])


def test_rotation_expands_the_canvas(tools):
    api, ws = tools
    _png(ws / "a.png", size=(400, 200))

    api["edit_image"]("a.png", "out.png", rotate=90)
    assert Image.open(ws / "out.png").size == (200, 400)


def test_flip_and_grayscale_apply(tools):
    api, ws = tools
    _png(ws / "a.png")

    result = api["edit_image"]("a.png", "out.png", flip="horizontal", grayscale=True)
    assert "error" not in result, result
    assert Image.open(ws / "out.png").mode == "L"


def test_an_unknown_flip_direction_is_refused(tools):
    api, ws = tools
    _png(ws / "a.png")
    assert "error" in api["edit_image"]("a.png", "out.png", flip="diagonal")


def test_format_conversion_follows_the_output_extension(tools):
    api, ws = tools
    _png(ws / "a.png")

    api["edit_image"]("a.png", "out.jpg")
    assert Image.open(ws / "out.jpg").format == "JPEG"


def test_transparent_png_converts_to_jpeg_without_failing(tools):
    """RGBA → JPEG raises deep inside Pillow unless the alpha is flattened first."""
    api, ws = tools
    _png(ws / "a.png", mode="RGBA", color=(255, 0, 0, 128))

    result = api["edit_image"]("a.png", "out.jpg")
    assert "error" not in result, result
    assert (ws / "out.jpg").is_file()


def test_lower_quality_produces_a_smaller_file(tools):
    api, ws = tools
    # Noise, so the JPEG encoder has something to trade away.
    import random

    image = Image.new("RGB", (300, 300))
    random.seed(0)
    image.putdata([(random.randint(0, 255),) * 3 for _ in range(300 * 300)])
    image.save(ws / "a.png")

    big = api["edit_image"]("a.png", "big.jpg", quality=95)
    small = api["edit_image"]("a.png", "small.jpg", quality=20)
    assert small["bytes"] < big["bytes"]


def test_an_absurd_resize_is_refused_rather_than_exhausting_memory(tools):
    api, ws = tools
    _png(ws / "a.png")
    assert "error" in api["edit_image"]("a.png", "out.png", width=50_000, height=50_000)


def test_writing_outside_the_workspace_is_refused(tools):
    api, ws = tools
    _png(ws / "a.png")
    result = api["edit_image"]("a.png", "/tmp/escape.png", width=10)
    assert "error" in result and "escapes" in result["error"]


# -- annotation -----------------------------------------------------------------


def test_annotation_changes_pixels_and_keeps_the_size(tools):
    api, ws = tools
    _png(ws / "shot.png", size=(400, 200), color="white")

    result = api["annotate_image"](
        "shot.png",
        "marked.png",
        [{"type": "box", "box": [10, 10, 200, 100], "color": "red", "text": "Look here"}],
    )
    assert "error" not in result, result
    assert result["annotations_drawn"] == 1
    assert Image.open(ws / "marked.png").size == (400, 200)
    # Something was actually drawn.
    assert (
        Image.open(ws / "marked.png").convert("RGB").tobytes()
        != Image.open(ws / "shot.png").convert("RGB").tobytes()
    )


def test_every_annotation_type_draws(tools):
    api, ws = tools
    _png(ws / "shot.png", size=(400, 300), color="white")

    result = api["annotate_image"](
        "shot.png",
        "marked.png",
        [
            {"type": "box", "box": [5, 5, 100, 60]},
            {"type": "arrow", "from": [10, 200], "to": [150, 120]},
            {"type": "line", "from": [0, 250], "to": [300, 250]},
            {"type": "text", "at": [200, 20], "text": "Peak"},
            {"type": "highlight", "box": [200, 100, 350, 160]},
        ],
    )
    assert "error" not in result, result
    assert result["annotations_drawn"] == 5


def test_a_highlight_leaves_content_visible_underneath(tools):
    """A solid fill would hide exactly the thing being highlighted."""
    api, ws = tools
    Image.new("RGB", (200, 100), "black").save(ws / "dark.png")

    api["annotate_image"]("dark.png", "out.png", [{"type": "highlight", "box": [0, 0, 200, 100]}])
    pixel = Image.open(ws / "out.png").convert("RGB").getpixel((100, 50))
    assert pixel != (255, 224, 102)  # not fully painted over
    assert pixel != (0, 0, 0)  # but visibly tinted


def test_unknown_annotation_type_is_reported(tools):
    api, ws = tools
    _png(ws / "a.png")
    result = api["annotate_image"]("a.png", "out.png", [{"type": "sparkle"}])
    assert "error" in result and "sparkle" in result["error"]


def test_a_malformed_box_is_reported(tools):
    api, ws = tools
    _png(ws / "a.png")
    assert "error" in api["annotate_image"]("a.png", "out.png", [{"type": "box", "box": [1, 2]}])


def test_empty_annotations_are_refused(tools):
    api, ws = tools
    _png(ws / "a.png")
    assert "error" in api["annotate_image"]("a.png", "out.png", [])


# -- composition ----------------------------------------------------------------


def test_horizontal_combine_places_images_side_by_side(tools):
    api, ws = tools
    _png(ws / "a.png", size=(100, 100), color="red")
    _png(ws / "b.png", size=(100, 100), color="blue")

    result = api["combine_images"](["a.png", "b.png"], "pair.png", spacing=10)
    assert "error" not in result, result
    assert result["size"] == "210x100"
    assert result["combined"] == 2


def test_vertical_combine_stacks(tools):
    api, ws = tools
    _png(ws / "a.png", size=(100, 100))
    _png(ws / "b.png", size=(100, 100))

    assert api["combine_images"](["a.png", "b.png"], "out.png", layout="vertical", spacing=0)[
        "size"
    ] == "100x200"


def test_grid_layout_wraps_by_columns(tools):
    api, ws = tools
    for name in "abcd":
        _png(ws / f"{name}.png", size=(50, 50))

    result = api["combine_images"](
        [f"{n}.png" for n in "abcd"], "grid.png", layout="grid", columns=2, spacing=0
    )
    assert result["size"] == "100x100"


def test_mixed_sizes_are_centred_in_a_uniform_cell(tools):
    api, ws = tools
    _png(ws / "big.png", size=(200, 100))
    _png(ws / "small.png", size=(50, 50))

    result = api["combine_images"](["big.png", "small.png"], "out.png", spacing=0)
    assert result["size"] == "400x100"  # two cells of the largest width


def test_combining_needs_at_least_two_images(tools):
    api, ws = tools
    _png(ws / "a.png")
    assert "error" in api["combine_images"](["a.png"], "out.png")


def test_a_missing_source_is_reported(tools):
    api, ws = tools
    _png(ws / "a.png")
    assert "error" in api["combine_images"](["a.png", "gone.png"], "out.png")


def test_unknown_layout_is_reported(tools):
    api, ws = tools
    _png(ws / "a.png")
    _png(ws / "b.png")
    assert "error" in api["combine_images"](["a.png", "b.png"], "out.png", layout="spiral")
