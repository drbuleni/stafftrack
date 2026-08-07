"""Contrast audit for the StaffTrack design system.

Guards against the class of bug that shipped twice: text rendered on a
background it cannot be read against (dark headings on dark card headers,
the unreadable NET COLLECTIONS row). Every foreground/background pair the
design system declares is checked against WCAG AA.

Run: python tools/check_contrast.py
Exits non-zero if any pair fails, so it can gate a commit.
"""
import sys

# Tokens — keep in step with app/static/css/tokens.css
ACCENT = '#1F5F4E'
ACCENT_HOVER = '#17493C'
ACCENT_WASH = '#EAF2EE'
INK = '#16211E'
BODY = '#4A5A55'
MUTED = '#5D6E69'
ON_ACCENT = '#FFFFFF'
GROUND = '#F4F6F5'
PANEL = '#FFFFFF'
PANEL_ALT = '#FAFBFA'
SUCCESS, SUCCESS_WASH = '#1F7A4C', '#E6F2EB'
WARNING, WARNING_WASH = '#845812', '#F7EFE1'
DANGER, DANGER_WASH = '#9E3232', '#F6E7E7'
INFO, INFO_WASH = '#2A6480', '#E6EFF4'

# (label, foreground, background, minimum ratio)
# 4.5 for body text, 3.0 for large/bold display text and UI boundaries.
PAIRS = [
    ('body on ground',            BODY, GROUND, 4.5),
    ('body on panel',             BODY, PANEL, 4.5),
    ('body on panel-alt',         BODY, PANEL_ALT, 4.5),
    ('ink on ground',             INK, GROUND, 4.5),
    ('ink on panel',              INK, PANEL, 4.5),
    ('muted on ground',           MUTED, GROUND, 4.5),
    ('muted on panel',            MUTED, PANEL, 4.5),
    ('muted on panel-alt',        MUTED, PANEL_ALT, 4.5),

    ('on-accent on accent',       ON_ACCENT, ACCENT, 4.5),
    ('on-accent on accent-hover', ON_ACCENT, ACCENT_HOVER, 4.5),
    ('accent on accent-wash',     ACCENT, ACCENT_WASH, 4.5),
    ('accent on panel',           ACCENT, PANEL, 4.5),
    ('accent on ground',          ACCENT, GROUND, 4.5),
    ('ink on accent-wash',        INK, ACCENT_WASH, 4.5),

    ('success on wash',           SUCCESS, SUCCESS_WASH, 4.5),
    ('success on panel',          SUCCESS, PANEL, 4.5),
    ('warning on wash',           WARNING, WARNING_WASH, 4.5),
    ('warning on panel',          WARNING, PANEL, 4.5),
    ('danger on wash',            DANGER, DANGER_WASH, 4.5),
    ('danger on panel',           DANGER, PANEL, 4.5),
    ('info on wash',              INFO, INFO_WASH, 4.5),
    ('info on panel',             INFO, PANEL, 4.5),

    ('white on success',          ON_ACCENT, SUCCESS, 4.5),
    ('white on danger',           ON_ACCENT, DANGER, 4.5),
    ('white on info',             ON_ACCENT, INFO, 4.5),
]


def contrast_ratio(fg_hex, bg_hex):
    """WCAG 2.1 relative-luminance contrast ratio between two hex colours."""
    def luminance(value):
        value = value.lstrip('#')
        channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        channels = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                    for c in channels]
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    a, b = luminance(fg_hex), luminance(bg_hex)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def main():
    failures = []
    print(f"{'pair':<28} {'ratio':>7}  {'min':>4}  result")
    print('-' * 52)
    for label, fg, bg, minimum in PAIRS:
        ratio = contrast_ratio(fg, bg)
        ok = ratio >= minimum
        if not ok:
            failures.append((label, ratio, minimum))
        print(f'{label:<28} {ratio:>7.2f}  {minimum:>4.1f}  {"PASS" if ok else "FAIL"}')

    print('-' * 52)
    if failures:
        print(f'{len(failures)} pair(s) below the minimum:')
        for label, ratio, minimum in failures:
            print(f'  {label}: {ratio:.2f} < {minimum}')
        return 1
    print(f'All {len(PAIRS)} pairs pass WCAG AA.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
