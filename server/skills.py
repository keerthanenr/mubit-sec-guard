"""Which skill file to point at for a finding."""
import re
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
SKILL_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

SKILLS = {
    ("web_php", "sql_injection"): "php-sql-injection",
    ("web_php", "xss"): "php-xss",
    ("web_php", "hardcoded_secret"): "php-hardcoded-secret",
    ("web_php", "path_traversal"): "php-path-traversal",
    ("web_php", "unsafe_deserialization"): "php-unsafe-deserialization",
}

# WordPress code gets the WordPress-specific skill (the CVE-2024-27956 bug class).
WORDPRESS = re.compile(r"\$wpdb|wp_ajax_|register_rest_route|current_user_can|add_action\s*\(")


def skill_for(lane, label, code):
    if lane == "web_php" and label == "sql_injection" and WORDPRESS.search(code):
        return "wordpress-request-to-query"
    return SKILLS.get((lane, label))


def list_skills():
    return sorted(p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md"))


def read_skill(skill_id):
    """Return the skill's markdown, or None. Only ids from the skills folder are served."""
    if not SKILL_ID.match(skill_id or "") or skill_id not in list_skills():
        return None
    return (SKILLS_DIR / skill_id / "SKILL.md").read_text()
