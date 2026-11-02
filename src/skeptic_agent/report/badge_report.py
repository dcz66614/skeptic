"""Badge generator (S12, E49): badge.svg."""

from __future__ import annotations

from pathlib import Path

from skeptic_agent.report.loader import RunData


def get_badge_color(sks: float) -> str:
    """Return color hex matching S12 thresholds.

    - >= 80: #2ea043 (green)
    - 60-79: #d29922 (yellow/orange)
    - < 60:  #cf222e (red)
    """
    if sks >= 80.0:
        return "#2ea043"
    if sks >= 60.0:
        return "#d29922"
    return "#cf222e"


def generate_badge_report(run_data: RunData, out_path: Path) -> Path:
    """Generate shields.io style badge.svg conforming to S12.

    Left label: skeptic
    Right label: SKS <integer>
    Color: #2ea043 (>=80), #d29922 (60-79), #cf222e (<60)

    Args:
        run_data: Loaded run data.
        out_path: File path to write badge.svg to.

    Returns:
        The written Path.
    """
    sks_val = run_data.sks_score
    sks_int = round(sks_val)
    color = get_badge_color(sks_val)

    left_label = "skeptic"
    right_label = f"SKS {sks_int}"

    left_width = 52
    right_width = 56
    total_width = left_width + right_width
    left_x = int(left_width * 5)
    right_x = int((left_width + (right_width / 2.0)) * 10)
    left_len = left_width * 7
    right_len = right_width * 7

    font_fam = "Verdana,Geneva,DejaVu Sans,sans-serif"
    svg_content = (
        f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20" """
        f"""role="img" aria-label="{left_label}: {right_label}">\n"""
        f"""  <title>{left_label}: {right_label}</title>\n"""
        """  <linearGradient id="s" x2="0" y2="100%">\n"""
        """    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>\n"""
        """    <stop offset="1" stop-opacity=".1"/>\n"""
        """  </linearGradient>\n"""
        """  <clipPath id="r">\n"""
        f"""    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>\n"""
        """  </clipPath>\n"""
        """  <g clip-path="url(#r)">\n"""
        f"""    <rect width="{left_width}" height="20" fill="#555"/>\n"""
        f"""    <rect x="{left_width}" width="{right_width}" height="20" fill="{color}"/>\n"""
        f"""    <rect width="{total_width}" height="20" fill="url(#s)"/>\n"""
        """  </g>\n"""
        f"""  <g fill="#fff" text-anchor="middle" font-family="{font_fam}" """
        """text-rendering="geometricPrecision" font-size="110">\n"""
        f"""    <text aria-hidden="true" x="{left_x}" y="150" fill="#010101" fill-opacity=".3" """
        f"""transform="scale(.1)" textLength="{left_len}">{left_label}</text>\n"""
        f"""    <text x="{left_x}" y="140" transform="scale(.1)" fill="#fff" """
        f"""textLength="{left_len}">{left_label}</text>\n"""
        f"""    <text aria-hidden="true" x="{right_x}" y="150" fill="#010101" fill-opacity=".3" """
        f"""transform="scale(.1)" textLength="{right_len}">{right_label}</text>\n"""
        f"""    <text x="{right_x}" y="140" transform="scale(.1)" fill="#fff" """
        f"""textLength="{right_len}">{right_label}</text>\n"""
        """  </g>\n"""
        """</svg>\n"""
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg_content, encoding="utf-8")
    return out_path
