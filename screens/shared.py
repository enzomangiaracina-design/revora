"""Outils d'interface partagés entre les pages (formulaires, cartes, navigation)."""

from screens.common import *  # noqa: F401,F403


def show_flash_message():
    """Affiche le message laisse par l'action precedente.

    Concept : st.rerun() relance tout le script, ce qui efface un st.success()
    affiche juste avant. On range donc le message dans st.session_state
    (une memoire qui survit aux relances) et on l'affiche au tour suivant.
    """

    message = st.session_state.pop("flash", None)

    if message:
        st.success(message)


def reset_form(form_key):
    """Vide un formulaire prospect APRES une creation reussie.

    Concept : Streamlit garde les valeurs d'un formulaire tant que son nom
    (key) ne change pas. En ajoutant un numero de version au nom, on obtient
    un formulaire neuf et vide. En cas d'erreur, on ne l'appelle pas : les
    valeurs saisies restent la pour etre corrigees.
    """

    version_key = f"_form_version_{form_key}"
    st.session_state[version_key] = st.session_state.get(version_key, 0) + 1


# ==========================================
# UTILISATEUR ACTIF (phase 11.1)
# ==========================================

USER_KEY = "user"   # clé du menu « Signed in as » (et paramètre ?user=<id> de l'URL)


# ---------- Vraie connexion (phase 12.1) ----------

def auth_enabled():
    """True si une section [auth] complète existe dans .streamlit/secrets.toml."""

    return auth_is_configured(st.secrets)


def _identity_claims():
    """Identité renvoyée par le fournisseur (dictionnaire), ou None si personne n'est connecté."""

    info = st.user.to_dict()          # .get() : la clé peut manquer (aucune session, tests)

    return info if info.get("is_logged_in") else None


def require_login(users):
    """Porte d'entrée : arrête la page tant que la personne n'est pas connectée ET dans l'équipe.

    Retourne l'utilisateur REVORA correspondant à l'email du compte connecté.
    """

    claims = _identity_claims()

    if not claims:
        st.title("Sign in to REVORA")
        st.caption("Use your work Google or Microsoft account. REVORA never sees or stores your password.")
        if st.button("Sign in", type="primary", icon=":material/login:"):
            st.login()
        st.stop()

    user, message = resolve_user(users, claims)

    if not user:
        st.title("Access not granted")
        st.warning(message, icon=":material/lock:")
        if st.button("Sign out", icon=":material/logout:"):
            st.logout()
        st.stop()

    st.session_state[USER_KEY] = user["id"]     # même clé que « Signed in as » (propriétaire par défaut…)

    return user


def sidebar_identity(user):
    """Barre latérale avec la vraie connexion : qui est connecté, et « Sign out »."""

    st.sidebar.caption(f"Signed in as **{user['name']}** · {user['role']}")

    if st.sidebar.button("Sign out", icon=":material/logout:", type="tertiary", key="sign_out"):
        st.logout()


def signed_in_user(users):
    """Menu « Signed in as » de la barre latérale. Retourne l'utilisateur choisi, ou None.

    Prototype sans mot de passe. Le choix est gardé dans l'URL (?user=3, un
    identifiant, jamais le nom) : il survit au rechargement de la page.
    """

    active = [u for u in users if u["active"]]

    if not active:
        st.sidebar.caption("No team yet: add it in Settings › Team.")
        return None

    labels = {u["id"]: f"{u['name']} · {u['role']}" for u in active}

    # Page rechargée : on retrouve le choix à partir de l'URL (?user=3)
    if USER_KEY not in st.session_state:
        from_url = st.query_params.get(USER_KEY, "")
        st.session_state[USER_KEY] = int(from_url) if from_url.isdigit() and int(from_url) in labels else None

    # Utilisateur désactivé entre-temps : plus proposé
    if st.session_state[USER_KEY] not in labels:
        st.session_state[USER_KEY] = None

    chosen = st.sidebar.selectbox(
        "Signed in as", list(labels), format_func=labels.get,
        placeholder="Choose your name", key=USER_KEY, on_change=_remember_user,
    )

    return next((u for u in active if u["id"] == chosen), None)


def _remember_user():
    """Callback : garde l'identifiant (jamais le nom) dans l'URL."""

    chosen = st.session_state.get(USER_KEY)

    if chosen is None:
        st.query_params.pop(USER_KEY, None)
    else:
        st.query_params[USER_KEY] = str(chosen)


# ---------- « Mes prospects » (phase 11.2) ----------

SCOPE_KEY = "scope"          # choix partagé par l'Overview, la liste Prospects et le Pipeline
SCOPE_OWNER_KEY = "_scope_user"


def _sync_scope(widget_key):
    st.session_state[SCOPE_KEY] = st.session_state[widget_key]


def scope_prospects(ctx, container, key):
    """Bouton « My prospects / Everyone ». Retourne (prospects visibles, True si « mes prospects »).

    Affiché seulement si quelqu'un est choisi dans « Signed in as ». Le choix est
    partagé entre les pages ; il revient au défaut du rôle quand on change d'utilisateur.
    """

    if not ctx.user:
        return ctx.prospects, False

    if st.session_state.get(SCOPE_OWNER_KEY) != ctx.user["id"]:
        st.session_state[SCOPE_KEY] = default_scope(ctx.user)
        st.session_state[SCOPE_OWNER_KEY] = ctx.user["id"]

    widget_key = f"{key}_scope"
    st.session_state[widget_key] = st.session_state[SCOPE_KEY]     # même choix sur toutes les pages
    container.segmented_control(
        "Show", [MINE, EVERYONE], key=widget_key, required=True, label_visibility="collapsed",
        on_change=_sync_scope, args=(widget_key,),
        help=f"My prospects: those whose sales owner is {ctx.user['name']}.",
    )

    if st.session_state[SCOPE_KEY] == MINE:
        return owned_by(ctx.prospects, ctx.user["name"]), True

    return ctx.prospects, False


def show_everyone():
    """Callback : repasse la vue sur « Everyone »."""

    st.session_state[SCOPE_KEY] = EVERYONE


def current_user_name():
    """Nom de l'utilisateur choisi dans « Signed in as », ou None."""

    chosen = st.session_state.get(USER_KEY)
    user = next((u for u in get_users(active_only=True) if u["id"] == chosen), None)

    return user["name"] if user else None


def prospect_form(form_key, verticals, submit_label, defaults=None):
    """Formulaire prospect, vide (creation) ou pre-rempli (modification).

    Les champs sont poses ligne par ligne (une paire de colonnes par ligne)
    pour que la touche Tab suive l'ordre de lecture : Prenom -> Nom ->
    Entreprise -> Verticale...

    Retourne (bouton_clique, donnees_saisies).
    """

    defaults = defaults or {}

    vertical_options = list(verticals)
    if defaults.get("vertical") and defaults["vertical"] not in vertical_options:
        vertical_options.append(defaults["vertical"])

    status_options = list(get_stage_names())
    if defaults.get("status") and defaults["status"] not in status_options:
        status_options.append(defaults["status"])

    version = st.session_state.get(f"_form_version_{form_key}", 0)

    # clear_on_submit=False : une erreur de validation ne doit pas effacer la saisie
    with st.form(f"{form_key}_{version}", clear_on_submit=False):

        col1, col2 = st.columns(2)

        first_name = col1.text_input("First name *", value=defaults.get("first_name") or "")
        last_name = col2.text_input("Last name *", value=defaults.get("last_name") or "")

        col1, col2 = st.columns(2)

        company_name = col1.text_input("Company *", value=defaults.get("company_name") or "")
        vertical = col2.selectbox(
            "Vertical",
            vertical_options,
            index=(
                vertical_options.index(defaults["vertical"])
                if defaults.get("vertical") else None
            ),
            accept_new_options=True,
            placeholder="Choose or type a new vertical"
        )

        col1, col2 = st.columns(2)

        job_title = col1.text_input("Job title", value=defaults.get("job_title") or "")
        status = col2.selectbox(
            "Status",
            status_options,
            index=status_options.index(defaults.get("status") or status_options[0])
        )

        col1, col2 = st.columns(2)

        email = col1.text_input("Email", value=defaults.get("email") or "")
        phone = col2.text_input("Phone", value=defaults.get("phone") or "")

        col1, col2 = st.columns(2)

        source = col1.text_input(
            "Source", value=defaults.get("source") or "",
            placeholder="Example: HubSpot list, trade show, referral"
        )
        # Phase 11 : propriétaire choisi dans l'équipe (sinon saisie libre, comme avant).
        # Nouveau prospect : l'utilisateur actif par défaut.
        team = get_users(active_only=True)
        current_owner = defaults.get("owner") if defaults else current_user_name()

        if team:
            choices = owner_choices(team, current_owner)
            owner = col2.selectbox(
                "Sales owner", choices,
                index=next((i for i, n in enumerate(choices) if n.casefold() == (current_owner or "").casefold()), 0),
                format_func=lambda name: name or UNASSIGNED_LABEL,
            )
        else:
            owner = col2.text_input("Sales owner", value=current_owner or "",
                                    help="Tip: add your team in Settings › Team to choose from a list.")

        linkedin_url = st.text_input(
            "LinkedIn profile URL", value=defaults.get("linkedin_url") or "",
            placeholder="https://www.linkedin.com/in/…  (copied by you — REVORA never visits LinkedIn)"
        )

        submitted = st.form_submit_button(submit_label, width="stretch")

    data = {
        "linkedin_url": linkedin_url,
        "first_name": first_name,
        "last_name": last_name,
        "company_name": company_name,
        "vertical": vertical,
        "job_title": job_title,
        "status": status,
        "email": email,
        "phone": phone,
        "source": source,
        "owner": owner,
    }

    return submitted, data


def interaction_form(form_key, prospect_options=None, defaults=None):
    """Formulaire d'enregistrement (ou de correction) d'une interaction.

    prospect_options : {libelle: contact_id}. S'il est fourni, le formulaire
    propose de choisir le prospect (page Activity) ; sinon le prospect est
    deja connu (fiche prospect).
    defaults : interaction existante a corriger. Les champs « relance » et
    « objection » sont alors masques (ils creent d'autres elements).

    Concept : le formulaire n'est PAS vide automatiquement a l'envoi
    (clear_on_submit=False). En cas d'erreur, la saisie reste la pour etre
    corrigee ; apres un succes, l'appelant appelle reset_form(form_key).

    Retourne (bouton_clique, contact_id ou None, donnees_saisies).
    """

    defaults = defaults or {}
    editing = bool(defaults)
    version = st.session_state.get(f"_form_version_{form_key}", 0)

    def pick(options, value):
        return options.index(value) if value in options else 0

    with st.form(f"{form_key}_{version}", clear_on_submit=False):

        contact_label = None

        if prospect_options:
            contact_label = st.selectbox("Prospect", list(prospect_options))

        col1, col2, col3 = st.columns(3)

        channel = col1.selectbox("Interaction type", CHANNELS, index=pick(CHANNELS, defaults.get("channel")))
        direction = col2.selectbox("Direction", DIRECTIONS, index=pick(DIRECTIONS, defaults.get("direction")))
        event_type = col3.selectbox(
            "Result", RESULTS, index=pick(RESULTS, defaults.get("event_type")),
            help="LinkedIn actions (connection request, accepted, InMail) require the LinkedIn type; "
                 "their direction is set automatically.",
        )

        when = datetime.fromisoformat(defaults["occurred_at_local"]) if defaults.get("occurred_at_local") else None
        seconds = (defaults.get("metadata") or {}).get("duration_seconds") or 0

        col1, col2, col3 = st.columns(3)

        day = col1.date_input("Date", value=when.date() if when else "today", max_value=date.today())
        time = col2.time_input("Time", value=when.time() if when else "now")
        duration = col3.number_input(
            "Call duration (minutes)", min_value=0.0, step=1.0, value=round(seconds / 60, 1),
            help="Calls only. Leave 0 if unknown."
        )

        subject = st.text_input("Subject", value=defaults.get("subject") or "")

        content = st.text_area(
            "Notes / interaction details", value=defaults.get("content") or "",
            placeholder="What happened during this interaction?"
        )

        col1, col2 = st.columns(2)

        outcome = col1.text_input(
            "Next step", value=defaults.get("outcome") or "",
            placeholder="Example: Call back next Tuesday"
        )

        follow_up_date = objection_category = objection_verbatim = None

        if not editing:
            follow_up_date = col2.date_input(
                "Follow-up date (optional)", value=None,
                help="Creates a follow-up task with the next step as title."
            )

            col1, col2 = st.columns(2)

            objection_category = col1.selectbox(
                "Objection raised (optional)",
                objection_categories(get_objections()),
                index=None,
                accept_new_options=True,
                placeholder="None — only if the prospect actually said it",
            )
            objection_verbatim = col2.text_input(
                "Objection wording (optional)",
                placeholder="What the prospect said, in their words",
            )

        submitted = st.form_submit_button("Save changes" if editing else "Save interaction", width="stretch")

    data = {
        "channel": channel,
        "direction": direction,
        "event_type": event_type,
        "subject": subject,
        "content": content,
        "outcome": outcome,
        "occurred_at": datetime.combine(day, time),
        "duration_minutes": duration,
        "follow_up_date": follow_up_date,
        "objection_category": objection_category,
        "objection_verbatim": objection_verbatim,
    }

    contact_id = prospect_options[contact_label] if prospect_options else None

    return submitted, contact_id, data


BOARD_KEY = "pipeline_board"


def prospect_label(prospect):
    """Libelle d'un prospect dans les listes de choix (doit rester identique partout)."""

    return f"{prospect['first_name']} {prospect['last_name']} — {prospect['company_name']}"


def open_prospect(contact_id):
    """Ouvre la fiche d'un prospect (a appeler depuis un callback).

    Concept : un "callback" s'execute AVANT que la page soit redessinee.
    C'est le seul moment ou l'on peut changer la valeur d'un widget deja
    affiche (ici la navigation et le choix du prospect).
    """

    prospect = get_prospect_by_id(contact_id)

    if prospect:
        # La fiche s'ouvre PAR-DESSUS la page en cours (blueprint : la fiche n'est
        # pas une entree de menu). La page d'origine reste selectionnee pour le retour.
        st.session_state["prospect_open"] = True
        st.session_state["details_prospect"] = prospect_label(prospect)


def close_prospect():
    """Ferme la fiche prospect et revient a la page d'origine (callback)."""

    st.session_state["prospect_open"] = False


def open_from_table(table_name, ids):
    """Callback d'un tableau cliquable : ouvre la fiche de la ligne choisie.

    ids : identifiants des prospects, dans l'ordre des lignes du tableau.
    Apres ouverture, le tableau recoit un nouveau numero de version : sa
    selection est remise a zero (sinon la fiche se rouvrirait au retour).
    """

    version_key = f"_table_version_{table_name}"
    state = st.session_state.get(f"{table_name}_{st.session_state.get(version_key, 0)}")
    rows = (state or {}).get("selection", {}).get("rows", [])

    if rows and rows[0] < len(ids):
        open_prospect(ids[rows[0]])
        st.session_state[version_key] = st.session_state.get(version_key, 0) + 1


def table_key(table_name):
    """Cle actuelle (versionnee) d'un tableau cliquable."""

    return f"{table_name}_{st.session_state.get(f'_table_version_{table_name}', 0)}"


# ---------- P2.4 : changement d'étape, avec confirmation vers une étape fermée ----------

PENDING_STAGE = "pending_stage_change"


def request_stage_change(contact_id, stage_name):
    """Déplace un prospect, sauf vers une étape FERMÉE : on demande d'abord confirmation.

    Concept : une étape fermée (Perdu, Disqualifié…) sort le prospect du tableau
    et des priorités. Une erreur de glisser-déposer passerait inaperçue : la
    demande est donc mise en attente (st.session_state) jusqu'à confirmation.
    Retourne True si le changement est appliqué tout de suite.
    """

    stage = next((s for s in get_stages() if s["name"] == stage_name), None)
    current = get_prospect_by_id(contact_id)

    if stage and stage["is_closed"] and current and current["status"] != stage_name:
        st.session_state[PENDING_STAGE] = {
            "id": contact_id,
            "name": f"{current['first_name']} {current['last_name']}",
            "from": current["status"],
            "stage": stage_name,
            "definition": stage.get("definition"),
        }
        return False

    ok, message = set_prospect_stage(contact_id, stage_name)
    st.session_state["flash"] = message if ok else f"Error: {message}"
    return ok


def _confirm_stage_change():
    pending = st.session_state.pop(PENDING_STAGE, None)

    if pending:
        ok, message = set_prospect_stage(pending["id"], pending["stage"])
        st.session_state["flash"] = message if ok else f"Error: {message}"


def _cancel_stage_change():
    pending = st.session_state.pop(PENDING_STAGE, None)

    if pending:
        st.session_state["flash"] = f"{pending['name']} stays in « {pending['from']} »."
        # Le tableau est redessiné à partir des données : la carte revient à sa place
        st.session_state["board_revision"] = st.session_state.get("board_revision", 0) + 1


def stage_change_confirmation():
    """Bandeau de confirmation d'un déplacement vers une étape fermée (s'il y en a un)."""

    pending = st.session_state.get(PENDING_STAGE)

    if not pending:
        return

    with st.container(border=True):
        st.markdown(
            f":orange[:material/warning:] Move **{pending['name']}** from « {pending['from']} » "
            f"to the closed stage **« {pending['stage']} »**?"
        )
        st.caption(
            "A closed stage means the prospect is no longer worked: it leaves the board "
            "(unless closed stages are shown) and Today's focus."
            + (f" Stage definition: {pending['definition']}" if pending.get("definition") else "")
        )
        with st.container(horizontal=True):
            st.button("Confirm move", type="primary", key="stage_change_confirm",
                      on_click=_confirm_stage_change)
            st.button("Cancel", key="stage_change_cancel", on_click=_cancel_stage_change)


def _on_board_move():
    """Glisser-deposer d'une carte : enregistre la nouvelle etape (ou demande confirmation)."""

    move = event_value(BOARD_KEY, "move")

    if move:
        request_stage_change(int(move["id"]), move["stage"])


def _on_board_open():
    """Clic sur une carte : ouvre la fiche du prospect."""

    target = event_value(BOARD_KEY, "open")

    if target:
        open_prospect(int(target["id"]))


def go_to(page_name, **state):
    """Change de page depuis un bouton (callback), en reglant d'autres widgets si besoin."""

    st.session_state["nav_page"] = page_name
    st.session_state["prospect_open"] = False

    for key, value in state.items():
        st.session_state[key] = value


@st.dialog("Add prospect", width="large")
def add_prospect_dialog():
    """Fenetre d'ajout rapide : reutilise le formulaire et les controles existants."""

    submitted, data = prospect_form("overview_create_form", get_verticals(), "Create prospect")

    if submitted:
        ok, message = create_prospect(data)

        if ok:
            reset_form("overview_create_form")
            st.session_state["flash"] = message
            st.rerun()
        else:
            st.error(message)


PRIORITY_BADGES = {"High": ":red-badge[High]", "Medium": ":orange-badge[Medium]", "Low": ":gray-badge[Low]"}

FEED_ICONS = {
    "Call": ":material/call:",
    "Email": ":material/mail:",
    "LinkedIn": ":material/work:",
    "Note": ":material/sticky_note_2:",
    "Objection": ":material/forum:",
    "Prospect": ":material/person_add:",
    "Score": ":material/trending_up:",
    "Stage": ":material/view_kanban:",
}


TEMPERATURE_COLORS = {"Hot": "red", "Warm": "orange", "Cold": "blue"}


def score_label(result):
    """Libelle colore du score, ex. ":red[72 · Hot]" (syntaxe de couleur Streamlit)."""

    if not result:
        return "No score"

    color = TEMPERATURE_COLORS[result["temperature"]]

    return f":{color}[{result['global']} · {result['temperature']}]"


def follow_up_card(task, show_prospect=True):
    """Affiche une relance avec un bouton pour la marquer comme terminee."""

    with st.container(border=True):

        col_text, col_button = st.columns([4, 1])

        col_text.markdown(f"**{task['title']}**")

        details = [f"Due: {task['due_at'] or 'no date'}"]

        if show_prospect and task.get("first_name"):
            details.insert(0, f"{task['first_name']} {task['last_name']} — {task['company_name']}")

        col_text.caption(" · ".join(details))

        if task.get("description"):
            col_text.write(task["description"])

        if task["status"] == TASK_OPEN:
            if col_button.button("Done", key=f"done_{task['id']}", width="stretch"):
                complete_task(task["id"])
                st.session_state["flash"] = f"Follow-up completed: {task['title']}"
                st.rerun()


# ==========================================
# ETATS VIDES ET ERREURS (P0.4)
# ==========================================
# Un seul modele pour toute l'application (blueprint : « les etats vides
# expliquent quoi faire ensuite », « les erreurs sont visibles et recuperables »).

def empty_state(title, message="", actions=(), icon=":material/inbox:", key="empty"):
    """Etat vide : icone + titre + explication + actions pour continuer.

    actions : liste de dictionnaires {"label", "on_click", "args", "kwargs",
              "icon", "primary"} ; chaque bouton execute son callback.
    key     : prefixe unique (plusieurs etats vides peuvent coexister sur une page).
    """

    with st.container(border=True):
        st.markdown(f"{icon} **{title}**")

        if message:
            st.caption(message)

        if actions:
            # Rangée horizontale : chaque bouton prend la largeur de son texte et
            # passe à la ligne s'il manque de place (colonnes étroites, mobile).
            with st.container(horizontal=True, wrap=True):
                for index, action in enumerate(actions):
                    st.button(
                        action["label"],
                        key=f"{key}_action_{index}",
                        icon=action.get("icon"),
                        type="primary" if action.get("primary") else "secondary",
                        on_click=action.get("on_click"),
                        args=action.get("args", ()),
                        kwargs=action.get("kwargs", {}),
                        width="content",
                    )


def no_results(what, key="no_results"):
    """Etat vide d'une liste filtree : rien ne correspond aux filtres choisis."""

    empty_state(
        f"No {what} matches these filters",
        "Loosen or clear the filters above to see more.",
        icon=":material/filter_alt_off:",
        key=key,
    )


# Actions reutilisables des etats vides
ADD_PROSPECT = {
    "label": "Add a prospect", "icon": ":material/person_add:", "primary": True,
    "on_click": go_to, "args": ("Prospects",), "kwargs": {"prospects_tabs": "New prospect"},
}
IMPORT_CSV = {
    "label": "Import a CSV file", "icon": ":material/upload_file:",
    "on_click": go_to, "args": ("Prospects",), "kwargs": {"prospects_tabs": "Import CSV"},
}
LOG_ACTIVITY = {
    "label": "Log a call or email", "icon": ":material/add_call:", "primary": True,
    "on_click": go_to, "args": ("Activity",), "kwargs": {"activity_tabs": "Log activity"},
}
OPEN_PIPELINE = {
    "label": "Open the pipeline", "icon": ":material/view_kanban:",
    "on_click": go_to, "args": ("Prospecting Pipeline",),
}


def error_state(error):
    """Erreur inattendue d'une page : message clair, actions, details techniques.

    Les donnees ne sont pas touchees : les ecritures en base se font dans des
    transactions qui sont annulees en cas d'erreur.
    """

    import traceback

    details = "".join(traceback.format_exception(error))
    print(details)  # aussi visible dans le terminal qui a lance streamlit

    with st.container(border=True):
        st.markdown(":material/error: **This page hit an unexpected error.**")
        st.caption(
            "Your data is safe. Try again; if the error persists, go back to the Overview "
            "and share the technical details below."
        )

        col_retry, col_home, _ = st.columns([1, 1, 2])
        col_retry.button("Try again", icon=":material/refresh:", type="primary",
                         key="error_retry", width="stretch")
        col_home.button("Back to Overview", icon=":material/home:", key="error_home",
                        on_click=go_to, args=("Overview",), width="stretch")

        with st.expander("Technical details"):
            st.code(details, language="text")
