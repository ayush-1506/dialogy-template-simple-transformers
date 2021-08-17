"""
This module offers an interactive repl to run a Workflow.
"""
import ast
import json
import re
import time
from datetime import datetime
from pprint import pprint
from typing import List, Optional, Tuple

from dialogy.plugins.preprocess.text.normalize_utterance import normalize
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import FileHistory

from slu import constants as const
from slu.src.controller.prediction import predict_wrapper
from slu.utils.config import YAMLLocalConfig
from slu.utils.logger import log

CLIENT_CONFIGS = YAMLLocalConfig().generate()
PREDICT_API = predict_wrapper(CLIENT_CONFIGS)


def make_alts_from_text(text: str) -> Tuple[List[str], Optional[str]]:
    """
    Create test example from raw string.

    To test context pass the value with text like:

    ```python
    "I need fruit juice" | COF1
    ```

    Args:
        text (str): Raw string test input.

    Returns:
        Tuple[List[str], Optional[str]]
    """
    context: Optional[str]

    if "|" in text:
        text_, context = text.split("|")
        context_ = context.strip()
    else:
        text_ = text
        context_ = None

    text_ = re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9 ]+", " ", text_)).lower().strip()
    return [text_], context_


def parse_as(text: str, func) -> Tuple[Optional[List[str]], Optional[str]]:
    """
    Parse text as Dict either expecting json, or python object.

    Args:
        text (str): Raw user input.
        func (function): One of `json.loads`, `ast.literal_eval`.

    Returns:
        Optional[Dict[str, Any]]: Predict API compatible data structure.
    """
    try:
        content = func(text)
        if isinstance(content, dict):
            return normalize(content[const.ALTERNATIVES]), content[const.CONTEXT]
        elif isinstance(content, list):
            return normalize(content), {}
        else:
            return None, {}
    except json.JSONDecodeError:
        return None, {}
    except ValueError:
        return None, {}
    except SyntaxError:
        return None, {}


def repl_prompt(separator="", show_help=True):
    message = """
    Provide either a json like:\n

    ```
    {
        "alternatives": [[{"transcript": "...", "confidence": "..."}]],
        "context": {}
    }
    ```

    or 

    ```
    [[{"transcript": "...", "confidence": "..."}]]
    ```

    or just plain-text: "This sentence gets converted to above internally!"

Input interactions:

- ESC-ENTER to submit
- C-c or C-d to exit (C = Ctrl)
    """
    message = message.strip()
    return f"{message}\n{separator}\nEnter>\n" if show_help else "Enter>\n"


def repl() -> None:
    separator = "-" * 100
    show_help = True
    log.info("Loading models... this takes around 20s.")
    session = PromptSession(history=FileHistory(".repl_history"))  # type: ignore
    prompt = session.prompt
    auto_suggest = AutoSuggestFromHistory()

    try:
        while True:
            raw = prompt(
                repl_prompt(separator=separator, show_help=show_help),
                multiline=True,
                auto_suggest=auto_suggest,
            )

            if raw == "--help":
                raw = prompt(
                    repl_prompt(separator=separator, show_help=True),
                    multiline=True,
                    auto_suggest=auto_suggest,
                )

            show_help = False
            utterance, context = parse_as(raw, json.loads)
            if not utterance:
                utterance, context = parse_as(raw, ast.literal_eval)
            if not utterance:
                utterance, context = make_alts_from_text(raw)

            log.info("utterance")
            pprint(utterance)
            log.info("context: %s ", context)

            start = time.time()
            response = PREDICT_API(
                utterance,
                context,
                reference_time=int(datetime.now().timestamp() * 1000),
            )

            end = time.time() - start
            log.info("response")
            pprint(response)
            log.info("Prediction took %ds", end)
    except KeyboardInterrupt:
        log.info("Exiting...")
    except EOFError:
        log.info("Exiting...")
