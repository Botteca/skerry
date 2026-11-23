"""Safety rules of "allow for N minutes": what a timed rule may never approve."""
import pytest

from skerry.store import risky

CWD = "C:/rep/ExampleApp"


@pytest.mark.parametrize("command", [
    "npm test", "git status", "git push origin main", "python tools/build.py --out dist",
    "dir /s", r"type C:\rep\ExampleApp\README.md", "pytest -k test_dates",
])
def test_safe_commands(command):
    assert not risky("Bash", {"command": command}, CWD)


@pytest.mark.parametrize("command", [
    "rm -rf node_modules", "git rm old.py", "del /s /q build", "rd /s build", "Remove-Item -Recurse dist",
    "format D:", "git push --force", "git push -f origin main", "git push origin +main",
    "git push --force-with-lease", "psql -c 'DROP TABLE users'", "TRUNCATE TABLE logs", "npm run clean && rm x",
    # outside the project folder
    "cat ../other/secret.txt", r"copy a.txt C:\Windows\a.txt", "type C:/rep/ExampleApp2/x", "cat ~/.ssh/id_rsa",
    "echo %USERPROFILE%", r"Get-Content $env:APPDATA\x", "cat /etc/passwd", r"cp x \\server\share",
])
def test_dangerous_commands(command):
    assert risky("Bash", {"command": command}, CWD)


def test_codex_command_lists():
    assert not risky("shell", {"command": ["git", "status"]}, CWD)
    assert risky("shell", {"command": ["bash", "-lc", "rm -rf build"]}, CWD)


def test_file_tools_stay_inside_the_project():
    assert not risky("Edit", {"file_path": r"C:\rep\ExampleApp\src\app.py"}, CWD)
    assert not risky("Write", {"file_path": "src/new.py"}, CWD)
    assert risky("Edit", {"file_path": "C:/rep/OtherApp/app.py"}, CWD)
    assert risky("Write", {"file_path": "../OtherApp/app.py"}, CWD)
    assert risky("Read", {"file_path": "~/.claude/settings.json"}, CWD)


def test_patches():
    ok = "*** Begin Patch\n*** Update File: src/app.py\n@@\n-a\n+b\n*** End Patch"
    assert not risky("apply_patch", {"input": ok}, CWD)
    assert risky("apply_patch", {"input": ok.replace("Update File: src/app.py", "Delete File: src/app.py")}, CWD)
    assert risky("apply_patch", {"input": ok.replace("src/app.py", "../Other/app.py")}, CWD)


def test_no_project_folder_means_no_rule():
    assert risky("Bash", {"command": "npm test"}, "")
