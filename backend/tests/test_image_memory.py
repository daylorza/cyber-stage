from PIL import Image

import meta_client


def test_large_jpeg_is_downsampled_before_rgb_conversion(tmp_path, monkeypatch):
    path = tmp_path / "large.jpg"
    Image.new("RGB", (4000, 3000)).save(path)
    original_convert = Image.Image.convert
    decoded_sizes = []

    def record_convert(image, *args, **kwargs):
        decoded_sizes.append(image.size)
        return original_convert(image, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "convert", record_convert)
    image, width, height = meta_client._load_scaled(path, 1024)
    assert (width, height) == (4000, 3000)
    assert max(image.size) <= 1024
    assert decoded_sizes[0][0] <= 2000
