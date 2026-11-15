"""Page « Objections »."""

from screens.common import *  # noqa: F401,F403
from screens.shared import *  # noqa: F401,F403


def _save_log_edits(editor_key, ids):
    """Enregistre les corrections du journal (callback du tableau).

    Concept : un callback s'exécute AVANT le script. Le message « flash » est
    donc affiché dans ce même passage ; puis le tableau reçoit une nouvelle
    clé (version) pour repartir des données à jour, sans relance supplémentaire
    qui effacerait le message.
    """

    edited_rows = (st.session_state.get(editor_key) or {}).get("edited_rows", {})
    saved = 0

    for row, changes in edited_rows.items():
        objection_id = int(ids[int(row)])

        if "Status" in changes:
            set_objection_status(objection_id, changes["Status"])
            saved += 1

        if "Category" in changes:
            ok, _ = change_objection_category(objection_id, changes["Category"])
            saved += ok

    if saved:
        st.session_state["flash"] = f"{saved} objection change(s) saved."

    st.session_state["objections_log_version"] = st.session_state.get("objections_log_version", 0) + 1


def render(ctx):
    """Affiche la page « Objections »."""

    prospects, stage_names, scores = ctx.prospects, ctx.stage_names, ctx.scores


    st.title("Objection Intelligence")
    st.caption(
        "Every objection your prospects actually expressed — and how to answer it next time. "
        "Nothing here is guessed: only recorded objections are counted."
    )

    show_flash_message()

    all_objections = get_objections()

    # ---------- FILTRES ----------

    col_period, col_vertical, _ = st.columns([1, 2, 2])

    period = col_period.selectbox(
        "Period", ["Last 30 days", "Last 90 days", "All time"], index=2, key="objections_period"
    )
    verticals_used = sorted({o["vertical"] for o in all_objections if o["vertical"]})
    selected_verticals = col_vertical.multiselect("Vertical", verticals_used, key="objections_verticals")

    objections = filter_period(
        all_objections, {"Last 30 days": 30, "Last 90 days": 90}.get(period)
    )

    if selected_verticals:
        objections = [o for o in objections if o["vertical"] in selected_verticals]

    # ---------- INDICATEURS ----------

    by_category = count_by(objections, "category")
    handled = sum(1 for o in objections if o["status"] == "Handled")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Objections", len(objections))
    col2.metric("Open", sum(1 for o in objections if o["status"] == "Open"))
    col3.metric("Handled rate", f"{round(handled / len(objections) * 100)} %" if objections else "—")
    col4.metric("Most frequent", by_category[0][0] if by_category else "—")

    tab_insights, tab_playbook, tab_log = st.tabs(
        ["Insights", "Playbook", "Log"], key="objections_tabs",
        on_change="rerun",   # garde l'onglet ouvert après une correction dans le journal
    )

    # ---------- ANALYSE ----------

    with tab_insights:

        if not objections:
            empty_state(
                "No objection recorded for this period",
                "Note objections when logging a call or an email, or from a prospect file. "
                "Only objections actually expressed are counted.",
                [LOG_ACTIVITY], icon=":material/forum:", key="objections_empty",
            )

        else:
            col_left, col_right = st.columns(2)

            with col_left:
                st.markdown("**Most frequent objections**")
                st.bar_chart(
                    pd.DataFrame(by_category, columns=["Category", "Objections"]).set_index("Category"),
                    horizontal=True,
                    sort=False,  # garde l'ordre des données : la plus fréquente en premier
                )

            with col_right:
                st.markdown("**Evolution per week**")
                trend = weekly_trend(objections)
                st.bar_chart(
                    pd.DataFrame.from_dict(trend, orient="index").fillna(0).astype(int),
                    stack=True,
                )

            def pivot(field, label):
                frame = pd.DataFrame(objections)
                frame[field] = frame[field].fillna("Unknown")
                table = pd.crosstab(frame[field], frame["category"])
                table["Total"] = table.sum(axis=1)
                return table.sort_values("Total", ascending=False).rename_axis(label)

            col_left, col_right = st.columns(2)

            with col_left:
                st.markdown("**By vertical**")
                st.dataframe(pivot("vertical", "Vertical"), width="stretch")

            with col_right:
                st.markdown("**By pipeline stage** (stage when the objection was raised)")
                st.dataframe(pivot("stage", "Stage"), width="stretch")

            st.markdown("**By company** (top 10)")
            st.dataframe(pivot("company_name", "Company").head(10), width="stretch")

            st.markdown("**How well each objection is handled**")
            st.dataframe(pd.DataFrame(resolution_by_category(objections)), width="stretch", hide_index=True)

    # ---------- PLAYBOOK : reponses recommandees ----------

    with tab_playbook:

        st.caption(
            "Write your recommended answer for each objection. It appears in the prospect file "
            "(“Prepare the next call”) whenever this objection was raised. "
            "Examples are anonymized: names, companies, emails and phone numbers are removed."
        )

        responses = get_objection_responses()
        counts = dict(count_by(all_objections, "category"))
        ordered = sorted(
            objection_categories(all_objections),
            key=lambda c: (-counts.get(c, 0), objection_categories(all_objections).index(c)),
        )

        for category in ordered:
            with st.container(border=True):

                st.markdown(f"**{category}** · {counts.get(category, 0)} time(s)")

                for example in anonymized_examples(all_objections, category, limit=3):
                    st.caption(f"“{example}”")

                with st.form(f"playbook_{category}"):

                    response = st.text_area(
                        "Recommended response",
                        value=responses.get(category, ""),
                        placeholder=PLAYBOOK_PLACEHOLDER,
                        height=110,
                        label_visibility="collapsed",
                    )

                    if st.form_submit_button("Save response"):
                        set_objection_response(category, response)
                        st.session_state["flash"] = f"Response saved for “{category}”."
                        st.rerun()

    # ---------- JOURNAL ----------

    with tab_log:

        if not objections:
            no_results("objection", key="objections_no_results")

        else:
            log = pd.DataFrame([
                {
                    "id": o["id"],
                    "Date": o["occurred_at_local"],
                    "Prospect": f"{o['first_name']} {o['last_name']}",
                    "Company": o["company_name"],
                    "Vertical": o["vertical"],
                    "Stage": o["stage"],
                    "Category": o["category"],
                    "Wording": o["verbatim"],
                    "Raised during": source_interaction(o) or "—",
                    "Status": o["status"],
                    "Source": OBJECTION_SOURCE_LABELS.get(o["source"], o["source"]),
                }
                for o in objections
            ])

            st.caption("Category and status can be corrected directly in the table.")

            editable = ["Category", "Status"]
            version = st.session_state.get("objections_log_version", 0)
            editor_key = f"objections_log_editor_{version}"

            st.data_editor(
                log,
                column_config={
                    "id": None,
                    "Category": st.column_config.SelectboxColumn(
                        "Category", options=objection_categories(all_objections), required=True),
                    "Status": st.column_config.SelectboxColumn("Status", options=OBJECTION_STATUSES, required=True),
                },
                disabled=[c for c in log.columns if c not in editable],
                hide_index=True,
                width="stretch",
                key=editor_key,
                on_change=_save_log_edits, args=(editor_key, log["id"].tolist()),
            )
