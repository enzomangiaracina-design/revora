"""Page « AI Copilot » : chat sur toute la base (phase 10.2).

Lecture seule : le chat ne crée, ne modifie et ne supprime rien.
L'historique reste dans la session du navigateur (pas dans la base).
"""

from screens.common import *  # noqa: F401,F403
from screens.shared import *  # noqa: F401,F403

from core.copilot_service import (
    CHAT_SCHEMA,
    CHAT_SYSTEM_PROMPT,
    MAX_PROSPECTS,
    build_chat_prompt,
    build_global_context,
    validate_chat,
)

CHAT_KEY = "copilot_chat"

EXAMPLES = [
    "Who should I follow up with this week?",
    "Which interested prospects have had no contact for 10 days?",
    "Which objections come up most often?",
]


def _clear_chat():
    st.session_state[CHAT_KEY] = []


def _ask(question, ctx):
    """Envoie la question avec l'instantané de la base et range la réponse dans l'historique."""

    history = st.session_state.setdefault(CHAT_KEY, [])
    summaries = get_activity_summary()
    ranked = prioritize(
        ctx.prospects, get_stages(), summaries, DEFAULT_STALE_DAYS,
        scores={pid: result["global"] for pid, result in ctx.scores.items()},
    )
    context = build_global_context(
        ctx.prospects, ctx.scores, get_all_interactions(), get_objections(), get_all_tasks(), get_stages(),
        priority_ids=[item["prospect"]["id"] for item in ranked],
    )
    prompt = build_chat_prompt(question, [m for m in history if m.get("content")], context)
    history.append({"role": "user", "content": question})

    try:
        data, usage = ai_generate(CHAT_SYSTEM_PROMPT, prompt, CHAT_SCHEMA)
    except CopilotError as error:
        history.append({"role": "assistant", "content": "", "error": str(error)})
        return

    result = validate_chat(data, context)
    history.append({
        "role": "assistant", "content": result["answer"], "result": result, "usage": usage,
        "labels": context["labels"], "truncated": context["truncated"], "prices": ai_provider().PRICES,
    })


def _show_answer(index, message):
    if message.get("error"):
        st.error(message["error"])
        return

    result = message["result"]
    st.markdown(result["answer"] or "_No answer._")

    if result["facts"] or result["hypotheses"]:
        with st.expander(f"Sources ({len(result['facts'])} fact(s), {len(result['hypotheses'])} hypothesis(es))"):
            for title, items in (("Facts", result["facts"]), ("Hypotheses — to verify", result["hypotheses"])):
                if items:
                    st.markdown(f"*{title}*")
                for item in items:
                    st.markdown(f"- {item['text']}")
                    if item["sources"]:
                        st.caption(" · ".join(message["labels"][s] for s in item["sources"]))

    if result["prospects"]:
        with st.container(horizontal=True):
            names = st.session_state.get("_copilot_names", {})
            for pid in result["prospects"][:6]:
                st.button(
                    f"Open {names.get(pid, 'prospect')}", type="tertiary", icon=":material/open_in_new:",
                    key=f"copilot_open_{index}_{pid}", on_click=open_prospect, args=(pid,),
                )

    notes = []
    if result["dropped"]:
        notes.append(f":orange[{result['dropped']} item(s) removed: they cited no real record]")
    if message.get("truncated"):
        notes.append(f"only the {MAX_PROSPECTS} most relevant prospects were sent")
    usage = message["usage"]
    prices = message.get("prices")
    cost = ai_estimate_cost(usage, *prices) if prices else None
    notes.append(f"{usage['model']} · {usage['input_tokens']} tokens in, {usage['output_tokens']} out"
                 + (f" · ≈ ${cost}" if cost is not None else " · free tier"))
    st.caption(" · ".join(notes))


def render(ctx):
    """Affiche la page « AI Copilot »."""

    col_title, col_clear = st.columns([4, 1], vertical_alignment="bottom")
    col_title.title("AI Sales Copilot")

    if not (get_setting(AI_SETTING, False) and ai_is_configured()):
        empty_state(
            "The AI Copilot is off",
            "Ask questions about your prospects, interactions, follow-ups and objections — answers come "
            "with their sources. Add an API key to the .env file, then turn on « Enable AI features » in Settings.",
            [{"label": "Open Settings", "icon": ":material/settings:", "on_click": go_to, "args": ("Settings",)}],
            icon=":material/auto_awesome:", key="copilot_empty",
        )
        return

    if not ctx.prospects:
        empty_state(
            "No prospect to talk about yet",
            "The Copilot answers from your own data. Add or import prospects first.",
            [ADD_PROSPECT, IMPORT_CSV], icon=":material/auto_awesome:", key="copilot_no_data",
        )
        return

    provider = ai_provider()
    st.caption(
        f"Answers from your REVORA data only, with sources. Read-only: it never changes anything. "
        f"Each question sends a summary of up to {MAX_PROSPECTS} prospects to {provider.LABEL} "
        "(no email, phone or LinkedIn URL)."
    )
    if provider.FREE_TIER_NOTE:
        st.caption(f":orange[{provider.FREE_TIER_NOTE}]")

    history = st.session_state.setdefault(CHAT_KEY, [])
    st.session_state["_copilot_names"] = {p["id"]: f"{p['first_name']} {p['last_name']}" for p in ctx.prospects}

    if history:
        col_clear.button("New chat", icon=":material/add_comment:", type="tertiary",
                         on_click=_clear_chat, key="copilot_clear")

    if not history:
        st.markdown("**Try:**")
        with st.container(horizontal=True):
            for i, example in enumerate(EXAMPLES):
                if st.button(example, key=f"copilot_example_{i}"):
                    st.session_state["_copilot_pending"] = example

    for index, message in enumerate(history):
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.markdown(message["content"])
            else:
                _show_answer(index, message)

    question = st.chat_input("Ask about your prospects, follow-ups or objections…", key="copilot_input")
    question = question or st.session_state.pop("_copilot_pending", None)

    if question and question.strip():
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Reading your data…"):
                _ask(question.strip(), ctx)
        st.rerun()
