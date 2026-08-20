from pathlib import Path


def test_ticket_2_brand_tokens_acceptance():
    css = (Path(__file__).parents[1] / "static/table-story.css").read_text().lower()
    assert all(color in css for color in ("#fff8ed", "#c9472d", "#3f6b4f", "#26231f", "#e9b44c"))
    assert ".recipe-grid" in css and "minmax(220px,1fr)" in css
    assert "@media (max-width: 520px)" in css and "grid-template-columns:1fr" in css
    assert ":focus-visible" in css and "outline" in css
    assert '.cookbook[aria-pressed="true"]' in css
