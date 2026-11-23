# Security policy

Skerry runs a local HTTP server, edits the configuration of Claude Code and Codex, and can approve actions those agents
take on your PC. Security reports are taken seriously.

## Reporting a vulnerability

**Please do not open a public issue, discussion or pull request for a vulnerability.**

Report it privately through GitHub: go to the repository's **Security** tab →
[**Report a vulnerability**](https://github.com/fabrisimo/skerry/security/advisories/new). Only the maintainer can see it.

Please include:

- the Skerry version and Windows version;
- what an attacker can do and under which conditions (local user, another process, a web page, the network…);
- steps or a proof of concept to reproduce it;
- any suggested fix.

You should get a first answer within 7 days. Once the issue is confirmed, a fix is prepared and released, and the
advisory is published with credit to you (unless you prefer to stay anonymous).

## Supported versions

Only the latest release receives security fixes.

## Scope

In scope, for example:

- anything that lets something other than the user approve a permission request (the decision must only come from the
  Skerry window, never over HTTP);
- the local server (`127.0.0.1:47800`) being reachable from other machines or from web pages in a harmful way;
- tokens or secrets stored in clear text or readable by other users;
- changes to `~/.claude/settings.json` or `~/.codex/hooks.json` that break or weaken the user's configuration;
- the updater installing something that is not an official release.

Out of scope: issues that need an attacker who already runs code as the same Windows user (they could edit the agent
configuration directly), and the unsigned-executable SmartScreen warning.
