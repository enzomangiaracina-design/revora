"""Tableau Kanban du pipeline, façon HubSpot, avec glisser-déposer.

Concept : un "composant personnalisé" Streamlit (API components v2, incluse
dans Streamlit 1.67, aucune dépendance ajoutée). Le tableau est dessiné en
HTML/CSS/JavaScript dans le navigateur ; quand une carte est déposée dans
une autre colonne, le JavaScript envoie un événement à Python
(setTriggerValue), qui enregistre la nouvelle étape en base.

Sécurité : toutes les données (noms, entreprises...) sont insérées avec
textContent, jamais innerHTML : un texte contenant du code ne peut pas
s'exécuter dans la page.

Couleurs : jetons de ui/theme.py (charte REVORA), pas les couleurs HubSpot.
"""

import streamlit as st

from ui.theme import COLORS, RADIUS_CARD, RADIUS_CONTROL

HTML = '<div class="board" role="list"></div>'

CSS = f"""
:host {{ display: block; }}

.board {{
    display: flex;
    gap: 12px;
    overflow-x: auto;
    padding-bottom: 8px;
    align-items: flex-start;
}}

.column {{
    flex: 0 0 300px;
    background: #12121B;
    border: 1px solid {COLORS["border"]};
    border-radius: {RADIUS_CARD};
    display: flex;
    flex-direction: column;
    max-height: 72vh;
}}

.column-header {{
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 14px 16px 10px;
    color: {COLORS["white"]};
    font-weight: 500;
    font-size: 0.95rem;
}}

.column-header .count {{
    color: #9CA3AF;
    font-weight: 600;
}}

.column-header .closed {{
    margin-left: auto;
    color: {COLORS["gray"]};
    font-size: 0.75rem;
    font-weight: 500;
}}

.column-body {{
    padding: 4px 10px 12px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-height: 80px;
    border-radius: {RADIUS_CARD};
    transition: background-color 120ms ease;
}}

.column-body.drop-target {{
    background: rgba(124, 58, 237, 0.12);
    outline: 1px dashed {COLORS["lavender"]};
    outline-offset: -4px;
}}

.empty {{
    color: {COLORS["gray"]};
    font-size: 0.8rem;
    text-align: center;
    padding: 18px 0;
}}

.card {{
    background: {COLORS["slate"]};
    border: 1px solid {COLORS["border"]};
    border-radius: {RADIUS_CARD};
    padding: 14px 16px 10px;
    cursor: grab;
    transition: border-color 120ms ease, opacity 120ms ease;
}}

.card:hover {{ border-color: #3A3A4D; }}
.card.dragging {{ opacity: 0.45; cursor: grabbing; }}

.card-title {{
    color: {COLORS["lavender"]};
    font-weight: 600;
    font-size: 1rem;
    margin: 0 0 8px;
    cursor: pointer;
    background: none;
    border: none;
    padding: 0;
    text-align: left;
    font-family: inherit;
}}

.card-title:hover {{ text-decoration: underline; }}

.field {{
    color: #D1D5DB;
    font-size: 0.84rem;
    line-height: 1.55;
}}

.field .label {{ color: #9CA3AF; }}
.field.overdue .value {{ color: #F87171; }}
.field.stale .value {{ color: #FBBF24; }}

.score {{
    display: inline-block;
    font-weight: 600;
    font-size: 0.78rem;
    padding: 1px 8px;
    border-radius: 999px;
}}

.score.Hot  {{ color: #F87171; background: rgba(248, 113, 113, 0.14); }}
.score.Warm {{ color: #FBBF24; background: rgba(251, 191, 36, 0.14); }}
.score.Cold {{ color: #93C5FD; background: rgba(147, 197, 253, 0.14); }}

.divider {{
    border-top: 1px solid {COLORS["border"]};
    margin: 10px 0 8px;
}}

.contact {{
    display: flex;
    align-items: center;
    gap: 8px;
    color: {COLORS["lavender"]};
    font-size: 0.86rem;
    font-weight: 500;
}}

.avatar {{
    width: 26px;
    height: 26px;
    border-radius: 50%;
    background: rgba(167, 139, 250, 0.16);
    color: {COLORS["lavender"]};
    font-size: 0.7rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 26px;
}}

.actions {{
    display: flex;
    justify-content: flex-end;
    gap: 6px;
    margin-top: 6px;
}}

.icon-button {{
    background: none;
    border: 1px solid transparent;
    border-radius: {RADIUS_CONTROL};
    color: #9CA3AF;
    padding: 4px;
    cursor: pointer;
    display: flex;
}}

.icon-button:hover {{
    color: {COLORS["white"]};
    border-color: {COLORS["border"]};
}}

.icon-button svg {{ width: 16px; height: 16px; }}
"""

# Icônes au trait (style Lucide, conforme à la charte) : ouvrir la fiche, relances
ICON_OPEN = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>'
    '<path d="M18.4 2.6a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4Z"/></svg>'
)

ICON_TASKS = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/>'
    '<path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/></svg>'
)

JS = """
export default function (component) {
    const { data, parentElement, setTriggerValue } = component;
    const board = parentElement.querySelector('.board');
    board.replaceChildren();

    const el = (tag, className, text) => {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = text;
        return node;
    };

    const field = (label, value, extraClass) => {
        const line = el('div', 'field' + (extraClass ? ' ' + extraClass : ''));
        line.append(el('span', 'label', label + ': '), el('span', 'value', value));
        return line;
    };

    const iconButton = (svg, title, onClick) => {
        const button = el('button', 'icon-button');
        button.type = 'button';
        button.title = title;
        button.setAttribute('aria-label', title);
        button.innerHTML = svg;  // icône statique définie dans le code, pas une donnée
        button.addEventListener('click', (event) => { event.stopPropagation(); onClick(); });
        return button;
    };

    const counters = {};

    for (const stage of data.stages) {
        const column = el('section', 'column');
        column.setAttribute('role', 'listitem');

        const header = el('div', 'column-header');
        const count = el('span', 'count', String(stage.cards.length));
        header.append(el('span', null, stage.name), count);
        if (stage.closed) header.append(el('span', 'closed', 'closed'));
        counters[stage.name] = count;

        const body = el('div', 'column-body');
        body.dataset.stage = stage.name;

        const refreshEmpty = () => {
            const hasCards = body.querySelector('.card');
            const placeholder = body.querySelector('.empty');
            if (!hasCards && !placeholder) body.append(el('div', 'empty', 'No prospect'));
            if (hasCards && placeholder) placeholder.remove();
        };

        for (const card of stage.cards) {
            const node = el('article', 'card');
            node.draggable = true;
            node.dataset.id = card.id;

            const title = el('button', 'card-title', card.title);
            title.type = 'button';
            title.addEventListener('click', () => setTriggerValue('open', { id: card.id, at: Date.now() }));
            node.append(title);

            node.append(field('Created', card.created));
            node.append(field('Last activity', card.last_activity, card.stale ? 'stale' : ''));
            node.append(field('Next follow-up', card.next_follow_up, card.overdue ? 'overdue' : ''));
            node.append(field('Owner', card.owner));

            const scoreLine = el('div', 'field');
            scoreLine.append(el('span', 'label', 'Score: '));
            scoreLine.append(el('span', 'score ' + card.temperature, card.score + ' · ' + card.temperature));
            node.append(scoreLine);

            node.append(el('div', 'divider'));

            const contact = el('div', 'contact');
            contact.append(el('span', 'avatar', card.initials), el('span', null, card.contact));
            node.append(contact);

            const actions = el('div', 'actions');
            actions.append(
                iconButton(data.icons.open, 'Open prospect file',
                    () => setTriggerValue('open', { id: card.id, at: Date.now() })),
                iconButton(data.icons.tasks, 'Follow-ups',
                    () => setTriggerValue('open', { id: card.id, at: Date.now() })),
            );
            node.append(actions);

            node.addEventListener('dragstart', (event) => {
                event.dataTransfer.setData('text/plain', String(card.id));
                event.dataTransfer.effectAllowed = 'move';
                node.classList.add('dragging');
            });
            node.addEventListener('dragend', () => node.classList.remove('dragging'));

            body.append(node);
        }

        body.addEventListener('dragover', (event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = 'move';
            body.classList.add('drop-target');
        });
        body.addEventListener('dragleave', (event) => {
            if (!body.contains(event.relatedTarget)) body.classList.remove('drop-target');
        });
        body.addEventListener('drop', (event) => {
            event.preventDefault();
            body.classList.remove('drop-target');

            const id = event.dataTransfer.getData('text/plain');
            const node = board.querySelector(`.card[data-id="${CSS.escape(id)}"]`);
            if (!node) return;

            const from = node.parentElement;
            if (from === body) return;

            // Déplacement immédiat à l'écran, puis enregistrement côté Python
            body.prepend(node);
            counters[from.dataset.stage].textContent = String(from.querySelectorAll('.card').length);
            counters[body.dataset.stage].textContent = String(body.querySelectorAll('.card').length);
            [from, body].forEach((zone) => {
                const hasCards = zone.querySelector('.card');
                const placeholder = zone.querySelector('.empty');
                if (!hasCards && !placeholder) zone.append(el('div', 'empty', 'No prospect'));
                if (hasCards && placeholder) placeholder.remove();
            });

            setTriggerValue('move', { id: Number(id), stage: body.dataset.stage, at: Date.now() });
        });

        refreshEmpty();
        column.append(header, body);
        board.append(column);
    }
}
"""

_render = st.components.v2.component("revora_pipeline_board", html=HTML, css=CSS, js=JS)


def pipeline_board(stages, key, on_move, on_open):
    """Affiche le tableau.

    stages  : [{"name", "closed", "cards": [carte, ...]}, ...]
    on_move : appelée après un glisser-déposer ; lire st.session_state[key]["move"]
    on_open : appelée au clic sur une carte ; lire st.session_state[key]["open"]
    """

    return _render(
        key=key,
        data={"stages": stages, "icons": {"open": ICON_OPEN, "tasks": ICON_TASKS}},
        on_move_change=on_move,
        on_open_change=on_open,
    )


def event_value(key, name):
    """Lit la valeur d'un événement du composant dans st.session_state."""

    state = st.session_state.get(key)

    if state is None:
        return None

    if isinstance(state, dict):
        return state.get(name)

    return getattr(state, name, None)
