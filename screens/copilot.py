"""Page « AI Copilot »."""

from screens.common import *  # noqa: F401,F403
from screens.shared import *  # noqa: F401,F403


def render(ctx):
    """Affiche la page « AI Copilot »."""

    prospects, stage_names, scores = ctx.prospects, ctx.stage_names, ctx.scores

    st.title("AI Sales Copilot")
    st.info("Your AI assistant is coming next.")
