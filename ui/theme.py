"""Thème REVORA : jetons de design et styles complémentaires.

Source : REVORA_Brand_Kit / REVORA_Direction_Artistique.pdf.

Répartition :
  - .streamlit/config.toml : couleurs de base, police Inter, rayons, graphiques
    (réglages natifs de Streamlit) ;
  - ce fichier : jetons réutilisables en Python et le peu de CSS que
    Streamlit ne permet pas de régler (cartes KPI, navigation).

Règle de la charte : ne pas introduire de couleur, d'effet, de rayon ou de
style d'icône arbitraire ailleurs. Tout nouveau style passe par ici.
"""

from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "brand"

LOGO = ASSETS / "revora_logo_horizontal.png"
MONOGRAM = ASSETS / "revora_monogram.png"
FAVICON = ASSETS / "revora_favicon.png"

SIGNATURE = "Your prospecting, intelligently orchestrated."
DESCRIPTOR = "Sales Execution Platform"

# Palette officielle
COLORS = {
    "lavender": "#A78BFA",  # accent principal
    "violet": "#7C3AED",    # accent soutenu : actions, navigation active, sélection
    "night": "#0B0B12",     # fond principal
    "slate": "#1A1A24",     # surfaces
    "gray": "#6B7280",      # texte secondaire
    "white": "#F8FAFC",     # texte principal
    "border": "#262633",    # bordure discrète
}

# Espacements (grille de 4 px) et rayons
SPACE = 4
RADIUS_CONTROL = "8px"
RADIUS_CARD = "12px"

# Icônes de navigation.
# La charte prévoit Lucide ; Streamlit n'intègre nativement que Material Symbols.
# On utilise donc UNE seule famille (Material Symbols, style linéaire arrondi)
# pour ne pas mélanger les styles, en attendant une interface où Lucide est possible.
NAV_ICONS = {
    "Overview": ":material/home:",
    "Prospecting Pipeline": ":material/view_kanban:",
    "Prospects": ":material/group:",
    "Prospect Details": ":material/person:",
    "Activity": ":material/bolt:",
    "Objections": ":material/forum:",
    "AI Copilot": ":material/auto_awesome:",
    "Performance": ":material/bar_chart:",
    "Settings": ":material/settings:",
}


def nav_label(page):
    """Libellé de navigation avec son icône."""

    return f"{NAV_ICONS.get(page, '')} {page}".strip()


CSS = f"""
<style>
/* ---------- Cartes KPI : un chiffre, un libellé ---------- */
div[data-testid="stMetric"] {{
    background-color: {COLORS["slate"]};
    border: 1px solid {COLORS["border"]};
    border-radius: {RADIUS_CARD};
    padding: {SPACE * 4}px {SPACE * 5}px;
}}

div[data-testid="stMetricLabel"] p {{
    color: #9CA3AF;
    font-weight: 500;
}}

div[data-testid="stMetricValue"] {{
    color: {COLORS["white"]};
}}

/* ---------- Cartes et conteneurs à bordure : rayon 12 px ---------- */
div[data-testid="stVerticalBlockBorderWrapper"],
div[data-testid="stExpander"] details {{
    border-radius: {RADIUS_CARD};
}}

/* ---------- Navigation latérale : élément actif en violet ---------- */
section[data-testid="stSidebar"] div[data-testid="stElementContainer"]:has(div[data-testid="stRadio"]),
section[data-testid="stSidebar"] div[data-testid="stRadio"] {{
    width: 100%;
}}

section[data-testid="stSidebar"] div[role="radiogroup"] {{
    gap: {SPACE}px;
    width: 100%;
}}

section[data-testid="stSidebar"] div[role="radiogroup"] > div {{
    width: 100%;
}}

section[data-testid="stSidebar"] label[data-testid="stRadioOption"] {{
    padding: {SPACE * 2}px {SPACE * 3}px;
    border-radius: {RADIUS_CONTROL};
    width: 100%;
    transition: background-color 120ms ease;
}}

/* Masque le rond de sélection : l'état actif est porté par le fond */
section[data-testid="stSidebar"] label[data-testid="stRadioOption"]
    > div > div:not([data-testid="stMarkdownContainer"]) {{
    display: none;
}}

section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:hover {{
    background-color: rgba(167, 139, 250, 0.08);
}}

section[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] {{
    background-color: rgba(124, 58, 237, 0.22);
}}

section[data-testid="stSidebar"] label[data-testid="stRadioOption"] p {{
    color: #C9CDD6;
    font-size: 0.9rem;
}}

section[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] p {{
    color: {COLORS["white"]};
    font-weight: 500;
}}

section[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] span[role="img"] {{
    color: {COLORS["lavender"]};
}}

/* Petits écrans : cartes KPI en grille de 2 colonnes au lieu d'une pile.
   Cible uniquement les colonnes qui contiennent DIRECTEMENT une carte KPI. */
@media (max-width: 640px) {{
    div[data-testid="stColumn"]:has(
        > div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] > div[data-testid="stMetric"]
    ) {{
        /* 50 % moins la moitié de l'espacement de 16 px entre colonnes */
        width: calc(50% - {SPACE * 2}px) !important;
        flex: 0 0 calc(50% - {SPACE * 2}px) !important;
        min-width: calc(50% - {SPACE * 2}px) !important;
    }}

    div[data-testid="stMetric"] {{
        padding: {SPACE * 3}px {SPACE * 3}px;
    }}
}}

/* Titres de section compacts (Overview) */
.revora-section {{
    color: #9CA3AF;
    font-size: 0.74rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin: {SPACE * 2}px 0 {SPACE * 2}px 0;
}}

/* Descripteur sous le logo */
.revora-descriptor {{
    color: {COLORS["gray"]};
    font-size: 0.68rem;
    font-weight: 500;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    margin: -{SPACE * 2}px 0 {SPACE * 2}px 0;
}}

/* ---------- Titres ---------- */
h1 {{
    letter-spacing: -0.02em;
}}
</style>
"""


def section_title(text, container=None):
    """Titre de section discret (majuscules espacées), via le style centralisé."""

    (container or st).markdown(f'<div class="revora-section">{text}</div>', unsafe_allow_html=True)


def apply_theme():
    """Applique le logo et les styles complémentaires (à appeler une fois par page)."""

    st.logo(str(LOGO), size="large", icon_image=str(MONOGRAM))
    st.markdown(CSS, unsafe_allow_html=True)
    st.sidebar.markdown(
        f'<div class="revora-descriptor">{DESCRIPTOR}</div>', unsafe_allow_html=True
    )
