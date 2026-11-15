"""REVORA — point d'entrée de l'application Streamlit.

Ce fichier ne fait que trois choses :
  1. configurer la page et charger les données communes ;
  2. afficher la navigation ;
  3. appeler la page choisie (un module par page dans screens/).

Lancement : streamlit run main.py
"""

import streamlit as st

from core.score_service import refresh_scores
from database import get_all_prospects, get_stage_names, initialize_database
from screens import AppContext
from screens import overview, prospects, prospect_details, pipeline, activity, objections, copilot, performance, settings
from ui import theme

# ==========================================
# 1. CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="REVORA | Sales Execution Platform",
    page_icon=str(theme.FAVICON),
    layout="wide"
)

initialize_database()

# Données communes, chargées une fois par affichage :
#  - prospects : la base ;
#  - stage_names : étapes du pipeline (servent aussi de liste de statuts) ;
#  - scores : recalculés à chaque affichage, seules les VARIATIONS sont historisées.
ctx = AppContext(
    prospects=get_all_prospects(),
    stage_names=get_stage_names(),
    scores=refresh_scores(),
)

# ==========================================
# 2. IDENTITE VISUELLE
# ==========================================

# Couleurs, police et rayons : .streamlit/config.toml
# Logo, cartes KPI et navigation : ui/theme.py
theme.apply_theme()

# ==========================================
# 3. NAVIGATION
# ==========================================

page = st.sidebar.radio(
    "Navigation",
    [
        "Overview",
        "Prospecting Pipeline",
        "Prospects",
        "Prospect Details",
        "Activity",
        "Objections",
        "AI Copilot",
        "Performance",
        "Settings"
    ],
    format_func=theme.nav_label,
    label_visibility="collapsed",
    key="nav_page"
)

st.sidebar.divider()
st.sidebar.caption("VERSION 0.14.1")

# ==========================================
# 4. PAGE CHOISIE
# ==========================================

PAGES = {
    "Overview": overview.render,
    "Prospects": prospects.render,
    "Prospect Details": prospect_details.render,
    "Prospecting Pipeline": pipeline.render,
    "Activity": activity.render,
    "Objections": objections.render,
    "AI Copilot": copilot.render,
    "Performance": performance.render,
    "Settings": settings.render,
}

PAGES[page](ctx)
