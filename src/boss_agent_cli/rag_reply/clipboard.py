"""Clipboard helpers for approve-and-copy."""

from __future__ import annotations

import shutil
import subprocess


def copy_text(text: str) -> bool:
	"""Copy text to the clipboard when a known platform tool is available."""
	commands = (
		["pbcopy"],
		["wl-copy"],
		["xclip", "-selection", "clipboard"],
		["xsel", "--clipboard", "--input"],
	)
	for command in commands:
		if shutil.which(command[0]) is None:
			continue
		try:
			subprocess.run(command, input=text, text=True, check=True, capture_output=True)
		except (subprocess.CalledProcessError, OSError):
			continue
		return True
	return False

