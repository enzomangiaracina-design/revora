"""Crée la base de démonstration fictive demo.db (ne touche jamais revora.db).

Utilisation :
    python3 seed_demo.py            # crée demo.db (refuse si elle existe déjà)
    python3 seed_demo.py --reset    # recrée demo.db (supprime seulement demo.db)

Puis lancer l'application sur cette base :
    REVORA_DATABASE=demo.db streamlit run main.py
"""

import sys

from core.demo_data import DEMO_PATH, generate_demo


def main(argv):
    reset = "--reset" in argv

    try:
        summary = generate_demo(DEMO_PATH, reset=reset)
    except (FileExistsError, ValueError) as error:
        print(f"Nothing done: {error}")
        return 1

    print(
        f"Demo database created: {summary['path']}\n"
        f"  {summary['prospects']} prospects, {summary['interactions']} interactions, "
        f"{summary['objections']} objections, {summary['follow_ups']} follow-ups (all fictitious)\n"
        "Launch the app on it with:\n"
        "  REVORA_DATABASE=demo.db streamlit run main.py"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
