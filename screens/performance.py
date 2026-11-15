"""Page « Performance »."""

from screens.common import *  # noqa: F401,F403
from screens.shared import *  # noqa: F401,F403


def render(ctx):
    """Affiche la page « Performance »."""

    prospects, stage_names, scores = ctx.prospects, ctx.stage_names, ctx.scores


    col_title, col_period = st.columns([3, 2], vertical_alignment="bottom")

    col_title.title("Performance")
    period_label = col_period.segmented_control(
        "Period", list(PERFORMANCE_PERIODS), default="Last 30 days",
        key="performance_period", label_visibility="collapsed",
    ) or "Last 30 days"

    start, end = period_range(PERFORMANCE_PERIODS[period_label])
    previous_start, previous_end = previous_range(start, end)

    st.caption(
        f"{start.strftime('%d/%m/%Y')} – {end.strftime('%d/%m/%Y')} · "
        f"compared with the previous {PERFORMANCE_PERIODS[period_label]} days · "
        "based only on recorded interactions"
    )

    # Filtre par commercial : celui du prospect (pas encore l'auteur de chaque interaction)
    owners = owner_options(prospects)
    selected_owners = []

    if owners:
        col_owner, _ = st.columns([2, 3])
        selected_owners = col_owner.multiselect(
            "Sales owner", owners, key="performance_owners", placeholder="All sales owners",
            help="Filters on the prospect's sales owner. Who logged each interaction "
                 "is not recorded yet (multi-user: phase 11).",
        )

    prospects = filter_by_owner(prospects, prospects, selected_owners)
    all_interactions = filter_by_owner(get_all_interactions(), ctx.prospects, selected_owners)
    all_objections = filter_by_owner(get_objections(), ctx.prospects, selected_owners)

    current = compute_kpis(all_interactions, all_objections, start, end)
    previous = compute_kpis(all_interactions, all_objections, previous_start, previous_end)
    low_volume = low_volume_rates(current)

    def kpi(column, label, key, unit="", inverse=False, help_text=None):
        """Carte KPI : un chiffre, un libellé, la comparaison avec la période précédente."""

        value = current[key]
        change = delta(value, previous[key])

        # Faible volume : le taux reste affiché, mais signalé comme fragile
        if key in low_volume:
            label = f":orange[:material/warning:] {label}"   # icône avant : jamais tronquée
            help_text = (f"{help_text} " if help_text else "") + (
                f"Based on few data ({low_volume[key]}): treat with care.")

        column.metric(
            label,
            "—" if value is None else f"{value}{unit}",
            delta=None if not change else f"{change:+g}{' pts' if unit == ' %' else ''}",
            delta_color="inverse" if inverse else "normal",
            help=help_text,
        )

    st.markdown("**Activity**")
    col1, col2, col3, col4, col5 = st.columns(5)
    kpi(col1, "Calls made", "calls")
    kpi(col2, "Calls / working day", "calls_per_day")
    kpi(col3, "Connection rate", "connection_rate", " %",
        help_text="Outbound calls that reached a conversation / outbound calls.")
    kpi(col4, "Emails sent", "emails_sent")
    kpi(col5, "Emails / working day", "emails_per_day")

    st.markdown("**Results**")
    col1, col2, col3, col4, col5 = st.columns(5)
    kpi(col1, "Reply rate", "reply_rate", " %",
        help_text="Contacted prospects who replied (inbound email, call or LinkedIn) / contacted prospects.")
    kpi(col2, "Meetings booked", "meetings")
    kpi(col3, "Conversion rate", "conversion_rate", " %",
        help_text="Contacted prospects who booked a meeting / contacted prospects.")
    kpi(col4, "Objections", "objections", inverse=True)
    kpi(col5, "Days between follow-ups", "follow_up_delay", inverse=True,
        help_text="Average days between two successive outbound touches on the same prospect.")

    st.markdown("**LinkedIn** (recorded manually)")
    col1, col2, col3, _, _ = st.columns(5)
    kpi(col1, "Connection requests", "linkedin_requests")
    kpi(col2, "Acceptance rate", "linkedin_acceptance_rate", " %",
        help_text="Prospects invited in the period who then accepted / prospects invited.")
    kpi(col3, "LinkedIn messages sent", "linkedin_messages")

    if low_volume:
        st.caption(
            f":orange[Low volume — fewer than {MIN_SAMPLE} data points behind: "
            + ", ".join(low_volume.values())
            + ". These rates can change a lot with one more result.]"
        )

    st.caption(
        f"{current['contacted']} prospect(s) contacted · {current['replied']} replied · "
        f"{current['emails_received']} email(s) received · {current['working_days']} working day(s)"
    )

    st.divider()

    st.markdown("**Daily activity**")
    activity_rows = daily_activity(all_interactions, start, end)

    if any(row["Calls"] or row["Emails sent"] or row["Replies"] for row in activity_rows):
        st.bar_chart(pd.DataFrame(activity_rows).set_index("Day"), stack=False)
    else:
        empty_state(
            "No interaction recorded in this period",
            "Indicators are calculated only from recorded activity. Choose a longer period or log activity.",
            [LOG_ACTIVITY], icon=":material/bar_chart:", key="performance_daily_empty",
        )

    st.markdown("**By vertical**")
    vertical_rows = by_vertical(all_interactions, all_objections, prospects, start, end)

    if vertical_rows:
        st.dataframe(pd.DataFrame(vertical_rows), width="stretch", hide_index=True)
    else:
        empty_state(
            "No prospect contacted in this period",
            "The table by vertical fills in as soon as prospects are contacted.",
            icon=":material/table_chart:", key="performance_vertical_empty",
        )

    with st.expander("How are these indicators calculated?"):
        st.markdown(
            "- **Calls made**: outbound calls. **Per working day**: divided by Monday–Friday days.\n"
            "- **Connection rate**: outbound calls with result *Completed, Positive response, Objection, "
            "Meeting booked* or *Information shared*, divided by outbound calls.\n"
            "- **Reply rate**: prospects contacted outbound in the period who then sent an inbound "
            "email, call or LinkedIn message, divided by prospects contacted.\n"
            "- **Meetings booked**: interactions whose result is *Meeting booked*.\n"
            "- **Conversion rate**: contacted prospects who booked a meeting in the period.\n"
            "- **Days between follow-ups**: average gap between two successive outbound touches "
            "on the same prospect.\n"
            "- A rate shows **—** when there is nothing to divide (never a misleading 0 %).\n"
            f"- **Low volume**: a rate based on fewer than {MIN_SAMPLE} calls, contacted or invited "
            "prospects is flagged: it is too fragile to compare.\n"
            "- **Sales owner** filter: uses the prospect's owner, not who logged the interaction.\n"
            "- **Performance by sequence** is not available yet: REVORA has no sequences "
            "(planned with the HubSpot connection)."
        )
