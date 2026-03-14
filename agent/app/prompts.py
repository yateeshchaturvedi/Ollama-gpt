from pathlib import Path


def load_system_prompt() -> str:
    """Load the agent system prompt from disk."""
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "system_prompt.txt"
    return prompt_path.read_text(encoding="utf-8").strip()

