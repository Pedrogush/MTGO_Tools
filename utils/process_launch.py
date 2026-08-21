"""Tell "Windows refused to start this" apart from "the launch failed".

Every executable this app starts -- the .NET bridge, and the Setup binary an
in-app update downloads -- goes through ``CreateProcess``, and on Windows a
handful of ``GetLastError`` values mean something categorically different from
the rest: the file is present, readable and correct, and a security component
outside the app decided it is not allowed to run. Nothing the app does on a
retry changes that answer, so surfacing it as ``[WinError 4551]`` sends the user
looking for a bug in MTGO Tools that is not there.

The one that prompted this module is 4551,
``ERROR_SYSTEM_INTEGRITY_POLICY_VIOLATION`` -- "An Application Control policy
has blocked this file". On consumer Windows 11 that is Smart App Control, which
blocks executables it cannot vouch for by cloud reputation *or* code signature;
on managed machines it is App Control for Business / WDAC (the message there
reads "Your organization used Device Guard to block this app"). MTGO Tools
ships unsigned and installs under ``%LOCALAPPDATA%\\Programs``, which is exactly
the shape both of those refuse by default, so this is an environment condition
rather than a defect -- but only if the app says so.

The neighbouring codes are grouped in because they land the user in the same
place: an administrator or a security product, not a retry. Group policy /
AppLocker denies with 1260, and Defender's on-access scanner denies with 225/226
when it has quarantined the file out from under the launch.

Deliberately dependency-free (no wx, no i18n, no logging) so both the update
installer and the bridge transport can use it, and so it is testable on Linux
where ``OSError.winerror`` does not exist at all.
"""

from __future__ import annotations

#: Reason tokens. Stable strings rather than an enum because they are used as
#: i18n key suffixes and appear in logs and bug reports.
APP_CONTROL = "app_control"
GROUP_POLICY = "group_policy"
ANTIVIRUS = "antivirus"

#: ``winerror`` values that mean the launch was refused, not that it failed.
#: Names are from ``winerror.h``; the values are load-bearing, so each one is
#: spelled out rather than expressed as a range -- 4554/4555 exist in that block
#: too but describe a malformed *policy*, not a blocked *file*, and would
#: mis-describe the situation if they were folded in here.
BLOCKED_WINERRORS: dict[int, str] = {
    225: ANTIVIRUS,  # ERROR_VIRUS_INFECTED
    226: ANTIVIRUS,  # ERROR_VIRUS_DELETED
    1260: GROUP_POLICY,  # ERROR_ACCESS_DISABLED_BY_POLICY
    4550: APP_CONTROL,  # ERROR_SYSTEM_INTEGRITY_ROLLBACK_DETECTED
    4551: APP_CONTROL,  # ERROR_SYSTEM_INTEGRITY_POLICY_VIOLATION
    4552: APP_CONTROL,  # ERROR_SYSTEM_INTEGRITY_INVALID_POLICY
    4553: APP_CONTROL,  # ERROR_SYSTEM_INTEGRITY_POLICY_NOT_SIGNED
}

#: Where the user is sent for the steps that actually resolve it. A link is
#: worth carrying in the message because the fix is several clicks deep in
#: Windows Security and differs between a personal and a managed machine.
HELP_URL = "https://github.com/Pedrogush/MTGO_Tools#windows-blocked-this-app-from-running"

_SENTENCES: dict[str, str] = {
    APP_CONTROL: (
        "Windows blocked {target} from running: an Application Control policy "
        "(Smart App Control on Windows 11, or App Control for Business / Device "
        "Guard on a managed PC) refused the file because MTGO Tools is not "
        "code-signed. The files installed correctly -- Windows will not let them "
        "start."
    ),
    GROUP_POLICY: (
        "Windows blocked {target} from running: a group policy / AppLocker rule "
        "on this PC does not allow it. The files installed correctly -- Windows "
        "will not let them start."
    ),
    ANTIVIRUS: (
        "Antivirus blocked {target} from running and may have quarantined it. "
        "MTGO Tools ships unsigned, which is a common false positive."
    ),
}


def launch_block_reason(exc: BaseException) -> str | None:
    """Return the reason token for a refused launch, or ``None``.

    ``None`` is the answer for every ordinary failure -- a missing file, a bad
    path, a permissions problem -- so callers keep their existing error handling
    for those and only special-case what they can actually explain.

    ``winerror`` is read with ``getattr`` because the attribute only exists on
    Windows: on Linux an ``OSError`` simply has none, and the answer there is
    always ``None`` rather than an ``AttributeError`` in a failure path.
    """
    code = getattr(exc, "winerror", None)
    if not isinstance(code, int):
        return None
    return BLOCKED_WINERRORS.get(code)


def describe_launch_block(exc: BaseException, *, target: str) -> str | None:
    """A sentence naming what was blocked and by what, or ``None``.

    ``target`` is the thing the *user* recognises ("MTGO Tools", "the MTGO
    bridge", "the installer"), not the file path -- the path is already in the
    underlying error, and the sentence has to make sense before anyone expands
    the details.
    """
    reason = launch_block_reason(exc)
    if reason is None:
        return None
    return f"{_SENTENCES[reason].format(target=target)} See {HELP_URL}"


__all__ = [
    "ANTIVIRUS",
    "APP_CONTROL",
    "BLOCKED_WINERRORS",
    "GROUP_POLICY",
    "HELP_URL",
    "describe_launch_block",
    "launch_block_reason",
]
