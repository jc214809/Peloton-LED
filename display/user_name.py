"""Compatibility wrapper: username is now one word.

This module kept to avoid breaking imports that still reference
`display.user_name`. New code should import from `display.username`.
"""

from display.username import render_username  # re-export for backward compatibility
