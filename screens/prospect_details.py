"""Page « Prospect Details »."""

from screens.common import *  # noqa: F401,F403
from screens.shared import *  # noqa: F401,F403


def render(ctx):
    """Affiche la page « Prospect Details »."""

    prospects, stage_names, scores = ctx.prospects, ctx.stage_names, ctx.scores


    origin = theme.NAV_DISPLAY.get(st.session_state.get("nav_page"), st.session_state.get("nav_page") or "Overview")

    st.button(
        f"Back to {origin}", icon=":material/arrow_back:", type="tertiary",
        on_click=close_prospect, key="prospect_back",
    )

    st.title("Prospect file")
    st.caption("Your complete commercial memory.")

    show_flash_message()

    if not prospects:
        st.info("Add a prospect before opening a prospect file.")

    else:

        prospect_options = {prospect_label(p): p["id"] for p in prospects}

        # Prospect choisi depuis le pipeline mais supprime entre-temps : on l'oublie
        if st.session_state.get("details_prospect") not in prospect_options:
            st.session_state.pop("details_prospect", None)

        selected_name = st.selectbox(
            "Select a prospect",
            list(prospect_options.keys()),
            key="details_prospect"
        )

        contact_id = prospect_options[selected_name]

        prospect = get_prospect_by_id(contact_id)

        if prospect:

            full_name = (
                prospect["first_name"] + " "
                + prospect["last_name"]
            )

            interactions = get_interactions(contact_id)
            tasks = get_tasks(contact_id)

            st.divider()

            st.title(full_name)
            st.caption(
                f"{prospect['job_title'] or 'Position not specified'}"
                f" · {prospect['company_name']}"
                f" · {prospect['vertical']}"
            )

            # CONTACT INFORMATION

            st.subheader("Contact information")

            col1, col2, col3, col4 = st.columns(4)

            col1.write("**Email**")
            col1.write(prospect["email"] or "Not provided")

            col2.write("**Phone**")
            col2.write(prospect["phone"] or "Not provided")

            col3.write("**LinkedIn**")
            if prospect.get("linkedin_url"):
                # Lien ouvert par VOUS dans votre navigateur : REVORA ne consulte pas LinkedIn
                col3.markdown(f"[Open profile]({prospect['linkedin_url']})")
            else:
                col3.write("Not provided")

            col4.write("**Status**")
            col4.write(prospect["status"])

            st.divider()

            # SCORE

            st.subheader("Score")

            result = scores.get(contact_id)

            if result:

                col1, col2, col3, col4 = st.columns(4)

                col1.metric("Global score", result["global"])
                col2.metric("Fit", result["fit"] if result["fit"] is not None else "n/a")
                col3.metric("Engagement", result["engagement"])
                col4.metric("Intent", result["intent"])

                st.markdown(score_label(result))

                with st.expander("Why this score?"):

                    st.caption(
                        "Observed = seen in recorded interactions · Confirmed = entered by you · "
                        "Rule = scoring rule applied. Nothing is inferred by AI."
                    )

                    st.dataframe(
                        pd.DataFrame([
                            {
                                "Dimension": item["dimension"].capitalize(),
                                "Signal": item["signal"],
                                "Points": item["points"],
                                "Type": item["type"].capitalize(),
                            }
                            for item in result["explanation"]
                        ]),
                        width="stretch",
                        hide_index=True
                    )

                history = score_changes(get_score_history(contact_id))

                with st.expander(f"Score history ({len(history)} change(s))"):

                    if len(history) > 1:
                        st.line_chart(
                            pd.DataFrame([
                                {
                                    "Date": row["calculated_at_local"],
                                    "Global": row["global_score"],
                                    "Engagement": row["engagement_score"],
                                    "Intent": row["intent_score"],
                                }
                                for row in history
                            ]).set_index("Date")
                        )

                    st.dataframe(
                        pd.DataFrame([
                            {
                                "Date": row["calculated_at_local"],
                                "Global": row["global_score"],
                                "Change": row["delta"],
                                "Fit": row["fit_score"],
                                "Engagement": row["engagement_score"],
                                "Intent": row["intent_score"],
                            }
                            for row in reversed(history)
                        ]),
                        width="stretch",
                        hide_index=True
                    )

            # QUALIFICATION (informations confirmees par le commercial)

            with st.form(f"qualification_form_{contact_id}"):

                st.markdown("**Qualification**")
                st.caption(
                    "Tick only what the prospect has explicitly confirmed. "
                    "These facts feed the Intent score."
                )

                labels = {
                    "need_identified": "Need identified",
                    "is_decision_maker": "Decision maker",
                    "budget_confirmed": "Budget confirmed",
                    "demo_requested": "Demo requested",
                }

                values = {}

                for column, field in zip(st.columns(len(QUALIFICATION_FIELDS)), QUALIFICATION_FIELDS):
                    values[field] = column.checkbox(labels[field], value=bool(prospect.get(field)))

                if st.form_submit_button("Save qualification", width="stretch"):
                    update_qualification(contact_id, values)
                    st.session_state["flash"] = "Qualification saved. Score updated."
                    st.rerun()

            # PREPARATION DU PROCHAIN APPEL (objections deja exprimees)

            preparation = call_preparation(contact_id)

            with st.expander(
                f"Prepare the next call — {len(preparation)} objection type(s) already raised",
                expanded=any(item["open"] for item in preparation),
            ):
                if not preparation:
                    st.caption("No objection recorded for this prospect yet.")

                for item in preparation:
                    st.markdown(
                        f"**{item['category']}** · raised {item['count']} time(s), "
                        f"last on {format_day(item['last_seen'])}"
                        + (f" · :orange[{item['open']} still open]" if item["open"] else "")
                    )

                    for verbatim in item["verbatims"]:
                        st.caption(f"“{verbatim}”")

                    if item["response"]:
                        st.info(item["response"])
                    else:
                        st.caption("No recommended response yet — add one in Objections › Playbook.")

            st.divider()

            # ACTIVITY COUNTERS (calcules automatiquement)

            counts = count_by_channel(interactions)
            summary = get_activity_summary().get(contact_id, {})

            col1, col2, col3, col4 = st.columns(4)

            col1.metric("Calls", counts["Call"])
            col2.metric("Emails", counts["Email"])
            col3.metric("LinkedIn", counts["LinkedIn"])
            col4.metric("Notes", counts["Note"])

            col1, col2 = st.columns(2)

            col1.metric(
                "Last interaction",
                summary.get("last_interaction_at") or "None yet"
            )
            col2.metric(
                "Next action",
                (
                    f"{summary['next_task_due'] or 'no date'} · {summary['next_task_title']}"
                    if summary.get("next_task_title") else "None scheduled"
                )
            )

            st.divider()

            # ADD INTERACTION

            st.subheader("Record an interaction")

            submitted, _, data = interaction_form(f"interaction_form_{contact_id}")

            if submitted:
                ok, message = log_interaction(contact_id, data)

                if ok:
                    st.session_state["flash"] = message
                    st.rerun()
                else:
                    st.error(message)

            st.divider()

            # ACTIVITY TIMELINE

            st.subheader("Activity timeline")

            if interactions:

                for item in interactions:

                    with st.container(border=True):

                        st.markdown(
                            f"**{item['channel']} · {item['event_type']}**"
                        )

                        details = [
                            item["occurred_at_local"],
                            item["direction"] or "Not specified",
                            format_duration(item["metadata"]),
                        ]

                        st.caption(" · ".join(d for d in details if d))

                        if item["subject"]:
                            st.write(f"**{item['subject']}**")

                        if item["content"]:
                            st.write(item["content"])

                        if item["outcome"]:
                            st.info(f"Outcome: {item['outcome']}")

            else:
                st.info("No interactions recorded yet.")

            st.divider()

            # OBJECTIONS DU PROSPECT

            st.subheader("Objections")

            prospect_objections = get_objections(contact_id)

            for objection in prospect_objections:
                with st.container(border=True):

                    col_text, col_status, col_delete = st.columns([5, 2, 1], vertical_alignment="center")

                    col_text.markdown(f"**{objection['category']}**")
                    col_text.caption(
                        f"{objection['occurred_at_local']} · stage: {objection['stage'] or '—'}"
                        f" · {objection['source']}"
                    )

                    if objection["verbatim"]:
                        col_text.write(f"“{objection['verbatim']}”")

                    new_status = col_status.selectbox(
                        "Status", OBJECTION_STATUSES,
                        index=OBJECTION_STATUSES.index(objection["status"])
                        if objection["status"] in OBJECTION_STATUSES else 0,
                        key=f"objection_status_{objection['id']}",
                        label_visibility="collapsed",
                    )

                    if new_status != objection["status"]:
                        set_objection_status(objection["id"], new_status)
                        st.session_state["flash"] = f"Objection marked as {new_status}."
                        st.rerun()

                    if col_delete.button(
                        "", icon=":material/delete:", key=f"objection_delete_{objection['id']}",
                        help="Delete this objection (entered by mistake)",
                    ):
                        delete_objection(objection["id"])
                        st.session_state["flash"] = "Objection deleted."
                        st.rerun()

            with st.form(f"objection_form_{contact_id}", clear_on_submit=True):

                st.caption(
                    "Record only what the prospect actually said. "
                    "Objections can also be noted when recording an interaction."
                )

                col1, col2 = st.columns([1, 2])

                category = col1.selectbox(
                    "Category", objection_categories(get_objections()),
                    index=None, accept_new_options=True, placeholder="Choose or type",
                )
                verbatim = col2.text_input("Wording (optional)")

                if st.form_submit_button("Add objection", width="stretch"):
                    ok, message = record_objection(contact_id, category, verbatim)

                    if ok:
                        st.session_state["flash"] = message
                        st.rerun()
                    else:
                        st.error(message)

            st.divider()

            # NEXT ACTION

            st.subheader("Next actions")

            with st.form("task_form"):

                task_title = st.text_input(
                    "Action",
                    placeholder="Example: Call Thomas back"
                )

                task_description = st.text_area(
                    "Description"
                )

                due_date = st.date_input(
                    "Due date"
                )

                save_task = st.form_submit_button(
                    "Schedule follow-up",
                    width="stretch"
                )

                if save_task:

                    if not task_title.strip():
                        st.error("Enter an action title.")

                    else:
                        create_task(
                            contact_id,
                            task_title,
                            task_description,
                            due_date.isoformat()
                        )

                        st.session_state["flash"] = "Follow-up scheduled."
                        st.rerun()

            groups = group_tasks(get_tasks(contact_id))
            open_tasks = groups["overdue"] + groups["today"] + groups["upcoming"] + groups["no_date"]

            if groups["overdue"]:
                st.warning(f"{len(groups['overdue'])} overdue follow-up(s).")

            for task in open_tasks:
                follow_up_card(task, show_prospect=False)

            if not open_tasks:
                st.info("No open follow-ups.")

            if groups["done"]:
                with st.expander(f"Completed follow-ups ({len(groups['done'])})"):
                    for task in groups["done"]:
                        st.caption(f"✓ {task['title']} · due {task['due_at'] or 'no date'}")
