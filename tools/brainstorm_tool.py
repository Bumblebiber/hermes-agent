#!/usr/bin/env python3
"""
Brainstorm Tool — Agent-initiated multi-model creative ideation.

Lets the main agent convene brainstorming sessions with models from
different providers. Loads a creativity technique from a skill file,
creates a GroupChat session with role-based participants, and returns
the formatted transcript.

Technique skills are defined in skills/brainstorm-*.md and define
the participants (roles, system prompts, recommended models).

Usage by the agent::

    brainstorm(technique="disney", topic="How to improve onboarding?")
"""

from __future__ import annotations

import json
import logging
import os
import re
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.auxiliary_client import call_llm
from agent.groupchat import GroupChat
from tools.registry import registry

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Skill parsing helpers
# ------------------------------------------------------------------

def _find_skill_file(technique: str) -> Optional[Path]:
    """Locate a brainstorm skill file by technique name."""
    candidates = [
        Path.home() / ".hermes" / "skills" / f"brainstorm-{technique}.md",
        Path(__file__).resolve().parent.parent / "skills" / f"brainstorm-{technique}.md",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _parse_skill(filepath: Path) -> Dict[str, Any]:
    """Extract technique metadata and participant definitions from a skill file.

    Returns a dict with:
        name, description, technique, participants: [{name, system_prompt, model?}]
    """
    text = filepath.read_text(encoding="utf-8")
    result: Dict[str, Any] = {
        "participants": [],
    }

    # Extract participant blocks: each starts with "### Name" followed by
    # "**System Prompt**: ..." code block
    participant_pattern = re.compile(
        r'^###\s+(.+?)\n(.*?)(?=^###\s|\Z)',
        re.MULTILINE | re.DOTALL,
    )

    for match in participant_pattern.finditer(text):
        name = match.group(1).strip()
        block = match.group(2)

        # Skip non-participant headers (like "## Usage", "## Participants")
        if name.lower() in ("usage", "participants", "best for"):
            continue

        # Extract system prompt from code block
        prompt_match = re.search(
            r'\*\*System Prompt\*\*[:\s]*\n\s*```\n(.*?)```',
            block, re.DOTALL,
        )
        if not prompt_match:
            continue

        system_prompt = textwrap.dedent(prompt_match.group(1)).strip()

        # Extract recommended model
        model_match = re.search(
            r'\*\*Recommended Model\*\*[:\s]*(.+?)(?:\n|$)',
            block,
        )
        model = model_match.group(1).strip() if model_match else None

        result["participants"].append({
            "name": name,
            "system_prompt": system_prompt,
            "model": model,
        })

    return result


# ------------------------------------------------------------------
# Model resolution
# ------------------------------------------------------------------

def _resolve_provider_for_model(model_hint: Optional[str]) -> str:
    """Heuristic to pick a provider for a model hint.

    Default: auto-detect from available credentials. Falls back to 'openrouter'.
    """
    # Check which providers are configured
    if os.getenv("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("DEEPSEEK_API_KEY"):
        return "deepseek"
    return "openrouter"  # fallback


# ------------------------------------------------------------------
# Brainstorm handler
# ------------------------------------------------------------------

def brainstorm_handler(args: Dict[str, Any], **kwargs) -> str:
    """Execute a brainstorming session.

    Args (from tool schema):
        technique: Technique name (disney, six-hats, scamper, brainwriting)
        topic: The topic/question to brainstorm about
        models: Optional list of {name, provider, model} overrides
        rounds: Number of rounds (default 1)

    Returns:
        JSON with transcript and metadata.
    """
    technique = (args.get("technique") or "").strip().lower()
    topic = (args.get("topic") or "").strip()
    models_override = args.get("models") or []
    rounds = max(1, min(5, int(args.get("rounds", 1) or 1)))

    if not technique:
        return json.dumps({"error": "technique is required"})
    if not topic:
        return json.dumps({"error": "topic is required"})

    # Locate and parse the technique skill
    skill_file = _find_skill_file(technique)
    if not skill_file:
        available = _list_available_techniques()
        return json.dumps({
            "error": f"Unknown technique '{technique}'. Available: {available}"
        })

    try:
        skill = _parse_skill(skill_file)
    except Exception as exc:
        logger.exception("Failed to parse skill %s", skill_file)
        return json.dumps({"error": f"Failed to parse technique: {exc}"})

    participants = skill.get("participants", [])
    if not participants:
        return json.dumps({"error": f"No participants defined in {technique}"})

    # Build model override map
    override_map: Dict[str, Dict[str, str]] = {}
    for entry in models_override:
        if isinstance(entry, dict) and "name" in entry:
            override_map[entry["name"].lower()] = entry

    # Create group chat
    gc = GroupChat()
    for p in participants:
        name = p["name"]
        override = override_map.get(name.lower(), {})
        provider = override.get("provider") or _resolve_provider_for_model(
            override.get("model") or p.get("model")
        )
        model = override.get("model") or p.get("model") or ""
        gc.add(
            name=name,
            system=p["system_prompt"],
            provider=provider,
            model=model if model else None,
        )

    # Run rounds
    all_responses: List[str] = []
    for round_num in range(1, rounds + 1):
        if rounds > 1:
            msg = f"@all Round {round_num}/{rounds}: {topic}"
        else:
            msg = f"@all {topic}"

        try:
            response = gc.send(msg)
            all_responses.append(response)
        except Exception as exc:
            logger.exception("Brainstorm round %d failed", round_num)
            all_responses.append(f"Round {round_num} error: {exc}")

    # Build result
    transcript_parts = [
        f"🧠 Brainstorm: {technique.upper()}",
        f"Topic: {topic}",
        f"Participants: {', '.join(p['name'] for p in participants)}",
        f"Rounds: {rounds}",
        "",
    ]
    for i, resp in enumerate(all_responses):
        if rounds > 1:
            transcript_parts.append(f"── Round {i + 1} ──")
        transcript_parts.append(resp)
        transcript_parts.append("")

    return json.dumps({
        "technique": technique,
        "topic": topic,
        "transcript": "\n".join(transcript_parts),
        "full_transcript": gc.full_transcript(),
    })


def _list_available_techniques() -> List[str]:
    """List brainstorm skill files found on disk."""
    techniques = []
    for base in [
        Path.home() / ".hermes" / "skills",
        Path(__file__).resolve().parent.parent / "skills",
    ]:
        if not base.exists():
            continue
        for f in sorted(base.glob("brainstorm-*.md")):
            name = f.stem.replace("brainstorm-", "")
            techniques.append(name)
    return sorted(set(techniques))


def check_brainstorm_requirements() -> bool:
    """Brainstorming requires at least one configured LLM provider."""
    return bool(
        os.getenv("OPENROUTER_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
    )


# ------------------------------------------------------------------
# Register tool
# ------------------------------------------------------------------

BRAINSTORM_TOOL_SCHEMA = {
    "name": "brainstorm",
    "description": (
        "Start a multi-model brainstorming session using a creativity technique. "
        "Queries multiple LLMs (different providers/models) in parallel, each "
        "with a role-specific personality. The models see each other's responses "
        "and build on them. Use for creative ideation, problem solving, product "
        "design, strategy, and any task benefiting from diverse AI perspectives.\n\n"
        "Available techniques:\n"
        "- disney: Dreamer (vision), Realist (planning), Critic (quality)\n"
        "- six-hats: White (facts), Red (emotion), Black (risks), Yellow (benefits), Green (creativity), Blue (process)\n"
        "- scamper: Substitute, Combine, Adapt, Modify, Put to use, Eliminate, Reverse\n"
        "- brainwriting: 6 thinkers × 3 ideas × 5 rounds of silent ideation\n\n"
        "Models default to auto-detection from configured providers. "
        "Override with the 'models' parameter to assign specific provider:model pairs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "technique": {
                "type": "string",
                "description": "Creativity technique: disney, six-hats, scamper, or brainwriting",
                "enum": ["disney", "six-hats", "scamper", "brainwriting"],
            },
            "topic": {
                "type": "string",
                "description": "The topic, question, or problem to brainstorm about",
            },
            "models": {
                "type": "array",
                "description": "Optional model assignments per participant",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Participant name"},
                        "provider": {"type": "string", "description": "Provider (openrouter, anthropic, openai, deepseek)"},
                        "model": {"type": "string", "description": "Model ID"},
                    },
                },
            },
            "rounds": {
                "type": "integer",
                "description": "Number of brainstorming rounds (1-5, default: 1)",
                "minimum": 1,
                "maximum": 5,
            },
        },
        "required": ["technique", "topic"],
    },
}


registry.register(
    name="brainstorm",
    toolset="creativity",
    schema=BRAINSTORM_TOOL_SCHEMA,
    handler=brainstorm_handler,
    check_fn=check_brainstorm_requirements,
    description="Multi-model creative brainstorming with parallel LLM participants",
    emoji="🧠",
)
