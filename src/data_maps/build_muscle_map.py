"""
Build the clickable body map used by the Workouts tab (run once; the app then works offline).

    python -m src.data_maps.build_muscle_map

Muscle shapes come from react-body-highlighter (https://github.com/giavinh79/react-body-highlighter,
MIT License, pinned to one commit): polygons on a 1000 x 2000 canvas for the front (anterior) and back
(posterior). This script turns them into assets/muscle_map_front.svg and _back.svg, where each muscle is
<g class="muscle" data-muscle="<id>">, and writes assets/muscle_map.json with how each muscle maps to
the body areas of the Instagram posts and to the muscles of the exercise database (reference.exercises).
"""
import json
import os
import re
import urllib.request

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
COMMIT = "d03fcd8740033721a51f5a2682de02ec31df92ba"
SOURCE = f"https://raw.githubusercontent.com/giavinh79/react-body-highlighter/{COMMIT}/"

# body-map muscle -> (label, body areas in clean.workouts, muscles in reference.exercises)
MUSCLES = {
    "neck": ("Neck", ["neck"], ["neck"]),
    "trapezius": ("Trapezius", ["neck", "back"], ["traps"]),
    "front-deltoids": ("Front shoulders", ["shoulders"], ["shoulders"]),
    "back-deltoids": ("Rear shoulders", ["shoulders"], ["shoulders"]),
    "chest": ("Chest", ["chest"], ["chest"]),
    "upper-back": ("Upper back", ["back"], ["lats", "middle back"]),
    "lower-back": ("Lower back", ["back"], ["lower back"]),
    "biceps": ("Biceps", ["arms"], ["biceps"]),
    "triceps": ("Triceps", ["arms"], ["triceps"]),
    "forearm": ("Forearms", ["arms"], ["forearms"]),
    "abs": ("Abs", ["core"], ["abdominals"]),
    "obliques": ("Obliques", ["core"], ["abdominals"]),
    "gluteal": ("Glutes", ["glutes"], ["glutes"]),
    "adductor": ("Inner thighs", ["legs", "hips"], ["adductors"]),
    "abductors": ("Outer thighs", ["legs", "hips"], ["abductors"]),
    "quadriceps": ("Quads", ["legs"], ["quadriceps"]),
    "hamstring": ("Hamstrings", ["legs"], ["hamstrings"]),
    "calves": ("Calves", ["legs"], ["calves"]),
    "soleus": ("Soleus", ["legs"], ["calves"]),  # left-soleus + right-soleus
    "head": ("Face / head", ["face"], []),
}
NOT_CLICKABLE = {"knees"}


def fetch(path):
    with urllib.request.urlopen(SOURCE + path, timeout=30) as response:
        return response.read().decode("utf-8")


def muscle_names():
    """MuscleType.UPPER_BACK -> 'upper-back' (from src/component/metadata.ts)."""
    metadata = fetch("src/component/metadata.ts")
    block = re.search(r"export const MuscleType = \{(.*?)\} as const", metadata, re.S).group(1)
    return dict(re.findall(r"([A-Z_]+):\s*'([a-z-]+)'", block))


def polygons(assets, side, names):
    """{muscle id: [points, ...]} for anteriorData or posteriorData."""
    block = re.search(rf"export const {side}Data[^=]*=\s*\[(.*?)\n\];", assets, re.S).group(1)
    shapes = {}
    for constant, points in re.findall(r"muscle:\s*MuscleType\.([A-Z_]+),\s*svgPoints:\s*\[(.*?)\]", block, re.S):
        muscle = names[constant].replace("left-", "").replace("right-", "")
        shapes.setdefault(muscle, []).extend(re.findall(r"'([\d\s.]+)'", points))
    return shapes


def main():
    os.makedirs(ASSETS, exist_ok=True)
    names = muscle_names()
    assets = fetch("src/assets/index.ts")
    for side, source in (("front", "anterior"), ("back", "posterior")):
        groups = []
        for muscle, shapes in polygons(assets, source, names).items():
            shapes_svg = "".join(f'<polygon points="{p}"/>' for p in shapes)
            if muscle in NOT_CLICKABLE or muscle not in MUSCLES:
                groups.append(f'<g class="part">{shapes_svg}</g>')
            else:
                groups.append(f'<g class="muscle" data-muscle="{muscle}"><title>{MUSCLES[muscle][0]}</title>{shapes_svg}</g>')
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 2000" class="body {side}">{"".join(groups)}</svg>'
        with open(os.path.join(ASSETS, f"muscle_map_{side}.svg"), "w", encoding="utf-8") as file:
            file.write(svg)
        print(f"{side}: {sum(g.startswith('<g class=\"muscle') for g in groups)} muscles, {len(svg) // 1024} KB")
    with open(os.path.join(ASSETS, "muscle_map.json"), "w") as file:
        json.dump({m: {"label": label, "areas": areas, "exercise_muscles": db}
                   for m, (label, areas, db) in MUSCLES.items()}, file, indent=2)
    license_text = fetch("LICENSE")
    with open(os.path.join(ASSETS, "MUSCLE_MAP_CREDITS.md"), "w") as file:
        file.write("Muscle shapes: react-body-highlighter (https://github.com/giavinh79/react-body-highlighter), "
                   f"commit {COMMIT}, used under the MIT License:\n\n{license_text}")


if __name__ == "__main__":
    main()
