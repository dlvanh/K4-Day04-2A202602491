from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import streamlit as st

from chat import ARTIFACTS_DIR, ROOT, now_iso, run_model_tool_loop, safe_slug, trim_history, write_transcript
from providers import make_provider
from tools import load_tool_declarations, to_openai_tools
from versioning import artifact_version_dict, build_artifact_version

PROVIDERS = ["openai", "openrouter", "anthropic", "gemini"]
SYSTEM_PROMPT_PATH = ARTIFACTS_DIR / "system_prompt.md"
TOOLS_PATH = ARTIFACTS_DIR / "tools.yaml"

st.set_page_config(page_title="IT Helpdesk Agent", page_icon="🛠️", layout="wide")


@st.cache_resource(show_spinner=False)
def get_provider(provider_name: str):
    return make_provider(provider_name)


def load_artifacts(version_label: str):
    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    declarations = load_tool_declarations(TOOLS_PATH)
    openai_tools = to_openai_tools(declarations)
    artifact_version = build_artifact_version(version_label, SYSTEM_PROMPT_PATH, TOOLS_PATH)
    return system_prompt, openai_tools, artifact_version


def init_state() -> None:
    defaults = {
        "history": [],
        "display_turns": [],
        "turn_index": 0,
        "version_label": "v14",
        "transcript_id": None,
        "transcript": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_conversation() -> None:
    st.session_state.history = []
    st.session_state.display_turns = []
    st.session_state.turn_index = 0
    st.session_state.transcript_id = None
    st.session_state.transcript = None


def render_tool_activity(rounds: list[dict[str, Any]]) -> None:
    for round_record in rounds:
        for call in round_record["tool_calls"]:
            st.markdown(f"🔧 **{call['name']}**`({json.dumps(call['args'], ensure_ascii=False)})`")
        for event in round_record["tool_results"]:
            tool_result = event.get("result")
            is_error = isinstance(tool_result, dict) and tool_result.get("error")
            icon = "❌" if is_error else "✅"
            with st.expander(f"{icon} {event['tool']} result", expanded=bool(is_error)):
                st.json(tool_result)


init_state()

with st.sidebar:
    st.header("Agent settings")
    provider_name = st.selectbox("Provider", PROVIDERS, index=PROVIDERS.index("openai"))
    model_override = st.text_input("Model override (optional)", value="")
    version_label = st.text_input("Artifact version label", value=st.session_state.version_label)
    st.session_state.version_label = version_label
    history_window = st.slider("History window (turns)", 1, 10, 5)
    max_tool_rounds = st.slider("Max tool rounds", 1, 6, 4)

    if st.button("New conversation", use_container_width=True):
        reset_conversation()
        st.rerun()

    st.divider()
    system_prompt, openai_tools, artifact_version = load_artifacts(version_label)
    st.subheader("Artifact version")
    st.code(artifact_version.artifact_version, language="text")
    st.caption(f"prompt_hash: {artifact_version.prompt_hash[:16]}…")
    st.caption(f"tools_hash: {artifact_version.tools_hash[:16]}…")
    with st.expander("System prompt"):
        st.text(system_prompt)
    with st.expander(f"Declared tools ({len(openai_tools)})"):
        for tool in openai_tools:
            fn = tool["function"]
            st.markdown(f"**{fn['name']}** — {fn['description']}")

    if st.session_state.transcript_id:
        transcript_path = ROOT / "transcripts" / f"{st.session_state.transcript_id}.transcript.json"
        st.caption(f"Transcript: {transcript_path}")

st.title("IT Helpdesk Agent — Chat")
st.caption("Northstar Labs internal IT service desk assistant (demo UI)")

for turn in st.session_state.display_turns:
    with st.chat_message("user"):
        st.write(turn["user"])
    with st.chat_message("assistant"):
        render_tool_activity(turn.get("rounds", []))
        if turn.get("status") == "provider_error":
            st.error(f"Provider error: {turn.get('error')}")
        else:
            st.write(turn.get("assistant_text"))
        st.caption(
            f"status={turn.get('status')} · round(s)={len(turn.get('rounds', []))} · "
            f"artifact={turn.get('artifact_version')}"
        )

user_text = st.chat_input("Nhập yêu cầu IT helpdesk...")
if user_text:
    with st.chat_message("user"):
        st.write(user_text)

    st.session_state.turn_index += 1
    messages = [
        {"role": "system", "content": system_prompt},
        *trim_history(st.session_state.history, history_window),
        {"role": "user", "content": user_text},
    ]

    if st.session_state.transcript_id is None:
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        st.session_state.transcript_id = "_".join(
            [safe_slug(version_label), safe_slug(provider_name), "ui", timestamp]
        )
        st.session_state.transcript = {
            "transcript_id": st.session_state.transcript_id,
            **artifact_version_dict(artifact_version),
            "provider": provider_name,
            "model": model_override or None,
            "system_prompt": str(SYSTEM_PROMPT_PATH),
            "tools": str(TOOLS_PATH),
            "history_window": history_window,
            "max_tool_rounds": max_tool_rounds,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "turns": [],
        }

    turn_record: dict[str, Any] = {
        "turn_index": st.session_state.turn_index,
        "started_at": now_iso(),
        "user": user_text,
        "status": "started",
        "assistant_text": None,
        "rounds": [],
        "tool_events": [],
        "artifact_version": artifact_version.artifact_version,
    }

    with st.chat_message("assistant"):
        try:
            provider = get_provider(provider_name)
            with st.spinner("Agent is working..."):
                result = run_model_tool_loop(
                    provider=provider,
                    messages=messages,
                    tools=openai_tools,
                    model=model_override or None,
                    max_tool_rounds=max_tool_rounds,
                )
            turn_record.update(result)
            render_tool_activity(result["rounds"])
            assistant_text = result["assistant_text"]
            st.write(assistant_text)
            st.caption(
                f"status={result['status']} · round(s)={len(result['rounds'])} · "
                f"artifact={artifact_version.artifact_version}"
            )
            st.session_state.history.append({"role": "user", "content": user_text})
            st.session_state.history.append({"role": "assistant", "content": assistant_text})
        except Exception as exc:  # keep UI usable; surface the error as evidence
            turn_record.update({"status": "provider_error", "error": f"{type(exc).__name__}: {exc}"})
            st.error(f"Provider error: {turn_record['error']}")

    turn_record["ended_at"] = now_iso()
    st.session_state.display_turns.append(turn_record)
    st.session_state.transcript["turns"].append(turn_record)
    transcript_path = ROOT / "transcripts" / f"{st.session_state.transcript_id}.transcript.json"
    write_transcript(transcript_path, st.session_state.transcript)
    st.rerun()
