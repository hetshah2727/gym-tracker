"""Starter templates for the drag-and-drop website builder.

A site is an ordered list of blocks. ``plans`` and ``trainers`` blocks are
"live": the public site fills them from the gym's current data, so prices and
staff stay in sync without republishing.
"""
import uuid

from app.database.models import Gym

TEMPLATES = {
    "classic": {"name": "Classic", "theme": {"primaryColor": "#16a34a", "font": "Inter", "mode": "light"}},
    "bold": {"name": "Bold", "theme": {"primaryColor": "#f97316", "font": "Oswald", "mode": "dark"}},
    "minimal": {"name": "Minimal", "theme": {"primaryColor": "#0f172a", "font": "Inter", "mode": "light"}},
}

BLOCK_TYPES = ["hero", "about", "plans", "trainers", "gallery", "testimonials", "timings", "contact", "cta"]


def _block(block_type: str, **props) -> dict:
    return {"id": uuid.uuid4().hex[:8], "type": block_type, "props": props}


def default_blocks(gym: Gym) -> list[dict]:
    return [
        _block("hero", heading=f"Train harder at {gym.name}",
               subheading="Expert trainers, modern equipment and plans that fit your goals.",
               ctaText="Book a free trial", ctaTarget="#contact", backgroundImage=None),
        _block("about", heading="About us",
               body=f"{gym.name} helps you get stronger, fitter and healthier with personal guidance."),
        _block("plans", heading="Membership plans", live=True),
        _block("trainers", heading="Meet our trainers", live=True),
        _block("gallery", heading="Inside the gym", images=[]),
        _block("timings", heading="Timings", rows=[{"days": "Mon - Sat", "hours": "5:30 AM - 10:30 PM"},
                                                   {"days": "Sunday", "hours": "7:00 AM - 12:00 PM"}]),
        _block("contact", heading="Get in touch", phone=gym.phone, email=gym.email,
               address=gym.address, showLeadForm=True),
    ]
