"""Ansible sudo become support for Ubuntu's sudo-rs prompt wrapper."""

from ansible.plugins.become.sudo import (  # type: ignore[import-not-found]
    BecomeModule as SudoBecomeModule,
)


DOCUMENTATION = r"""
name: sudo_rs
short_description: Substitute User DO through Ubuntu sudo-rs
description:
  - Uses Ansible's standard sudo behavior while recognizing sudo-rs's wrapped PAM prompt.
author: DovieW
options:
  become_user:
    description: User to become.
    default: root
    ini:
      - section: privilege_escalation
        key: become_user
    vars:
      - name: ansible_become_user
    env:
      - name: ANSIBLE_BECOME_USER
    keyword:
      - name: become_user
  become_exe:
    description: Sudo executable.
    default: sudo
    ini:
      - section: privilege_escalation
        key: become_exe
    vars:
      - name: ansible_become_exe
      - name: ansible_sudo_exe
    env:
      - name: ANSIBLE_BECOME_EXE
      - name: ANSIBLE_SUDO_EXE
    keyword:
      - name: become_exe
  become_flags:
    description: Options passed to sudo.
    default: -H -S
    ini:
      - section: privilege_escalation
        key: become_flags
    vars:
      - name: ansible_become_flags
      - name: ansible_sudo_flags
    env:
      - name: ANSIBLE_BECOME_FLAGS
      - name: ANSIBLE_SUDO_FLAGS
    keyword:
      - name: become_flags
  become_pass:
    description: Password passed to sudo.
    required: false
    vars:
      - name: ansible_become_password
      - name: ansible_become_pass
      - name: ansible_sudo_pass
    env:
      - name: ANSIBLE_BECOME_PASS
      - name: ANSIBLE_SUDO_PASS
  sudo_chdir:
    description: Directory to enter before invoking sudo.
    vars:
      - name: ansible_sudo_chdir
    env:
      - name: ANSIBLE_SUDO_CHDIR
"""


class BecomeModule(SudoBecomeModule):
    """Recognize sudo-rs wrapping Ansible's supplied password prompt."""

    name = "sudo_rs"

    def build_become_command(self, cmd, shell):
        command = super().build_become_command(cmd, shell)
        if self.prompt:
            # sudo-rs displays a PAM prompt as:
            # [sudo: <value supplied with --prompt>] Password:
            # Matching the stable prefix avoids depending on the PAM method's
            # translated Password/PIN text.
            self.prompt = f"[sudo: {self.prompt}]"
        return command
