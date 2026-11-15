"""Page « Prospects »."""

from screens.common import *  # noqa: F401,F403
from screens.shared import *  # noqa: F401,F403


def render(ctx):
    """Affiche la page « Prospects »."""

    prospects, stage_names, scores = ctx.prospects, ctx.stage_names, ctx.scores


    st.title("Prospect Intelligence")
    st.caption("Create, find, update and import your prospects.")

    show_flash_message()

    verticals = get_verticals()

    # key : Streamlit memorise l'onglet ouvert, qui reste affiche apres
    # une relance du script (ex. apres le depot d'un fichier CSV).
    # on_change="rerun" : permet aussi d'ouvrir un onglet depuis une autre page
    # (ex. bouton « Import a CSV file » de l'Overview) via st.session_state.
    tab_list, tab_new, tab_import = st.tabs(
        ["Database", "New prospect", "Import CSV"],
        key="prospects_tabs",
        on_change="rerun"
    )

    # ---------- RECHERCHE, FILTRES, MODIFICATION, SUPPRESSION ----------

    with tab_list:

        if not prospects:
            st.info("No prospects registered. Create one or import a CSV file.")

        else:
            col_search, col_vertical, col_status, col_source, col_owner = st.columns(
                [2, 1, 1, 1, 1]
            )

            query = col_search.text_input(
                "Search", placeholder="Name, company, email or phone"
            )
            selected_verticals = col_vertical.multiselect("Vertical", verticals)
            selected_statuses = col_status.multiselect("Status", stage_names)
            selected_sources = col_source.multiselect(
                "Source", sorted({p["source"] for p in prospects if p["source"]})
            )
            selected_owners = col_owner.multiselect(
                "Sales owner", sorted({p["owner"] for p in prospects if p["owner"]})
            )

            filtered = filter_prospects(
                prospects, query, selected_verticals, selected_statuses,
                selected_sources, selected_owners
            )

            st.caption(f"{len(filtered)} of {len(prospects)} prospects")

            if filtered:
                df = pd.DataFrame(filtered)
                df["Prospect"] = df["first_name"] + " " + df["last_name"]

                # Compteurs automatiques calcules depuis les interactions et relances
                summary = get_activity_summary()

                for column, key in [
                    ("Calls", "calls"),
                    ("Emails", "emails"),
                    ("Last activity", "last_interaction_at"),
                    ("Next follow-up", "next_task_due"),
                ]:
                    df[column] = df["id"].map(lambda i, k=key: summary.get(i, {}).get(k))

                df["Score"] = df["id"].map(lambda i: scores[i]["global"] if i in scores else None)
                df["Temperature"] = df["id"].map(lambda i: scores[i]["temperature"] if i in scores else None)

                st.dataframe(
                    df[[
                        "Prospect", "company_name", "vertical", "job_title",
                        "Score", "Temperature",
                        "email", "phone", "status", "Calls", "Emails",
                        "Last activity", "Next follow-up", "source", "owner", "linkedin_url"
                    ]].rename(columns={
                        "company_name": "Company",
                        "vertical": "Vertical",
                        "job_title": "Job title",
                        "email": "Email",
                        "phone": "Phone",
                        "status": "Status",
                        "source": "Source",
                        "owner": "Owner",
                        "linkedin_url": "LinkedIn"
                    }),
                    column_config={
                        "LinkedIn": st.column_config.LinkColumn("LinkedIn", display_text="Profile"),
                    },
                    width="stretch",
                    hide_index=True
                )
            else:
                st.info("No prospect matches these filters.")

            st.divider()
            st.subheader("Edit a prospect")

            edit_options = {
                f"{p['first_name']} {p['last_name']} — {p['company_name']}": p["id"]
                for p in prospects
            }

            selected_label = st.selectbox("Prospect to edit", list(edit_options))
            contact_id = edit_options[selected_label]
            prospect = get_prospect_by_id(contact_id)

            # La cle du formulaire inclut l'id : changer de prospect
            # recharge bien les valeurs pre-remplies.
            submitted, data = prospect_form(
                f"edit_form_{contact_id}", verticals, "Save changes", defaults=prospect
            )

            if submitted:
                ok, message = update_prospect(contact_id, data)

                if ok:
                    st.session_state["flash"] = message
                    st.rerun()
                else:
                    st.error(message)

            with st.expander("Delete this prospect"):

                counts = count_prospect_activity(contact_id)

                st.warning(
                    f"This permanently deletes **{selected_label}** together with "
                    f"{counts['interactions']} interaction(s), {counts['tasks']} "
                    f"follow-up(s), {counts['objections']} objection(s) and "
                    f"{counts['scores']} score record(s). "
                    "The company is kept. This cannot be undone."
                )

                confirmed = st.checkbox(
                    "I understand and want to delete this prospect permanently",
                    key=f"confirm_delete_{contact_id}"
                )

                if st.button(
                    "Delete prospect",
                    type="primary",
                    disabled=not confirmed,
                    key=f"delete_{contact_id}"
                ):
                    delete_prospect(contact_id)
                    st.session_state["flash"] = f"{selected_label} deleted."
                    st.rerun()

    # ---------- CREATION ----------

    with tab_new:

        submitted, data = prospect_form("create_form", verticals, "Create prospect")

        if submitted:
            ok, message = create_prospect(data)

            if ok:
                reset_form("create_form")
                st.session_state["flash"] = message
                st.rerun()
            else:
                st.error(message)

    # ---------- IMPORT CSV ----------

    with tab_import:

        st.write(
            "Required columns: **first_name, last_name, company_name**. "
            "Optional: vertical, email, phone, job_title, status, source, owner. "
            "French headers (prénom, nom, entreprise…) and HubSpot export "
            "headers are recognized."
        )

        st.download_button(
            "Download CSV template",
            data=CSV_TEMPLATE,
            file_name="revora_import_template.csv",
            mime="text/csv"
        )

        report = st.session_state.pop("import_report", None)

        if report:
            st.success(f"{report['created']} prospect(s) created.")

            if report["duplicates"]:
                with st.expander(f"{len(report['duplicates'])} duplicate(s) skipped"):
                    st.dataframe(pd.DataFrame(report["duplicates"]), hide_index=True)

            if report["errors"]:
                with st.expander(f"{len(report['errors'])} row(s) rejected"):
                    st.dataframe(pd.DataFrame(report["errors"]), hide_index=True)

        uploaded_file = st.file_uploader("CSV file", type=["csv"])

        if uploaded_file:
            try:
                import_df, ignored_columns = read_prospect_csv(uploaded_file)

            except ValueError as error:
                st.error(str(error))

            else:
                st.caption(f"{len(import_df)} row(s) detected.")

                if ignored_columns:
                    st.caption("Ignored columns: " + ", ".join(map(str, ignored_columns)))

                st.dataframe(import_df.head(20), width="stretch", hide_index=True)

                default_source = st.text_input(
                    "Source for rows without a source", value="Import CSV"
                )

                if st.button("Import prospects", type="primary"):
                    st.session_state["import_report"] = import_prospects(
                        import_df, default_source
                    )
                    st.rerun()
