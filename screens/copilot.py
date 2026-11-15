"""Page « AI Copilot »."""

from screens.common import *  # noqa: F401,F403
from screens.shared import *  # noqa: F401,F403


def render(ctx):
    """Affiche la page « AI Copilot »."""

    prospects, stage_names, scores = ctx.prospects, ctx.stage_names, ctx.scores

    st.title("AI Sales Copilot")

    empty_state(
        "The AI Copilot is not available yet",
        "It will answer questions about your prospects, interactions and pipeline, with sources "
        "and a clear distinction between facts and hypotheses. It needs an AI API key (phase 10).",
        icon=":material/auto_awesome:", key="copilot_empty",
    )
