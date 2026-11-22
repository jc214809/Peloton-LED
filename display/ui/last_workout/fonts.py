"""The fonts a workout page is drawn with, bundled so the layouts take one argument."""
from typing import Any, NamedTuple


class PageFonts(NamedTuple):
    """`title` is the discipline font, `titles` the optional larger one, `text` the small info font and
    `stat` the fixed 4 px stats font."""
    title: Any
    titles: Any | None
    text: Any
    stat: Any
