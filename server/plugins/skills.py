import os
import re
import shutil
import urllib.request
from pathlib import Path
from server.plugins import tool

SKILLS_DIR = Path("data/skills")
SKILLS_DIR.mkdir(parents=True, exist_ok=True)


def _parse_frontmatter_field(text: str, field: str) -> str:
    """Extract a flat string field (e.g. 'name' or 'description') from a YAML frontmatter block."""
    match = re.search(rf'^{field}\s*:\s*(.+)$', text, re.MULTILINE)
    if not match:
        return ""
    value = match.group(1).strip()
    return value.strip('"\'')


def get_skills_index() -> list[dict]:
    """Return [{name, description}] for every installed skill, read from SKILL.md frontmatter."""
    skills = []
    if not SKILLS_DIR.exists():
        return skills

    for item in sorted(SKILLS_DIR.iterdir()):
        skill_file = item / 'SKILL.md'
        if not (item.is_dir() and skill_file.exists()):
            continue
        try:
            content = skill_file.read_text(encoding='utf-8')
            frontmatter_match = re.match(r'^---\s*\n(.*?\n)---', content, re.DOTALL)
            frontmatter = frontmatter_match.group(1) if frontmatter_match else ""

            name = _parse_frontmatter_field(frontmatter, 'name') or item.name
            description = _parse_frontmatter_field(frontmatter, 'description')

            skills.append({"name": name, "description": description})
        except Exception:
            skills.append({"name": item.name, "description": ""})

    return skills

@tool(
    name="install_skill_from_url",
    description="Download and install a skill (markdown file) from a direct URL. It will be saved as SKILL.md inside a folder named after the skill.",
    parameters={
        "url": {"type": "string", "description": "The raw URL of the markdown file to download"},
        "skill_name": {"type": "string", "description": "The name of the skill (e.g., 'github', 'python-debug')"}
    },
    required=["url", "skill_name"]
)
def install_skill_from_url(url: str, skill_name: str) -> str:
    """Download a skill file from a URL and save it to data/skills/{skill_name}/SKILL.md."""
    try:
        skill_dir = SKILLS_DIR / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        file_path = skill_dir / 'SKILL.md'
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
            
        file_path.write_text(content, encoding='utf-8')
        return f"✅ Successfully installed skill '{skill_name}' from {url}"
    except Exception as e:
        return f"❌ Failed to install skill: {str(e)}"

@tool(
    name="list_skills",
    description="List all currently installed skills in the data/skills directory.",
    parameters={}
)
def list_skills() -> str:
    """List all available skill folders that contain a SKILL.md file."""
    try:
        skills = []
        for item in SKILLS_DIR.iterdir():
            if item.is_dir() and (item / 'SKILL.md').exists():
                skills.append(item.name)
        
        if not skills:
            return "No skills installed yet."
        
        skill_list = "\n".join(f"- {s}" for s in sorted(skills))
        return f"Installed skills:\n{skill_list}"
    except Exception as e:
        return f"❌ Failed to list skills: {str(e)}"

@tool(
    name="read_skill",
    description="Read the contents of a specific installed skill (reads its SKILL.md).",
    parameters={
        "skill_name": {"type": "string", "description": "The name of the skill (e.g., 'github')"}
    },
    required=["skill_name"]
)
def read_skill(skill_name: str) -> str:
    """Read a SKILL.md file from the data/skills/{skill_name} directory."""
    try:
        file_path = SKILLS_DIR / skill_name / 'SKILL.md'
        if not file_path.exists():
            return f"❌ Skill '{skill_name}' not found or missing SKILL.md."
            
        content = file_path.read_text(encoding='utf-8')
        return content
    except Exception as e:
        return f"❌ Failed to read skill: {str(e)}"

@tool(
    name="uninstall_skill",
    description="Remove/uninstall a skill by its name.",
    parameters={
        "skill_name": {"type": "string", "description": "The name of the skill to remove (e.g., 'github')"}
    },
    required=["skill_name"]
)
def uninstall_skill(skill_name: str) -> str:
    """Remove a skill folder from the data/skills directory."""
    try:
        skill_dir = SKILLS_DIR / skill_name
        if not skill_dir.exists() or not skill_dir.is_dir():
            return f"❌ Skill '{skill_name}' not found."
            
        shutil.rmtree(skill_dir)
        return f"✅ Successfully removed skill '{skill_name}'"
    except Exception as e:
        return f"❌ Failed to remove skill: {str(e)}"
