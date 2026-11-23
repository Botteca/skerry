"""Gemini CLI, GitHub Copilot CLI and OpenCode events, mapped onto the Claude Code schema the Store understands.

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
# OpenCode: Skerry's plugin (integrations.OPENCODE_SOURCE) already sends Claude Code event names; its tools and
# arguments are mapped here. "PermissionResolved" = answered in OpenCode itself: the island's request is withdrawn.
OPENCODE_TOOLS = {"bash": "Bash", "read": "Read", "write": "Write", "edit": "Edit", "patch": "Edit",
                  "multiedit": "MultiEdit", "glob": "Glob", "grep": "Grep", "list": "LS", "webfetch": "WebFetch",
                  "websearch": "WebSearch", "task": "Task", "todowrite": "TodoWrite"}
OPENCODE_REPLY = {"allow": "once", "always": "always", "deny": "reject"}


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
    if agent == "opencode":
        return _opencode(event, payload)
    return event, payload


def _opencode(event, p):
    inp = dict(p.get("tool_input") or {}) if isinstance(p.get("tool_input"), dict) else {}
    for src, dst in (("filePath", "file_path"), ("oldString", "old_string"), ("newString", "new_string")):
        if src in inp and dst not in inp:
            inp[dst] = inp[src]
    tool = str(p.get("tool_name") or "")
    if event == "PermissionRequest":
        pats = inp.get("patterns")
        pats = [str(x) for x in pats] if isinstance(pats, list) else ([str(pats)] if pats else [])
        if tool == "bash" and "command" not in inp and pats:
            inp["command"] = " ".join(pats)
        elif tool in ("edit", "write", "read", "patch") and "file_path" not in inp and pats:
            inp["file_path"] = pats[0]
        elif "command" not in inp and "file_path" not in inp and (inp.get("title") or pats):
            inp["description"] = inp.get("title") or " ".join(pats)
    out = {**p, "tool_name": OPENCODE_TOOLS.get(tool, tool), "tool_input": inp}
    if event == "PermissionRequest" and p.get("can_always"):
        out["permission_suggestions"] = [{"type": "opencode", "behavior": "always"}]   # enables "Always"
    return event, out


def reply(agent, out):
    """Permission answer in the agent's own format. {} always means "ask the user as usual"."""
    if agent == "opencode":
        decision = (out.get("hookSpecificOutput") or {}).get("decision") or {}
        if decision.get("behavior") == "allow":
            return {"decision": "always" if decision.get("updatedPermissions") else "once"}
        return {"decision": "reject"} if decision.get("behavior") == "deny" else {}
    if agent != "copilot":
        return out
    decision = (out.get("hookSpecificOutput") or {}).get("decision") or {}
    return {k: v for k, v in decision.items() if k in ("behavior", "message")}
