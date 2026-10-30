"""Secondary text contrast against the dashboard's declared dark surfaces."""
from pathlib import Path
import re
import unittest

CSS = Path(__file__).resolve().parents[1] / 'dashboard/styles.css'
SECONDARY_TEXT = (
    '.nav-label', '.nav-heading > span', '.project-button .project-tasks',
    '.sidebar-footer > p', '.scope-line', '.metric-card > p', '.command-path',
    '.trend-label', 'th', '.activity-main span, .route-main span',
    '.route-metrics span', '.evidence-panel .evidence-pricing, .evidence-panel .evidence-spread',
)


def contrast(first, second):
    def luminance(color):
        channels = [int(color[i:i+2],16) / 255 for i in (1,3,5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return sum(c*w for c,w in zip(linear,(0.2126,0.7152,0.0722)))
    values = sorted((luminance(first),luminance(second)))
    return (values[1] + 0.05) / (values[0] + 0.05)


class DashboardContrastTests(unittest.TestCase):
    def test_secondary_text_passes_declared_dark_surfaces(self):
        self.assertAlmostEqual(contrast('#000000','#ffffff'),21)
        css = CSS.read_text()
        palette = dict(re.findall(r'--([\w-]+):\s*(#[0-9a-f]{6})',css))
        for selector in SECONDARY_TEXT:
            rule = re.search(re.escape(selector) + r'\s*\{([^}]+)\}',css).group(1)
            value = re.search(r'(?:color|fill):\s*([^;]+)',rule).group(1).strip()
            color = palette[value[6:-1]] if value.startswith('var(--') else value
            for background in ('bg-deep','panel-solid','panel-hover'):
                with self.subTest(selector=selector,background=background):
                    self.assertGreaterEqual(contrast(color,palette[background]),4.5)
