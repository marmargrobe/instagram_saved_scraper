"""
Build the clickable body map used by the Workouts tab (run once; the app then works offline).

    python -m src.data_maps.build_muscle_map

Downloads the front/back body outlines and the 15 muscle drawings from wger (https://wger.de,
open source, AGPL-3.0) and merges them into assets/muscle_map_front.svg and _back.svg. Every
muscle becomes <g class="muscle" data-muscle="<id>">, so the app can colour and click it.
assets/muscle_map.json maps each muscle to the posts' body areas and to reference.exercises muscles.
"""
import json
import os
import re
import urllib.request

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
WGER = "https://wger.de"
USER_AGENT = "saved-instagram-muscle-map (personal, non-commercial project)"

# wger muscle id -> (id used in the app, label, body areas in clean.workouts, muscles in reference.exercises)
MUSCLES = {
    2: ("shoulders", "Shoulders", ["shoulders"], ["shoulders"]),
    4: ("chest", "Chest", ["chest"], ["chest"]),
    3: ("serratus", "Serratus", ["chest"], ["chest"]),
    1: ("biceps", "Biceps", ["arms"], ["biceps"]),
    13: ("brachialis", "Brachialis", ["arms"], ["biceps"]),
    5: ("triceps", "Triceps", ["arms"], ["triceps"]),
    6: ("abs", "Abs", ["core"], ["abdominals"]),
    14: ("obliques", "Obliques", ["core"], ["abdominals"]),
    12: ("lats", "Lats", ["back"], ["lats", "middle back"]),
    9: ("trapezius", "Trapezius", ["neck", "back"], ["traps"]),
    8: ("glutes", "Glutes", ["glutes"], ["glutes"]),
    10: ("quads", "Quads", ["legs"], ["quadriceps"]),
    11: ("hamstrings", "Hamstrings", ["legs"], ["hamstrings"]),
    7: ("calves", "Calves", ["legs"], ["calves"]),
    15: ("soleus", "Soleus", ["legs"], ["calves"]),
}


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def svg_parts(svg):
    """(width, height, inner markup) of an Inkscape SVG file."""
    width = float(re.search(r'\swidth="([\d.]+)', svg).group(1))
    height = float(re.search(r'\sheight="([\d.]+)', svg).group(1))
    inner = re.search(r"<svg[\s\S]*?>([\s\S]*)</svg>", svg).group(1)
    inner = re.sub(r"<metadata[\s\S]*?</metadata>|<sodipodi:namedview[\s\S]*?/>|<defs[\s\S]*?</defs>", "", inner)
    return width, height, inner


def muscle_markup(svg):
    """Muscle drawing without its red fill, so CSS can colour it."""
    _, _, inner = svg_parts(svg)
    inner = re.sub(r"fill:#[0-9a-fA-F]{6};?", "", inner)
    return re.sub(r'\sfill="#[0-9a-fA-F]{6}"', "", inner)


def main():
    os.makedirs(ASSETS, exist_ok=True)
    muscles = json.loads(fetch(f"{WGER}/api/v2/muscle/?format=json"))["results"]
    for side, is_front in (("front", True), ("back", False)):
        width, height, body = svg_parts(fetch(f"{WGER}/static/images/muscles/muscular_system_{side}.svg"))
        groups = []
        for muscle in muscles:
            if muscle["is_front"] != is_front or muscle["id"] not in MUSCLES:
                continue
            key, label, _, _ = MUSCLES[muscle["id"]]
            url = muscle["image_url_main"]
            drawing = muscle_markup(fetch(url if url.startswith("http") else WGER + url))
            groups.append(f'<g class="muscle" data-muscle="{key}"><title>{label}</title>{drawing}</g>')
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}" class="body {side}">'
            f'<g class="outline">{body}</g>{"".join(groups)}</svg>'
        )
        path = os.path.join(ASSETS, f"muscle_map_{side}.svg")
        with open(path, "w", encoding="utf-8") as file:
            file.write(svg)
        print(f"{side}: {len(groups)} muscles -> {os.path.relpath(path)} ({len(svg) // 1024} KB)")
    with open(os.path.join(ASSETS, "muscle_map.json"), "w") as file:
        json.dump({key: {"label": label, "areas": areas, "exercise_muscles": db}
                   for key, label, areas, db in MUSCLES.values()}, file, indent=2)
    with open(os.path.join(ASSETS, "MUSCLE_MAP_CREDITS.md"), "w") as file:
        file.write("Body outlines and muscle drawings: wger Workout Manager (https://wger.de, "
                   "https://github.com/wger-project/wger), AGPL-3.0. Merged by build_muscle_map.py.\n")


if __name__ == "__main__":
    main()
