"""Office deliverables — Word, Excel, PowerPoint as first-class tools.

Knowledge work ends in a file someone opens, not in a chat reply. Without these tools the
agent's only route to a .docx is writing an ad-hoc script against a library that isn't a
declared dependency — which fails on a clean install and produces unreviewable heredocs.

Each format is its own module because they version independently: a python-pptx API change
must not touch the Word reader. Path safety is shared (``paths.py``) because it must be
identical everywhere.

Dependencies are optional extras (``pip install 'coworker[office]'``). A tool whose library
is missing is still REGISTERED, and returns an actionable error when called. Hiding it would
be worse: the model would fall back to inventing a shell workaround instead of telling the
user what to install.
"""

from __future__ import annotations

from typing import Any

from .docx_tools import docx_tools
from .image_tools import image_tools
from .pdf_tools import pdf_tools
from .pptx_tools import pptx_tools
from .xlsx_tools import xlsx_tools

__all__ = [
    "docx_tools",
    "xlsx_tools",
    "pptx_tools",
    "pdf_tools",
    "image_tools",
    "office_tools",
]


def office_tools(context: Any) -> list:
    """Every Office tool for a session context (Word, Excel, PowerPoint, PDF, images)."""
    return [
        *docx_tools(context),
        *xlsx_tools(context),
        *pptx_tools(context),
        *pdf_tools(context),
        *image_tools(context),
    ]
