# Marketing assets

Source images that get re-used across marketing surfaces. Keep the
originals here; ship downsized / re-encoded copies wherever they're
consumed.

| File | Used by |
|---|---|
| `devto-bible-school-lms-cover.png` (1376×768) | The single DEV.to post Vadym wrote promoting biblie-school in April 2026. Source for the OpenGraph share-card at `frontend/public/og-image.jpg` (1200×630, q=85 JPEG, ~29 KB). |

If the cover changes, regenerate the OG card with a one-shot Pillow
script — JPEG at q=85 is the sweet spot for share previews:

```python
from PIL import Image
im = Image.open("docs/marketing/devto-bible-school-lms-cover.png").convert("RGB")
# Crop to 1.91:1 (OG ratio), then resize to 1200x630.
src_w, src_h = im.size
new_w = int(src_h * 1200 / 630)
x0 = (src_w - new_w) // 2
im.crop((x0, 0, x0 + new_w, src_h)).resize((1200, 630), Image.LANCZOS).save(
    "frontend/public/og-image.jpg",
    "JPEG", quality=85, optimize=True, progressive=True,
)
```
