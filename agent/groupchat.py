#!/usr/bin/env python3
"""
GroupChat Engine — Multi-Model Parallel Brainstorming

Enables multi-participant conversations where several LLMs (each with their
own personality, provider, and model) respond to user messages in parallel.
Participants see the full conversation history but only reply when explicitly
@mentioned (by name or @all).

Shared by:
- CLI `/brainstorm` slash command (interactive group chat mode)
- Agent `brainstorm` tool (agent-initiated creative ideation sessions)

Usage::

    gc = GroupChat()
    gc.add("Dreamer", system="You are a visionary...", provider="openrouter", model="claude-sonnet-4")
    gc.add("Realist", system="You are pragmatic...", provider="openrouter", model="gpt-4o")
    result = gc.send("@all How can we improve onboarding?")
    # result is a formatted transcript string
"""

from __future__ import annotations

import concurrent.futures
import logging
import os
import threading
from typing import Any, Dict, List, Optional

from agent.auxiliary_client import call_llm

logger = logging.getLogger(__name__)


class Participant:
    """A single participant in a GroupChat session."""

    def __init__(
        self,
        name: str,
        system_prompt: str,
        provider: str = "openrouter",
        model: Optional[str] = None,
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.provider = provider
        self.model = model  # None = provider default

    def __repr__(self):
        return f"Participant({self.name!r}, provider={self.provider!r})"


class GroupChat:
    """Orchestrates parallel multi-model conversations with @mention routing.

    A GroupChat session holds a list of participants and a shared message
    history.  When ``send()`` is called with a user message, the engine:

    1. Parses @mentions to determine which participants should reply
    2. Builds a message list per participant (system prompt + full history)
    3. Sends all reply requests to their respective LLMs in parallel
    4. Collects responses and appends them to the shared history
    5. Returns a formatted transcript

    Participants always see the full conversation (all user messages + all
    participant responses) so they can build on each other's ideas.
    """

    # Pre-compiled regex for @mention parsing
    _MENTION_RE = None

    def __init__(self):
        self._participants: Dict[str, Participant] = {}
        self._history: List[Dict[str, Any]] = []  # [{role, name?, content}]
        self._lock = threading.Lock()
        self._round = 0
        self._total_rounds = 0

    # ------------------------------------------------------------------
    # Participant management
    # ------------------------------------------------------------------

    def add(self, name: str, system: str, provider: str = "openrouter",
            model: Optional[str] = None) -> None:
        """Register a participant.  ``name`` is used for @mention matching."""
        with self._lock:
            self._participants[name.lower()] = Participant(
                name=name,
                system_prompt=system,
                provider=provider,
                model=model,
            )

    def remove(self, name: str) -> None:
        with self._lock:
            self._participants.pop(name.lower(), None)

    def list_participants(self) -> List[str]:
        with self._lock:
            return [p.name for p in self._participants.values()]

    # ------------------------------------------------------------------
    # Mention parsing
    # ------------------------------------------------------------------

    def _parse_mentions(self, message: str) -> List[str]:
        """Return list of participant names mentioned in the message.

        Rules:
        - ``@all`` or ``@everyone`` → all participants
        - ``@Name`` → participant whose name.lower() matches
        - No mentions → empty list (nobody replies)
        """
        text = message.strip()
        lowered = text.lower()

        if lowered.startswith("@all") or lowered.startswith("@everyone"):
            with self._lock:
                return list(self._participants.keys())

        mentioned = []
        for name_lower, p in self._participants.items():
            if f"@{name_lower}" in lowered:
                mentioned.append(name_lower)
        return mentioned

    # ------------------------------------------------------------------
    # Message building
    # ------------------------------------------------------------------

    def _build_messages(self, participant: Participant) -> List[Dict[str, str]]:
        """Build the full message list for a participant.

        Format:
            [system] Participant's personality prompt
            [user]   First user message
            [assistant] Response from participant A (prefixed with name)
            [user]   Second user message
            ...
        """
        msgs: List[Dict[str, str]] = [
            {"role": "system", "content": participant.system_prompt},
        ]
        for entry in self._history:
            role = entry["role"]
            content = entry.get("content", "")
            entry_name = entry.get("name", "")
            if role == "user":
                msgs.append({"role": "user", "content": content})
            elif role == "assistant" and entry_name:
                # Format: "[Name]: response text"
                msgs.append({
                    "role": "assistant",
                    "content": f"[{entry_name}]: {content}",
                })
        return msgs

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def send(self, message: str, *,
             max_tokens: int = 2048,
             temperature: float = 0.9,
             timeout: float = 120.0) -> str:
        """Send a user message and collect replies from @mentioned participants.

        Returns a formatted transcript string of this round.

        Raises ValueError if no participants are mentioned.
        """
        text = message.strip()
        if not text:
            return ""

        mentioned = self._parse_mentions(text)
        if not mentioned:
            return (
                "No participants were @mentioned. "
                "Use @name or @all to address participants.\n"
                f"Available: {', '.join(self.list_participants())}"
            )

        # Append user message to shared history
        with self._lock:
            self._history.append({"role": "user", "content": text})
            self._total_rounds += 1

        # Collect responses in parallel
        responses: Dict[str, str] = {}
        errors: Dict[str, str] = {}

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(len(mentioned), 6)
        ) as pool:
            futures = {}
            for name_lower in mentioned:
                p = self._participants[name_lower]
                msgs = self._build_messages(p)
                futures[name_lower] = pool.submit(
                    _call_participant,
                    participant=p,
                    messages=msgs,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=timeout,
                )

            for name_lower, future in futures.items():
                display_name = self._participants[name_lower].name
                try:
                    result = future.result(timeout=timeout + 10)
                    if result.startswith("ERROR:"):
                        errors[display_name] = result[6:]
                    else:
                        responses[display_name] = result
                except Exception as exc:
                    errors[display_name] = str(exc)
                    logger.warning("GroupChat: %s failed: %s", display_name, exc)

        # Append responses to history
        with self._lock:
            for display_name, content in responses.items():
                self._history.append({
                    "role": "assistant",
                    "name": display_name,
                    "content": content,
                })
            for display_name, err in errors.items():
                self._history.append({
                    "role": "assistant",
                    "name": display_name,
                    "content": f"[ERROR: {err}]",
                })

        return self._format_responses(responses, errors)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def _format_responses(self, responses: Dict[str, str],
                          errors: Dict[str, str]) -> str:
        """Build a readable transcript for this round."""
        lines = []
        for name, text in responses.items():
            provider = self._participants[name.lower()].provider
            model = self._participants[name.lower()].model or "default"
            lines.append(f"┌─ @{name}  ({provider}/{model})")
            for line in text.strip().splitlines():
                lines.append(f"│ {line}")
            lines.append("└─")
            lines.append("")
        for name, err in errors.items():
            lines.append(f"┌─ @{name}  ⚠ ERROR")
            lines.append(f"│ {err}")
            lines.append("└─")
            lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Snapshot (for tools that want the full transcript)
    # ------------------------------------------------------------------

    def full_transcript(self) -> str:
        """Return the complete conversation transcript."""
        with self._lock:
            lines = []
            for entry in self._history:
                role = entry["role"]
                name = entry.get("name", "")
                content = entry.get("content", "")
                if role == "user":
                    lines.append(f"\n🧑 User:\n{content}\n")
                elif role == "assistant":
                    label = f"🤖 {name}" if name else "🤖"
                    lines.append(f"{label}:\n{content}\n")
            return "\n".join(lines)


# ------------------------------------------------------------------
# Internal: per-participant LLM call (runs in thread pool)
# ------------------------------------------------------------------

def _call_participant(
    participant: Participant,
    messages: List[Dict[str, str]],
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> str:
    """Execute a single LLM call for one participant. Returns response text."""
    try:
        response = call_llm(
            provider=participant.provider,
            model=participant.model or "",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        if response and hasattr(response, "choices") and response.choices:
            return response.choices[0].message.content or ""
        return ""
    except Exception as exc:
        logger.debug("GroupChat participant %s error: %s", participant.name, exc)
        return f"ERROR:{exc}"
