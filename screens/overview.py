"""Page « Overview »."""

from screens.common import *  # noqa: F401,F403
from screens.shared import *  # noqa: F401,F403

from database import get_active_snoozes, reschedule_task, snooze_prospect, unsnooze_prospect

ACTION_ICONS = {
    "Follow up": ":material/event:", "Call": ":material/call:", "Email": ":material/mail:",
    "LinkedIn": ":material/work:", "Prepare": ":material/assignment:",
}

DUE_COLORS = {"overdue": "red", "today": "orange"}

LATER = [("+1 day", 1), ("+3 days", 3), ("+1 week", 7)]


# ---------- Actions rapides du Today's Focus (callbacks) ----------

def _complete(task_id, title):
    complete_task(task_id)
    st.session_state["flash"] = f"Follow-up completed: {title}"


def _postpone(task_id, title, days):
    new_due = (date.today() + timedelta(days=days)).isoformat()
    reschedule_task(task_id, new_due)
    st.session_state["flash"] = f"Follow-up « {title} » moved to {new_due}."


def _set_aside(contact_id, name, days, reason_key):
    until = (date.today() + timedelta(days=days)).isoformat()
    snooze_prospect(contact_id, until, st.session_state.get(reason_key))
    st.session_state["flash"] = f"{name} set aside from Today's focus until {until}."


def _restore_all():
    unsnooze_prospect()
    st.session_state["flash"] = "All prospects set aside are back in Today's focus."


def render(ctx):
    """Affiche la page « Overview »."""

    prospects, stage_names, scores = ctx.prospects, ctx.stage_names, ctx.scores


    today = date.today()
    stages = get_stages()
    summaries = get_activity_summary()
    all_interactions = get_all_interactions()
    all_objections = get_objections()

    # ---------- 1. EN-TETE : ou suis-je ? ----------

    col_hello, col_search, col_add = st.columns([2, 3, 1.2], vertical_alignment="center")

    col_hello.markdown(f"### {greeting()}")
    col_hello.caption(long_date(today))

    search = col_search.text_input(
        "Search", placeholder="Search a prospect: name, company, email or phone",
        key="overview_search", label_visibility="collapsed",
    )

    if col_add.button("Add prospect", type="primary", icon=":material/person_add:", width="stretch"):
        add_prospect_dialog()

    show_flash_message()

    if search.strip():
        results = filter_prospects(prospects, search)[:5]

        with st.container(border=True):
            if not results:
                st.caption("No prospect matches this search.")

            for p in results:
                col_name, col_meta, col_open = st.columns([3, 4, 1], vertical_alignment="center")
                col_name.markdown(f"**{p['first_name']} {p['last_name']}**")
                col_meta.caption(f"{p['company_name']} · {p['status']} · {p['email'] or 'no email'}")
                col_open.button("Open", key=f"search_open_{p['id']}", on_click=open_prospect,
                                args=(p["id"],), width="stretch")

    if not prospects:
        empty_state(
            "Your prospect database is empty",
            "Add a first prospect or import a CSV file: priorities and activity will appear here.",
            [ADD_PROSPECT, IMPORT_CSV], icon=":material/group_add:", key="overview_empty",
        )

    # ---------- 2. INDICATEURS DU JOUR ----------

    today_kpis = compute_kpis(all_interactions, all_objections, today, today)
    yesterday = today - timedelta(days=1)
    yesterday_kpis = compute_kpis(all_interactions, all_objections, yesterday, yesterday)

    task_groups = group_tasks(get_all_tasks(), today)
    stale_days = st.session_state.get("stale_days", DEFAULT_STALE_DAYS)
    ranked_all = prioritize(
        prospects, stages, summaries, stale_days,
        scores={pid: result["global"] for pid, result in scores.items()},
    )

    # « Pas maintenant » : les prospects mis de côté par le commercial sortent du focus
    set_aside = get_active_snoozes(today.isoformat())
    ranked = [item for item in ranked_all if item["prospect"]["id"] not in set_aside]

    def vs_yesterday(key):
        change = delta(today_kpis[key], yesterday_kpis[key])
        return f"{change:+g} vs yesterday" if change else None

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Calls today", today_kpis["calls"], delta=vs_yesterday("calls"))
    col2.metric("Emails sent today", today_kpis["emails_sent"], delta=vs_yesterday("emails_sent"))
    overdue_count = len(task_groups["overdue"])

    col3.metric(
        "Follow-ups due",
        len(task_groups["today"]) + overdue_count,
        delta=f"{overdue_count} overdue" if overdue_count else None,
        delta_color="inverse",   # du retard s'affiche en rouge
        delta_arrow="off",
        help="Follow-ups due today plus overdue ones.",
    )
    col4.metric(
        "Priority prospects", len(ranked),
        help="Prospects in open stages with an overdue or due follow-up, never contacted, "
             f"or without activity for {stale_days} days.",
    )

    col_main, col_side = st.columns([2, 1], gap="large")

    # ---------- 3. TODAY'S FOCUS : qui, quoi, pourquoi ----------

    with col_main:

        theme.section_title("Today's focus")

        rows = focus_rows(ranked, scores, limit=8, today=today)

        if not rows:
            empty_state(
                "Nothing urgent today",
                "No overdue follow-up, no prospect left without contact. "
                "Use the pipeline to move prospects forward.",
                [OPEN_PIPELINE], icon=":material/task_alt:", key="focus_empty",
            )

        for row in rows:
            with st.container(border=True):

                col_who, col_action, col_when, col_buttons = st.columns(
                    [2.3, 3.2, 1.2, 1.9], vertical_alignment="center"
                )

                col_who.markdown(f"{PRIORITY_BADGES[row['priority']]} **{row['prospect']}**")
                col_who.caption(
                    f"{row['company']} · {row['stage']}"
                    + (f" · score {row['score']}" if row["score"] is not None else "")
                )

                # Quoi faire, et pourquoi (raison vérifiable : source et date)
                col_action.markdown(
                    f"{ACTION_ICONS.get(row['action_type'], ':material/bolt:')} **{row['next_action']}**"
                )
                col_action.caption(f"Why: {row['reason']}")

                # Quand
                color = DUE_COLORS.get(row["due_state"])
                col_when.markdown(f":{color}[{row['due']}]" if color else row["due"])
                col_when.caption(f"Last touch: {row['last_interaction']}")

                # Actions rapides : ouvrir, terminer, plus tard
                with col_buttons.container(horizontal=True, gap="small"):
                    st.button(
                        "", icon=":material/open_in_new:", key=f"focus_open_{row['id']}",
                        on_click=open_prospect, args=(row["id"],),
                        help=f"Open {row['prospect']}'s prospect file",
                    )

                    if row["task_id"] and row["due_state"] in ("overdue", "today"):
                        st.button(
                            "", icon=":material/check:", key=f"focus_done_{row['id']}",
                            on_click=_complete, args=(row["task_id"], row["task_title"]),
                            help=f"Mark « {row['task_title']} » as done",
                        )

                    with st.popover("", icon=":material/schedule:", help="Later: postpone or set aside",
                                    key=f"focus_later_{row['id']}"):

                        if row["task_id"]:
                            st.caption(f"Postpone « {row['task_title']} »")
                            with st.container(horizontal=True):
                                for label, days in LATER:
                                    st.button(
                                        label, key=f"focus_postpone_{row['id']}_{days}",
                                        on_click=_postpone, args=(row["task_id"], row["task_title"], days),
                                    )

                        st.caption("Not now: set this prospect aside from Today's focus")
                        reason_key = f"focus_reason_{row['id']}"
                        st.text_input("Reason (optional)", key=reason_key,
                                      placeholder="Example: on holiday until Monday")
                        with st.container(horizontal=True):
                            for label, days in LATER:
                                st.button(
                                    label, key=f"focus_aside_{row['id']}_{days}",
                                    on_click=_set_aside, args=(row["id"], row["prospect"], days, reason_key),
                                )

        if set_aside:
            col_note, col_restore = st.columns([3, 1], vertical_alignment="center")
            col_note.caption(
                f"{len(set_aside)} prospect(s) set aside with « Not now » "
                "(they come back automatically when the date is reached)."
            )
            col_restore.button("Show them again", type="tertiary", icon=":material/undo:",
                               on_click=_restore_all, key="focus_restore")

        if len(ranked) > len(rows):
            st.button(
                f"See all {len(ranked)} priorities in the pipeline", type="tertiary",
                icon=":material/arrow_forward:", on_click=go_to,
                args=("Prospecting Pipeline",), kwargs={"pipeline_view": "Priorities"},
            )

    # ---------- 4. RECENT ACTIVITY ----------

    with col_side:

        theme.section_title("Recent activity")

        feed = build_feed(
            all_interactions, all_objections, prospects, get_recent_score_changes(), limit=8
        )

        if not feed:
            empty_state(
                "No activity recorded yet",
                "Your calls, emails, objections and new prospects will appear here.",
                [LOG_ACTIVITY], icon=":material/history:", key="feed_empty",
            )

        with st.container(border=bool(feed)):

            for index, event in enumerate(feed):
                # Une ligne compacte : icone, evenement et heure ; le prospect en lien dessous
                st.markdown(
                    f"{FEED_ICONS.get(event['kind'], ':material/history:')} "
                    f"**{event['title']}** · :gray[{format_when(event['at'], today) or ''}]"
                )
                st.button(
                    f"{event['prospect']}" + (f" · {event['company']}" if event["company"] else ""),
                    key=f"feed_open_{index}_{event['contact_id']}", type="tertiary",
                    on_click=open_prospect, args=(event["contact_id"],),
                )

        # ---------- 5. PERFORMANCE SNAPSHOT ----------

        theme.section_title("Last 7 days")

        week_start, week_end = period_range(7, today)
        previous_start, previous_end = previous_range(week_start, week_end)
        week = compute_kpis(all_interactions, all_objections, week_start, week_end)
        previous_week = compute_kpis(all_interactions, all_objections, previous_start, previous_end)

        def snapshot_line(label, key, unit=""):
            """Une ligne compacte : valeur, libellé, écart avec les 7 jours précédents."""

            value = week[key]
            change = delta(value, previous_week[key])
            shown = "—" if value is None else f"{value}{unit}"
            suffix = " pts" if unit else ""

            if change:
                color = "green" if change > 0 else "red"
                trend_text = f" · :{color}[{change:+g}{suffix}]"
            else:
                trend_text = ""

            return f"**{shown}** {label}{trend_text}"

        with st.container(border=True):
            st.markdown(
                "  \n".join([
                    snapshot_line("connection rate", "connection_rate", " %"),
                    snapshot_line("reply rate", "reply_rate", " %"),
                    snapshot_line("meetings booked", "meetings"),
                ])
            )
            st.caption("Compared with the previous 7 days.")

        trend = daily_activity(all_interactions, today - timedelta(days=13), today)

        if any(day["Calls"] or day["Emails sent"] for day in trend):
            st.caption("Calls + emails sent per day (14 days)")
            st.line_chart(
                pd.DataFrame(
                    [{"Day": d["Day"][5:], "Touches": d["Calls"] + d["Emails sent"]} for d in trend]
                ).set_index("Day"),
                height=140,
            )

        st.button("Full performance", type="tertiary", icon=":material/arrow_forward:",
                  on_click=go_to, args=("Performance",))
