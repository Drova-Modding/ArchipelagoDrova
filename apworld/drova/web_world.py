from BaseClasses import Tutorial
from worlds.AutoWorld import WebWorld

from .options import option_groups, option_presets


class DrovaWebWorld(WebWorld):
    game = "Drova - Forsaken Kin"

    theme = "jungle"

    bug_report_page = "https://github.com/Drova-Modding/ArchipelagoDrova/issues"

    setup_en = Tutorial(
        "Multiworld Setup Guide",
        "A guide to setting up Drova - Forsaken Kin for MultiWorld.",
        "English",
        "setup_en.md",
        "setup/en",
        ["TrustNoOneElse"],
    )

    tutorials = [setup_en]

    option_groups = option_groups
    options_presets = option_presets
