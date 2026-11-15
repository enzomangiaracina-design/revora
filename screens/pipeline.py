"""Page « Prospecting Pipeline »."""

from screens.common import *  # noqa: F401,F403
from screens.shared import *  # noqa: F401,F403
from screens.shared import _on_board_move, _on_board_open


def render(ctx):
    """Affiche la page « Prospecting Pipeline »."""

    prospects, stage_names, scores = ctx.prospects, ctx.stage_names, ctx.scores


    # ---------- EN-TETE : titre et choix de la vue (comme HubSpot) ----------

    col_title, col_view = st.columns([3, 2], vertical_alignment="bottom")

    col_title.title("Prospecting Pipeline")
    view = col_view.segmented_control(
        "View",
        ["Board", "Table", "Priorities", "Stages"],
        default="Board",
        key="pipeline_view",
        label_visibility="collapsed",
    ) or "Board"

    show_flash_message()

    stages = get_stages()
    summaries = get_activity_summary()

    if view != "Stages":

        # ---------- BARRE D'OUTILS : recherche, filtres, tri ----------

        col_search, col_filter, col_sort = st.columns([3, 1, 2], vertical_alignment="bottom")

        query = col_search.text_input(
            "Search", placeholder="Search name, company, email or phone",
            key="pipeline_search", label_visibility="collapsed"
        )

        with col_filter.popover("Filter", icon=":material/filter_list:", width="stretch"):
            selected_verticals = st.multiselect("Vertical", get_verticals(), key="pipeline_verticals")
            selected_temperatures = st.multiselect(
                "Temperature", ["Hot", "Warm", "Cold"], key="pipeline_temperatures"
            )
            min_score = st.slider("Minimum score", 0, 100, 0, key="pipeline_min_score")
            stale_days = st.number_input(
                "Inactive after (days)", min_value=1, value=DEFAULT_STALE_DAYS, key="stale_days"
            )
            show_closed = st.toggle("Show closed stages", key="pipeline_show_closed")

        sort_by = col_sort.selectbox(
            "Sort by", SORT_OPTIONS, key="pipeline_sort", label_visibility="collapsed"
        )

        # ---------- FILTRES RAPIDES (ligne sous la barre, comme HubSpot) ----------

        owners = sorted({p["owner"] for p in prospects if p["owner"]})

        def quick_label(name, key, default):
            value = st.session_state.get(key)
            if isinstance(value, list):
                value = ", ".join(value) if value else None
            return f"{name}: {value}" if value and value != default else name

        col_owner, col_created, col_activity, col_follow, _ = st.columns([1, 1, 1, 1, 1])

        with col_owner.popover(quick_label("Sales owner", "pipeline_owners", None), width="stretch"):
            selected_owners = st.multiselect("Sales owner", owners, key="pipeline_owners")

        with col_created.popover(quick_label("Create date", "qf_created", "Any time"), width="stretch"):
            created_filter = st.radio("Create date", CREATED_FILTERS, key="qf_created")

        with col_activity.popover(quick_label("Last activity", "qf_activity", "Any time"), width="stretch"):
            activity_filter = st.radio("Last activity", ACTIVITY_FILTERS, key="qf_activity")

        with col_follow.popover(quick_label("Next follow-up", "qf_follow_up", "Any"), width="stretch"):
            follow_up_filter = st.radio("Next follow-up", FOLLOW_UP_FILTERS, key="qf_follow_up")

        # ---------- APPLICATION DES FILTRES ET DU TRI ----------

        filtered = filter_prospects(prospects, query, selected_verticals, None, None, selected_owners)
        filtered = filter_quick(
            filtered, summaries, created_filter, activity_filter, follow_up_filter, stale_days
        )
        filtered = [
            p for p in filtered
            if scores[p["id"]]["global"] >= min_score
            and (not selected_temperatures or scores[p["id"]]["temperature"] in selected_temperatures)
        ]
        filtered = sort_prospects(filtered, sort_by, summaries, scores)

        visible_stages = [s for s in stages if show_closed or not s["is_closed"]]
        board = build_board(filtered, stages)
        hidden = sum(len(board[s["name"]]) for s in stages if s not in visible_stages)

        st.caption(
            f"{len(filtered)} of {len(prospects)} prospect(s)"
            + (f" · {hidden} in closed stages (hidden)" if hidden and view != "Priorities" else "")
        )

    # ---------- VUE KANBAN (glisser-deposer) ----------

    if view == "Board":

        pipeline_board(
            [
                {
                    "name": stage["name"],
                    "closed": stage["is_closed"],
                    "cards": [
                        build_card(p, summaries.get(p["id"]), scores.get(p["id"]), stale_days)
                        for p in board[stage["name"]]
                    ],
                }
                for stage in visible_stages
            ],
            key=BOARD_KEY,
            on_move=_on_board_move,
            on_open=_on_board_open,
        )

        st.caption("Drag a card to another column to change its stage. Click a company to open the prospect file.")

    # ---------- VUE TABLE ----------

    if view == "Table":

        rows = [
            {
                "Company": card["title"],
                "Contact": card["contact"],
                "Stage": p["status"],
                "Score": card["score"],
                "Temperature": card["temperature"],
                "Created": card["created"],
                "Last activity": card["last_activity"],
                "Next follow-up": card["next_follow_up"],
                "Owner": card["owner"],
            }
            for p in filtered
            if p["status"] in {s["name"] for s in visible_stages}
            for card in [build_card(p, summaries.get(p["id"]), scores.get(p["id"]), stale_days)]
        ]

        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        else:
            st.info("No prospect matches these filters.")

    # ---------- VUE PRIORISEE ----------

    if view == "Priorities":

        st.caption(
            "Urgency rules: overdue follow-up +3, follow-up due today +2, "
            "never contacted +1, inactive +1. Closed stages are excluded. "
            "Ties go to the highest score, then to the most advanced stage."
        )

        ranked = prioritize(
            filtered, stages, summaries, stale_days,
            scores={pid: result["global"] for pid, result in scores.items()}
        )

        if ranked:
            st.dataframe(
                pd.DataFrame([
                    {
                        "Priority": item["points"],
                        "Score": scores[item["prospect"]["id"]]["global"],
                        "Temperature": scores[item["prospect"]["id"]]["temperature"],
                        "Prospect": f"{item['prospect']['first_name']} {item['prospect']['last_name']}",
                        "Company": item["prospect"]["company_name"],
                        "Stage": item["prospect"]["status"],
                        "Why": " · ".join(item["reasons"]),
                        "Next follow-up": item["summary"].get("next_task_due"),
                        "Last activity": item["summary"].get("last_interaction_at"),
                    }
                    for item in ranked
                ]),
                width="stretch",
                hide_index=True
            )
        else:
            st.success("Nothing urgent: no overdue follow-up and no inactive prospect.")

    # ---------- GESTION DES ETAPES ----------

    if view == "Stages":

        st.caption(
            "Renaming a stage also updates every prospect in it. "
            "A closed stage means the prospect is no longer worked "
            "(hidden from the board by default, excluded from priorities)."
        )

        counts = {s["name"]: 0 for s in stages}
        for p in prospects:
            counts[p["status"]] = counts.get(p["status"], 0) + 1

        for index, stage in enumerate(stages):

            with st.container(border=True):

                c_name, c_count, c_closed, c_up, c_down, c_actions = st.columns(
                    [3, 1.2, 1, 0.6, 0.6, 1.4], vertical_alignment="center"
                )

                new_name = c_name.text_input(
                    "Stage name", value=stage["name"],
                    key=f"stage_name_{stage['id']}", label_visibility="collapsed"
                )

                c_count.caption(f"{counts.get(stage['name'], 0)} prospect(s)")

                closed = c_closed.checkbox(
                    "Closed", value=stage["is_closed"], key=f"stage_closed_{stage['id']}"
                )

                if closed != stage["is_closed"]:
                    set_stage_closed(stage["id"], closed)
                    st.rerun()

                if c_up.button("▲", key=f"stage_up_{stage['id']}", disabled=index == 0):
                    move_stage(stage["id"], -1)
                    st.rerun()

                if c_down.button("▼", key=f"stage_down_{stage['id']}", disabled=index == len(stages) - 1):
                    move_stage(stage["id"], 1)
                    st.rerun()

                if new_name.strip() != stage["name"]:
                    if c_actions.button("Rename", key=f"stage_rename_{stage['id']}", type="primary"):
                        ok, message = rename_stage(stage["id"], new_name)

                        if ok:
                            st.session_state["flash"] = message
                            st.rerun()
                        else:
                            st.error(message)

                with c_actions.popover("Delete"):

                    others = [s["name"] for s in stages if s["id"] != stage["id"]]
                    target = None

                    if counts.get(stage["name"]):
                        target = st.selectbox(
                            f"Move its {counts[stage['name']]} prospect(s) to",
                            others, key=f"stage_target_{stage['id']}"
                        )

                    if st.button("Delete stage", key=f"stage_delete_{stage['id']}", type="primary"):
                        ok, message = delete_stage(stage["id"], move_to=target)

                        if ok:
                            st.session_state["flash"] = message
                            st.rerun()
                        else:
                            st.error(message)

        with st.form("add_stage_form", clear_on_submit=True):

            col_name, col_closed, col_button = st.columns([3, 1, 1], vertical_alignment="bottom")

            stage_name = col_name.text_input("New stage")
            stage_closed = col_closed.checkbox("Closed stage")

            if col_button.form_submit_button("Add stage", width="stretch"):
                ok, message = add_stage(stage_name, stage_closed)

                if ok:
                    st.session_state["flash"] = message
                    st.rerun()
                else:
                    st.error(message)
