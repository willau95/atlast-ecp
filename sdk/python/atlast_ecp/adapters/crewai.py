"""
ATLAST ECP — CrewAI Callback Handler

One-line integration for CrewAI crews and agents.

Usage:
    from atlast_ecp.adapters.crewai import ATLASTCrewCallback

    # Option 1: Crew-level callback
    crew = Crew(
        agents=[researcher, writer],
        tasks=[research_task, write_task],
        callbacks=[ATLASTCrewCallback(agent="my-crew")],
    )

    # Option 2: Step-level callback
    crew = Crew(
        agents=[researcher],
        tasks=[task],
        step_callback=ATLASTCrewCallback(agent="my-crew").step_callback,
    )

Captures: task executions, agent steps, tool calls.
All content is SHA-256 hashed locally — nothing leaves your device.
Fail-Open: adapter errors never affect your crew.
"""

from __future__ import annotations

import time
from typing import Any, Optional


class ATLASTCrewCallback:
    """
    CrewAI callback that records ECP evidence for task/step executions.

    Args:
        agent: Agent identifier string (default: "crewai-agent")
        verbose: Print ECP record IDs to stdout (default: False)
    """

    def __init__(self, agent: str = "crewai-agent", verbose: bool = False):
        self.agent = agent
        self.verbose = verbose
        self._record_count = 0
        self._task_starts: dict[str, float] = {}

    @property
    def record_count(self) -> int:
        return self._record_count

    def __call__(self, output: Any) -> None:
        """
        Called by CrewAI when a task completes.

        CrewAI passes a TaskOutput object with:
          - .description (task description)
          - .raw (raw output text)
          - .agent (agent name, if available)
        """
        try:
            task_desc = ""
            output_text = ""
            agent_name = self.agent

            if hasattr(output, "description"):
                task_desc = str(output.description)
            elif isinstance(output, dict):
                task_desc = output.get("description", str(output))
            else:
                task_desc = str(output)

            if hasattr(output, "raw"):
                output_text = str(output.raw)
            elif hasattr(output, "output"):
                output_text = str(output.output)
            elif isinstance(output, dict):
                output_text = output.get("raw", output.get("output", str(output)))
            else:
                output_text = str(output)

            if hasattr(output, "agent") and output.agent:
                agent_name = f"{self.agent}/{output.agent}"

            self._do_record(
                input_content=task_desc,
                output_content=output_text,
                action="llm_call",
                agent_name=agent_name,
            )
        except Exception:
            pass  # Fail-Open

    def step_callback(self, step_output: Any) -> None:
        """
        Called by CrewAI on each agent step.

        Step output typically has:
          - For AgentAction: .tool, .tool_input, .log
          - For AgentFinish: .output, .log
        """
        try:
            # AgentAction (tool call)
            if hasattr(step_output, "tool"):
                tool_name = step_output.tool
                tool_input = str(getattr(step_output, "tool_input", ""))
                log = str(getattr(step_output, "log", ""))
                self._do_record(
                    input_content=f"[{tool_name}] {tool_input}",
                    output_content=log,
                    action="tool_call",
                )
            # AgentFinish
            elif hasattr(step_output, "output"):
                self._do_record(
                    input_content=str(getattr(step_output, "log", "")),
                    output_content=str(step_output.output),
                    action="llm_call",
                )
            # Dict format
            elif isinstance(step_output, dict):
                self._do_record(
                    input_content=str(step_output.get("input", step_output.get("log", ""))),
                    output_content=str(step_output.get("output", step_output.get("result", ""))),
                    action=step_output.get("type", "llm_call"),
                )
            else:
                self._do_record(
                    input_content="",
                    output_content=str(step_output),
                    action="llm_call",
                )
        except Exception:
            pass  # Fail-Open

    def on_task_start(self, task_description: str) -> None:
        """Optional: call this manually before a task to track latency."""
        try:
            self._task_starts[task_description[:100]] = time.time()
        except Exception:
            pass

    def _do_record(self, input_content, output_content, action="llm_call",
                   agent_name=None, model=None, latency_ms=0):
        """Create and save an ECP record. Fail-Open."""
        try:
            from atlast_ecp.core import record_minimal
            rid = record_minimal(
                input_content=input_content,
                output_content=output_content,
                agent=agent_name or self.agent,
                action=action,
                model=model,
                latency_ms=latency_ms,
            )
            self._record_count += 1
            if self.verbose and rid:
                print(f"[ATLAST ECP] {rid}")
        except Exception:
            pass  # Fail-Open
