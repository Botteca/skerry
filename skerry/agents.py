"""Gemini CLI and GitHub Copilot CLI hook events, mapped onto the Claude Code schema the Store understands.

Pure functions: `normalize()` runs on every incoming hook, `reply()` turns the Store's permission answer into the
format the agent expects. Sources: geminicli.com/docs/hooks/reference and
docs.github.com/en/copilot/reference/copilot-cli-reference/cli-hooks-reference.
"""
import json

# Gemini CLI: snake_case input like Claude Code. No hook can answer a permission prompt ("Notification" is
# observability only), so Skerry shows the activity and that a prompt is waiting in the terminal.
GEMINI_EVENTS = {"SessionStart": "SessionStart", "SessionEnd": "SessionEnd", "BeforeAgent": "UserPromptSubmit",
                 "BeforeTool": "PreToolUse", "AfterTool": "PostToolUse", "AfterAgent": "Stop",
                 "Notification": "Notification"}
# Copilot CLI (camelCase config): the input carries no event name, so skerry-cli passes it on the command line.
COPILOT_EVENTS = {"sessionStart": "SessionStart", "sessionEnd": "SessionEnd", "userPromptSubmitted": "UserPromptSubmit",
                  "preToolUse": "PreToolUse", "postToolUse": "PostToolUse", "postToolUseFailure": "PostToolUseFailure",
                  "agentStop": "Stop", "errorOccurred": "StopFailure", "permissionRequest": "PermissionRequest"}
ACTIVITY_ONLY = {"gemini"}   # agents whose permission prompts Skerry cannot answer


def _json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return {"input": value}
    return value if isinstance(value, dict) else {}


def normalize(agent, event, payload):
    """(event, payload) in Claude Code form, or (None, payload) for events Skerry ignores."""
    if agent == "gemini":
        ev = GEMINI_EVENTS.get(event)
        if ev == "Notification":
            if payload.get("notification_type") != "ToolPermission":
                return None, payload
            payload = {**payload, "notification_type": "permission_prompt"}
        elif ev == "Stop":
            payload = {**payload, "last_assistant_message": payload.get("prompt_response") or ""}
        return ev, payload
    if agent == "copilot":
        ev = COPILOT_EVENTS.get(event)
        p = payload
        if ev == "StopFailure":
            if p.get("recoverable", True):
                return None, payload
            err = p.get("error")
            p = {**p, "error": err.get("message") if isinstance(err, dict) else err}
        source = p.get("source")
        out = {**p, "session_id": p.get("sessionId") or p.get("session_id"),
               "tool_name": p.get("toolName") or p.get("tool_name") or "",
               "tool_input": _json(p.get("toolArgs") or p.get("toolInput") or p.get("tool_input")),
               "source": "startup" if source == "new" else source}
        return ev, out
    return event, payload


def reply(agent, out):
    """Permission answer in the agent's own format. {} always means "ask the user as usual"."""
    if agent != "copilot":
        return out
    decision = (out.get("hookSpecificOutput") or {}).get("decision") or {}
    return {k: v for k, v in decision.items() if k in ("behavior", "message")}
