"""Page « Activity »."""

from screens.common import *  # noqa: F401,F403
from screens.shared import *  # noqa: F401,F403


def render(ctx):
    """Affiche la page « Activity »."""

    prospects, stage_names, scores = ctx.prospects, ctx.stage_names, ctx.scores


    st.title("Activity Manager")
    st.caption("Every call, email, LinkedIn message and note — and what to do next.")

    show_flash_message()

    today_start, today_end = period_bounds("Today")
    week_start, week_end = period_bounds("Last 7 days")

    today_counts = count_by_channel(get_all_interactions(start_date=today_start, end_date=today_end))
    week_total = len(get_all_interactions(start_date=week_start, end_date=week_end))
    task_groups = group_tasks(get_all_tasks())

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Calls today", today_counts["Call"])
    col2.metric("Emails today", today_counts["Email"])
    col3.metric("Interactions (7 days)", week_total)
    col4.metric("Due today", len(task_groups["today"]))
    col5.metric("Overdue", len(task_groups["overdue"]))

    tab_timeline, tab_follow_ups, tab_log = st.tabs(
        ["Timeline", "Follow-ups", "Log activity"],
        key="activity_tabs",
        on_change="rerun"
    )

    # ---------- TIMELINE GLOBALE ----------

    with tab_timeline:

        # État des synchronisations : d'où viennent (ou viendront) les interactions
        status_colors = {"connected": "green", "error": "red", "not_connected": "gray"}
        col_sync, col_settings = st.columns([5, 1], vertical_alignment="center")
        col_sync.caption(
            "Sync: " + " · ".join(
                f"**{line['label']}** :{status_colors[line['state']]}[{line['text']}]"
                for line in sync_status(get_integrations())
            )
        )
        col_settings.button("Settings", type="tertiary", icon=":material/settings:",
                            key="activity_sync_settings", on_click=go_to, args=("Settings",))

        col_period, col_channel, col_source, col_search = st.columns([1, 1.5, 1.5, 2])

        period = col_period.selectbox("Period", PERIODS, index=1)
        selected_channels = col_channel.multiselect("Type", CHANNELS)
        all_activity = get_all_interactions()
        selected_sources = col_source.multiselect("Source", source_options(all_activity),
                                                  key="activity_sources")
        search = col_search.text_input("Prospect or company")

        start, end = period_bounds(period)
        activity = filter_by_source(get_all_interactions(selected_channels, start, end), selected_sources)

        if search.strip():
            needle = search.strip().lower()
            activity = [
                item for item in activity
                if needle in f"{item['first_name']} {item['last_name']} {item['company_name'] or ''}".lower()
            ]

        st.caption(f"{len(activity)} interaction(s)")

        if activity:
            st.dataframe(
                pd.DataFrame([
                    {
                        "Date": item["occurred_at_local"],
                        "Prospect": f"{item['first_name']} {item['last_name']}",
                        "Company": item["company_name"],
                        "Type": item["channel"],
                        "Direction": item["direction"],
                        "Result": item["event_type"],
                        "Duration": format_duration(item["metadata"]),
                        "Subject": item["subject"],
                        "Notes": item["content"],
                        "Next step": item["outcome"],
                        "Source": source_label(item.get("provider")),
                    }
                    for item in activity
                ]),
                width="stretch",
                hide_index=True
            )
        elif not all_activity:
            empty_state(
                "No activity recorded yet",
                "Log your calls, emails, LinkedIn messages and notes to build each prospect's history.",
                [LOG_ACTIVITY], icon=":material/history:", key="activity_empty",
            )
        else:
            no_results("interaction", key="activity_no_results")

    # ---------- RELANCES ----------

    with tab_follow_ups:

        sections = [
            ("overdue", "Overdue"),
            ("today", "Today"),
            ("upcoming", "Upcoming"),
            ("no_date", "No due date"),
        ]

        if not any(task_groups[key] for key, _ in sections):
            empty_state(
                "No open follow-ups",
                "Schedule one from a prospect file, or set a follow-up date when logging an activity.",
                [LOG_ACTIVITY], icon=":material/event_available:", key="followups_empty",
            )

        for key, label in sections:
            if task_groups[key]:
                st.subheader(f"{label} ({len(task_groups[key])})")

                for task in task_groups[key]:
                    follow_up_card(task)

        if task_groups["done"]:
            with st.expander(f"Completed ({len(task_groups['done'])})"):
                for task in task_groups["done"]:
                    st.caption(
                        f"✓ {task['title']} · {task['first_name']} {task['last_name']}"
                        f" · due {task['due_at'] or 'no date'}"
                    )

    # ---------- SAISIE RAPIDE ----------

    with tab_log:

        if not prospects:
            empty_state(
                "No prospect yet",
                "Activities are always linked to a prospect. Add or import prospects first.",
                [ADD_PROSPECT, IMPORT_CSV], icon=":material/group:", key="log_empty",
            )

        else:
            options = {
                f"{p['first_name']} {p['last_name']} — {p['company_name']}": p["id"]
                for p in prospects
            }

            submitted, contact_id, data = interaction_form("log_activity_form", options)

            if submitted:
                ok, message = log_interaction(contact_id, data)

                if ok:
                    reset_form("log_activity_form")   # formulaire neuf ; en cas d'erreur la saisie reste
                    st.session_state["flash"] = message
                    st.rerun()
                else:
                    st.error(message)
