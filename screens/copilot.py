"""Page « AI Copilot »."""

from screens.common import *  # noqa: F401,F403
from screens.shared import *  # noqa: F401,F403


def render(ctx):
    """Affiche la page « AI Copilot »."""

    prospects, stage_names, scores = ctx.prospects, ctx.stage_names, ctx.scores

    st.title("AI Sales Copilot")

    st.caption(
        "Available now in each prospect file (panel « AI Copilot »): call preparation with sourced "
        "facts and hypotheses, and follow-up email drafts. Turn it on in Settings."
    )

    empty_state(
        "The AI chat is not available yet",
        "A chat to ask questions about all your prospects, interactions and pipeline — with sources "
        "and a clear distinction between facts and hypotheses — is planned for phase 10.2.",
        [{"label": "Open Settings", "icon": ":material/settings:", "on_click": go_to, "args": ("Settings",)}],
        icon=":material/auto_awesome:", key="copilot_empty",
    )
