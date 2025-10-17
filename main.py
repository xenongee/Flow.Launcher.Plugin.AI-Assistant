import sys
import os
from pathlib import Path

# Add lib directory to path for external modules
plugindir = Path.absolute(Path(__file__).parent)
paths = (".", "lib", "plugin")
sys.path = [str(plugindir / p) for p in paths] + sys.path

import re
import tempfile
import subprocess
import requests
from pyflowlauncher import Plugin, Result, send_results
from pyflowlauncher.result import ResultResponse
from pyflowlauncher.settings import settings

DEFAULT_LLM_PROVIDER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "mistralai/mistral-small-3.2-24b-instruct:free"
DEFAULT_DELIMITER = "||"
DEFAULT_SYSTEM_PROMPT = "You are an assistant providing concise, factually accurate responses with no formatting. Reply only with a plain-text answer: no markdown, lists, explanations, or extra text. Prioritize brevity and precise truth above all else. If a user asks a question that can be answered in the terminal, only provide commands."
DEFAULT_TEXT_EDITOR = r"notepad.exe"

# Flag to force settings API key test - set to True when testing
FORCE_SETTINGS_API_KEY = False

# Cache for settings to handle inconsistent settings() behavior
_settings_cache = {}

def get_env_api_key():
    """
    Get the API key from environment variable, respecting the test flag.
    When FORCE_SETTINGS_API_KEY is True, this will return None as if no env var exists.
    """
    if FORCE_SETTINGS_API_KEY:
        return None
    return os.environ.get("FLOWLLM_API_KEY")

def get_settings(key=None, default=None):
    """
    Get settings with environment variable priority for API key.
    """
    global _settings_cache

    # Try to get current settings
    current_settings = settings()

    # If settings is available, update cache
    if current_settings is not None:
        _settings_cache.update(current_settings)

    # Special case for API key - prioritize environment variable
    if key == "api_key":
        env_api_key = get_env_api_key()
        if env_api_key:
            return env_api_key

    # If a specific key is requested
    if key is not None:
        value = _settings_cache.get(key, default)

        if not value:
            value = default

        return value


    # Return all settings
    return _settings_cache


# Run at module load to initialize settings
try:
    settings_obj = settings()
    if settings_obj is not None:
        _settings_cache.update(settings_obj)
except Exception:
    pass


plugin = Plugin()


@plugin.on_method
def query(query: str) -> ResultResponse:
    """Main entry point for the plugin."""
    # Get settings using our cache mechanism
    api_provider_url = get_settings("api_url", DEFAULT_LLM_PROVIDER_URL)
    api_key = get_settings("api_key", "")
    default_model = get_settings("default_model", DEFAULT_MODEL)
    delimiter = get_settings("delimiter", DEFAULT_DELIMITER)
    system_prompt = get_settings("system_prompt", DEFAULT_SYSTEM_PROMPT)
    reasoning = get_settings("reasoning", True)
    full_response = get_settings("full_response", True)
    text_editor = get_settings("text_editor", DEFAULT_TEXT_EDITOR)

    if not query.strip():
        return send_results([
            Result(
                Title="AI Assistant",
                SubTitle=f"Type a question followed by {delimiter} to ask {default_model}",
                IcoPath="Images/app.png"
            )
        ])

    # Execute only if delimiter is present
    if delimiter in query:
        query = query.split(delimiter, 1)[0].strip()

        if not api_key:
            return send_results([
                Result(
                    Title="API Key not set",
                    SubTitle="Set FLOWLLM_API_KEY environment variable",
                    IcoPath="Images/app.png"
                )
            ])

        model_messages = []

        if system_prompt.strip():
            model_messages.append({"role": "system", "content": system_prompt})

        model_messages.append({"role": "user", "content": query})

        # Make the API call
        try:
            response = requests.post(
                api_provider_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/xenongee/Flow.Launcher.Plugin.AI-Assistant",
                    "X-Title": "AI Assistant - Flow Launcher Plugin"
                },
                json={
                    "model": default_model,
                    "messages": model_messages,
                    "reasoning": {
                        "enabled": reasoning
                    }
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                answer = result["choices"][0]["message"]["content"]

                # Show result with actions
                preview = answer[:100] + "..." if len(answer) > 100 else answer

                if full_response:
                    subtitle = answer
                else:
                    subtitle = preview

                subtitle = re.sub(r'[\s]+', ' ', subtitle).strip()

                return send_results([
                    Result(
                        Title=f"AI Response ({default_model})",
                        SubTitle=subtitle,
                        IcoPath="Images/app.png",
                        JsonRPCAction={
                            "method": "copy_to_clipboard",
                            "parameters": [answer]
                        },
                        ContextData=[answer, text_editor],
                        Score=100
                    ),
                    Result(
                        Title=f"Open in {Path(text_editor).stem}",
                        SubTitle=f"Open the full response in {Path(text_editor).stem}",
                        IcoPath="Images/note.png",
                        JsonRPCAction={
                            "method": "open_in_notepad",
                            "parameters": [answer, text_editor]
                        },
                        ContextData=[answer, text_editor]
                    )
                ])
            else:
                error_data = response.json().get("error", {})
                error_message = error_data.get("message", "Unknown error")
                return send_results([
                    Result(
                        Title=f"Error: {response.status_code}",
                        SubTitle=error_message,
                        IcoPath="Images/app.png"
                    )
                ])
        except Exception as e:
            return send_results([
                Result(
                    Title="Error",
                    SubTitle=str(e),
                    IcoPath="Images/app.png"
                )
            ])

    # Just preview when typing, no Enter execution
    return send_results([
        Result(
            Title=f"Ask AI: {query}",
            SubTitle=f"Add '{delimiter}' to send to {default_model}",
            IcoPath="Images/app.png",
            JsonRPCAction={
                "method": "copy_to_clipboard",
                "parameters": [query]
            },
            ContextData=query
        )
    ])


@plugin.on_method
def copy_to_clipboard(text: str) -> ResultResponse:
    """Copy text to clipboard."""
    try:
        import pyperclip
        pyperclip.copy(text)

        return send_results([
            Result(
                Title="Copied to clipboard",
                SubTitle=text[:100] + "..." if len(text) > 100 else text,
                IcoPath="Images/copy.png"
            )
        ])
    except ImportError:
        return send_results([
            Result(
                Title="Error: Could not copy to clipboard",
                SubTitle="The pyperclip module is not installed properly",
                IcoPath="Images/app.png"
            )
        ])


@plugin.on_method
def open_in_notepad(text: str, text_editor: str) -> None:
    """Open text in notepad - properly implemented to actually open notepad."""
    if not text_editor or not text_editor.strip():
        text_editor = DEFAULT_TEXT_EDITOR

    try:
        text_editor = os.path.normpath(text_editor)

        # Validate that the editor executable exists
        if not os.path.isfile(text_editor):
            print(f"Error: Text editor not found: {text_editor}")
            return

        # Create a temporary file with the text content
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="ai_response_")
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)

        # Open the file with notepad using subprocess
        subprocess.Popen([text_editor, path])
    except Exception as e:
        print(f"Error opening notepad: {e}")


@plugin.on_method
def context_menu(data: str) -> ResultResponse:
    """Context menu for showing additional actions on results."""
    if isinstance(data, list) and len(data) >= 2:
        answer = data[0]
        text_editor = data[1]
    else:
        answer = data if isinstance(data, str) else str(data)
        text_editor = DEFAULT_TEXT_EDITOR

    return send_results([
        Result(
            Title="Copy to clipboard",
            SubTitle="Copy the full response to clipboard",
            IcoPath="Images/copy.png",
            JsonRPCAction={
                "method": "copy_to_clipboard",
                "parameters": [answer]
            }
        ),
        Result(
            Title=f"Open in {Path(text_editor).stem}",
            SubTitle=f"Open the full response in {Path(text_editor).stem} for viewing/editing",
            IcoPath="Images/note.png",
            JsonRPCAction={
                "method": "open_in_notepad",
                "parameters": [answer, text_editor]
            }
        )
    ])


if __name__ == "__main__":
    plugin.run()
