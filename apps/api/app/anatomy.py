from __future__ import annotations

from collections.abc import Iterable

# Keep the backend catalog aligned with the muscle ids consumed by the body-muscles frontend chart.
DEFAULT_ANATOMY_BY_GROUP: dict[str, dict[str, list[str]]] = {
    "Chest": {
        "primary": ["chest-upper-left", "chest-upper-right", "chest-lower-left", "chest-lower-right"],
        "secondary": ["shoulder-front-left", "shoulder-front-right", "triceps-long-left", "triceps-long-right"],
    },
    "Back": {
        "primary": [
            "traps-upper-left",
            "traps-upper-right",
            "traps-mid-left",
            "traps-mid-right",
            "lats-upper-left",
            "lats-upper-right",
            "lats-mid-left",
            "lats-mid-right",
            "lats-lower-left",
            "lats-lower-right",
        ],
        "secondary": ["deltoid-rear-left", "deltoid-rear-right", "biceps-left", "biceps-right"],
    },
    "Legs": {
        "primary": ["quads-left", "quads-right", "adductors-left", "adductors-right"],
        "secondary": ["glutes-left", "glutes-right", "hamstrings-left", "hamstrings-right", "calves-left", "calves-right"],
    },
    "Hamstrings": {
        "primary": ["hamstrings-left", "hamstrings-right"],
        "secondary": ["glutes-left", "glutes-right", "calves-left", "calves-right"],
    },
    "Glutes": {
        "primary": ["glutes-left", "glutes-right"],
        "secondary": ["hamstrings-left", "hamstrings-right", "adductors-left", "adductors-right"],
    },
    "Calves": {
        "primary": ["calves-left", "calves-right"],
        "secondary": ["hamstrings-left", "hamstrings-right"],
    },
    "Shoulders": {
        "primary": ["shoulder-front-left", "shoulder-front-right", "deltoid-rear-left", "deltoid-rear-right"],
        "secondary": ["traps-upper-left", "traps-upper-right", "biceps-left", "biceps-right", "triceps-long-left", "triceps-long-right"],
    },
    "Arms": {
        "primary": ["biceps-left", "biceps-right", "triceps-long-left", "triceps-long-right", "triceps-lateral-left", "triceps-lateral-right"],
        "secondary": ["forearm-left", "forearm-right", "shoulder-front-left", "shoulder-front-right"],
    },
    "Core": {
        "primary": ["abs-upper-left", "abs-upper-right", "abs-lower-left", "abs-lower-right", "obliques-left", "obliques-right"],
        "secondary": ["serratus-anterior-left", "serratus-anterior-right"],
    },
    "Conditioning": {
        "primary": ["quads-left", "quads-right", "hamstrings-left", "hamstrings-right", "calves-left", "calves-right"],
        "secondary": ["glutes-left", "glutes-right", "abs-upper-left", "abs-upper-right"],
    },
}

# Override slugs where generic muscle-group fallbacks are too coarse for a believable front/back view.
ANATOMY_OVERRIDES: dict[str, dict[str, list[str]]] = {
    "cable-triceps-pushdown": {
        "primary": ["triceps-long-left", "triceps-long-right", "triceps-lateral-left", "triceps-lateral-right"],
        "secondary": ["forearm-left", "forearm-right", "shoulder-front-left", "shoulder-front-right"],
    },
    "barbell-bench-press": {
        "primary": ["chest-upper-left", "chest-upper-right", "chest-lower-left", "chest-lower-right"],
        "secondary": ["shoulder-front-left", "shoulder-front-right", "triceps-long-left", "triceps-long-right"],
    },
    "incline-dumbbell-press": {
        "primary": ["chest-upper-left", "chest-upper-right"],
        "secondary": ["shoulder-front-left", "shoulder-front-right", "triceps-long-left", "triceps-long-right"],
    },
    "lat-pulldown": {
        "primary": ["lats-upper-left", "lats-upper-right", "lats-mid-left", "lats-mid-right"],
        "secondary": ["biceps-left", "biceps-right", "traps-mid-left", "traps-mid-right"],
    },
    "seated-cable-row": {
        "primary": ["lats-mid-left", "lats-mid-right", "traps-mid-left", "traps-mid-right"],
        "secondary": ["biceps-left", "biceps-right", "deltoid-rear-left", "deltoid-rear-right"],
    },
    "back-squat": {
        "primary": ["quads-left", "quads-right", "glutes-left", "glutes-right"],
        "secondary": ["hamstrings-left", "hamstrings-right", "calves-left", "calves-right"],
    },
    "front-squat": {
        "primary": ["quads-left", "quads-right"],
        "secondary": ["glutes-left", "glutes-right", "abs-upper-left", "abs-upper-right"],
    },
    "romanian-deadlift": {
        "primary": ["hamstrings-left", "hamstrings-right", "glutes-left", "glutes-right"],
        "secondary": ["lats-lower-left", "lats-lower-right", "traps-lower-left", "traps-lower-right"],
    },
    "deadlift": {
        "primary": ["glutes-left", "glutes-right", "hamstrings-left", "hamstrings-right", "traps-upper-left", "traps-upper-right"],
        "secondary": ["lats-mid-left", "lats-mid-right", "quads-left", "quads-right"],
    },
    "bulgarian-split-squat": {
        "primary": ["quads-left", "quads-right", "glutes-left", "glutes-right"],
        "secondary": ["hamstrings-left", "hamstrings-right", "adductors-left", "adductors-right"],
    },
    "walking-lunge": {
        "primary": ["quads-left", "quads-right", "glutes-left", "glutes-right"],
        "secondary": ["hamstrings-left", "hamstrings-right", "calves-left", "calves-right"],
    },
    "lying-leg-curl": {
        "primary": ["hamstrings-left", "hamstrings-right"],
        "secondary": ["calves-left", "calves-right", "glutes-left", "glutes-right"],
    },
    "standing-calf-raise": {
        "primary": ["calves-left", "calves-right"],
        "secondary": ["hamstrings-left", "hamstrings-right", "glutes-left", "glutes-right"],
    },
    "hip-thrust": {
        "primary": ["glutes-left", "glutes-right"],
        "secondary": ["hamstrings-left", "hamstrings-right", "quads-left", "quads-right"],
    },
    "pull-up": {
        "primary": ["lats-upper-left", "lats-upper-right", "lats-mid-left", "lats-mid-right"],
        "secondary": ["biceps-left", "biceps-right", "traps-mid-left", "traps-mid-right"],
    },
    "chest-supported-row": {
        "primary": ["lats-mid-left", "lats-mid-right", "traps-mid-left", "traps-mid-right"],
        "secondary": ["biceps-left", "biceps-right", "deltoid-rear-left", "deltoid-rear-right"],
    },
    "single-arm-dumbbell-row": {
        "primary": ["lats-mid-left", "lats-mid-right", "lats-lower-left", "lats-lower-right"],
        "secondary": ["biceps-left", "biceps-right", "traps-mid-left", "traps-mid-right"],
    },
    "machine-chest-press": {
        "primary": ["chest-upper-left", "chest-upper-right", "chest-lower-left", "chest-lower-right"],
        "secondary": ["shoulder-front-left", "shoulder-front-right", "triceps-long-left", "triceps-long-right"],
    },
    "cable-fly": {
        "primary": ["chest-upper-left", "chest-upper-right", "chest-lower-left", "chest-lower-right"],
        "secondary": [],
    },
    "push-up": {
        "primary": ["chest-upper-left", "chest-upper-right", "chest-lower-left", "chest-lower-right"],
        "secondary": ["shoulder-front-left", "shoulder-front-right", "triceps-long-left", "triceps-long-right", "abs-upper-left", "abs-upper-right"],
    },
    "overhead-press": {
        "primary": ["shoulder-front-left", "shoulder-front-right"],
        "secondary": ["triceps-long-left", "triceps-long-right", "abs-upper-left", "abs-upper-right"],
    },
    "dumbbell-shoulder-press": {
        "primary": ["shoulder-front-left", "shoulder-front-right"],
        "secondary": ["triceps-long-left", "triceps-long-right", "abs-upper-left", "abs-upper-right"],
    },
    "arnold-press": {
        "primary": ["shoulder-front-left", "shoulder-front-right"],
        "secondary": ["biceps-left", "biceps-right", "triceps-long-left", "triceps-long-right"],
    },
    "dumbbell-lateral-raise": {
        "primary": ["shoulder-front-left", "shoulder-front-right"],
        "secondary": ["deltoid-rear-left", "deltoid-rear-right", "traps-upper-left", "traps-upper-right"],
    },
    "face-pull": {
        "primary": ["deltoid-rear-left", "deltoid-rear-right", "traps-mid-left", "traps-mid-right"],
        "secondary": ["biceps-left", "biceps-right", "forearm-left", "forearm-right"],
    },
    "rear-delt-fly": {
        "primary": ["deltoid-rear-left", "deltoid-rear-right"],
        "secondary": ["traps-mid-left", "traps-mid-right", "lats-upper-left", "lats-upper-right"],
    },
    "upright-row": {
        "primary": ["shoulder-front-left", "shoulder-front-right", "traps-upper-left", "traps-upper-right"],
        "secondary": ["biceps-left", "biceps-right", "forearm-left", "forearm-right"],
    },
    "skull-crusher": {
        "primary": ["triceps-long-left", "triceps-long-right", "triceps-lateral-left", "triceps-lateral-right"],
        "secondary": ["forearm-left", "forearm-right", "shoulder-front-left", "shoulder-front-right"],
    },
    "overhead-cable-triceps-extension": {
        "primary": ["triceps-long-left", "triceps-long-right", "triceps-lateral-left", "triceps-lateral-right"],
        "secondary": ["forearm-left", "forearm-right", "shoulder-front-left", "shoulder-front-right"],
    },
    "close-grip-bench-press": {
        "primary": ["triceps-long-left", "triceps-long-right", "triceps-lateral-left", "triceps-lateral-right"],
        "secondary": ["chest-upper-left", "chest-upper-right", "shoulder-front-left", "shoulder-front-right"],
    },
    "ez-bar-curl": {
        "primary": ["biceps-left", "biceps-right"],
        "secondary": [],
    },
    "hammer-curl": {
        "primary": ["biceps-left", "biceps-right", "forearm-left", "forearm-right"],
        "secondary": [],
    },
    "preacher-curl": {
        "primary": ["biceps-left", "biceps-right"],
        "secondary": [],
    },
    "rope-cable-curl": {
        "primary": ["biceps-left", "biceps-right"],
        "secondary": [],
    },
    "plank": {
        "primary": ["abs-upper-left", "abs-upper-right", "abs-lower-left", "abs-lower-right", "obliques-left", "obliques-right"],
        "secondary": ["glutes-left", "glutes-right", "shoulder-front-left", "shoulder-front-right"],
    },
    "side-plank": {
        "primary": ["obliques-left", "obliques-right"],
        "secondary": ["abs-upper-left", "abs-upper-right", "glutes-left", "glutes-right"],
    },
    "ab-wheel-rollout": {
        "primary": ["abs-upper-left", "abs-upper-right", "abs-lower-left", "abs-lower-right"],
        "secondary": ["obliques-left", "obliques-right", "shoulder-front-left", "shoulder-front-right"],
    },
    "hanging-leg-raise": {
        "primary": ["abs-lower-left", "abs-lower-right"],
        "secondary": ["abs-upper-left", "abs-upper-right", "hip-flexors-left", "hip-flexors-right"],
    },
    "cable-crunch": {
        "primary": ["abs-upper-left", "abs-upper-right", "abs-lower-left", "abs-lower-right"],
        "secondary": ["obliques-left", "obliques-right"],
    },
    "chin-to-chest-stretch": {
        "primary": ["traps-upper-left", "traps-upper-right"],
        "secondary": ["shoulder-front-left", "shoulder-front-right"],
    },
    "isometric-neck-exercise-front-and-back": {
        "primary": ["traps-upper-left", "traps-upper-right"],
        "secondary": ["deltoid-rear-left", "deltoid-rear-right"],
    },
    "isometric-neck-exercise-sides": {
        "primary": ["traps-upper-left", "traps-upper-right"],
        "secondary": ["shoulder-front-left", "shoulder-front-right"],
    },
    "lying-face-down-plate-neck-resistance": {
        "primary": ["traps-upper-left", "traps-upper-right"],
        "secondary": ["deltoid-rear-left", "deltoid-rear-right"],
    },
    "lying-face-up-plate-neck-resistance": {
        "primary": ["traps-upper-left", "traps-upper-right"],
        "secondary": ["shoulder-front-left", "shoulder-front-right"],
    },
    "neck-smr": {
        "primary": ["traps-upper-left", "traps-upper-right"],
        "secondary": [],
    },
    "seated-head-harness-neck-resistance": {
        "primary": ["traps-upper-left", "traps-upper-right"],
        "secondary": ["deltoid-rear-left", "deltoid-rear-right"],
    },
    "side-neck-stretch": {
        "primary": ["traps-upper-left", "traps-upper-right"],
        "secondary": ["shoulder-front-left", "shoulder-front-right"],
    },
    "pallof-press": {
        "primary": ["obliques-left", "obliques-right", "abs-upper-left", "abs-upper-right"],
        "secondary": ["glutes-left", "glutes-right", "shoulder-front-left", "shoulder-front-right"],
    },
    "treadmill-incline-walk": {
        "primary": ["quads-left", "quads-right", "glutes-left", "glutes-right", "calves-left", "calves-right"],
        "secondary": ["hamstrings-left", "hamstrings-right", "abs-upper-left", "abs-upper-right"],
    },
    "stationary-bike": {
        "primary": ["quads-left", "quads-right", "calves-left", "calves-right"],
        "secondary": ["glutes-left", "glutes-right", "hamstrings-left", "hamstrings-right"],
    },
    "rowing-machine": {
        "primary": ["quads-left", "quads-right", "lats-mid-left", "lats-mid-right", "traps-mid-left", "traps-mid-right"],
        "secondary": ["biceps-left", "biceps-right", "hamstrings-left", "hamstrings-right"],
    },
    "elliptical": {
        "primary": ["quads-left", "quads-right", "hamstrings-left", "hamstrings-right", "calves-left", "calves-right"],
        "secondary": ["glutes-left", "glutes-right", "shoulder-front-left", "shoulder-front-right"],
    },
}

VARIANT_ALIAS_RULES: list[tuple[tuple[str, ...], dict[str, list[str]]]] = [
    (
        (
            "smith-machine-bench-press",
            "smith-machine-flat-bench-press",
            "smith-machine-decline-bench-press",
            "dumbbell-bench-press",
            "dumbbell-decline-bench-press",
            "dumbbell-neutral-grip-bench-press",
            "machine-decline-chest-press",
            "cable-chest-press",
            "single-arm-cable-chest-press",
            "parallel-bar-dip",
            "assisted-dip-bodyweight",
            "decline-push-up",
            "hand-release-push-up",
        ),
        {
            "primary": ["chest-upper-left", "chest-upper-right", "chest-lower-left", "chest-lower-right"],
            "secondary": ["triceps-long-left", "triceps-long-right", "shoulder-front-left", "shoulder-front-right"],
        },
    ),
    (
        (
            "smith-machine-incline-bench-press",
            "machine-incline-chest-press",
            "incline-machine-press",
            "dumbbell-incline-bench-press",
            "barbell-incline-bench-press",
        ),
        {
            "primary": ["chest-upper-left", "chest-upper-right"],
            "secondary": ["triceps-long-left", "triceps-long-right", "shoulder-front-left", "shoulder-front-right"],
        },
    ),
    (
        (
            "barbell-row",
            "pendlay-row",
            "tbar-row",
            "machine-high-row",
            "machine-low-row",
            "single-arm-cable-row",
            "inverted-row",
            "smith-machine-bent-over-row",
            "dumbbell-chest-supported-row",
            "dumbbell-seal-row",
            "dumbbell-single-arm-lat-row",
            "barbell-seal-row",
            "machine-seated-row",
            "landmine-row",
        ),
        {
            "primary": ["lats-mid-left", "lats-mid-right", "traps-mid-left", "traps-mid-right"],
            "secondary": ["biceps-left", "biceps-right", "deltoid-rear-left", "deltoid-rear-right"],
        },
    ),
    (
        ("chin-up", "neutral-grip-pull-up", "machine-lat-pulldown", "cable-lat-prayer"),
        {
            "primary": ["lats-upper-left", "lats-upper-right", "lats-mid-left", "lats-mid-right"],
            "secondary": ["biceps-left", "biceps-right", "traps-mid-left", "traps-mid-right"],
        },
    ),
    (
        (
            "smith-machine-squat",
            "smith-machine-front-squat",
            "smith-machine-box-squat",
            "belt-squat",
            "pendulum-squat",
            "v-squat-machine",
            "hack-squat-machine",
            "horizontal-leg-press",
            "single-leg-leg-press",
            "barbell-high-bar-squat",
            "barbell-box-squat",
            "barbell-zercher-squat",
            "barbell-landmine-squat",
        ),
        {
            "primary": ["quads-left", "quads-right", "glutes-left", "glutes-right"],
            "secondary": ["hamstrings-left", "hamstrings-right", "calves-left", "calves-right"],
        },
    ),
    (
        (
            "smith-machine-romanian-deadlift",
            "dumbbell-romanian-deadlift",
            "dumbbell-stiff-leg-deadlift",
            "barbell-good-morning",
            "smith-machine-good-morning",
            "barbell-deficit-romanian-deadlift",
            "glute-ham-raise",
            "nordic-hamstring-curl",
            "kettlebell-romanian-deadlift",
            "kettlebell-single-leg-deadlift",
        ),
        {
            "primary": ["hamstrings-left", "hamstrings-right", "glutes-left", "glutes-right"],
            "secondary": ["lats-lower-left", "lats-lower-right", "traps-lower-left", "traps-lower-right"],
        },
    ),
]

ISOLATION_RULES: list[tuple[tuple[str, ...], dict[str, list[str]]]] = [
    (
        (
            "bayesian-curl",
            "cable-bayesian-curl",
            "preacher-curl",
            "machine-preacher-curl",
            "concentration-curl",
            "incline-curl",
            "rope-cable-curl",
            "cable-overhead-curl",
            "cable-face-away-curl",
            "cable-high-curl",
            "dumbbell-spider-curl",
            "ez-bar-spider-curl",
            "ez-bar-close-grip-curl",
            "cable-drag-curl",
        ),
        {
            "primary": ["biceps-left", "biceps-right"],
            "secondary": [],
        },
    ),
    (
        ("drag-curl",),
        {
            "primary": ["biceps-left", "biceps-right"],
            "secondary": [],
        },
    ),
    (
        ("cable-hammer-curl", "hammer-curl", "dumbbell-zottman-curl", "ez-bar-reverse-curl", "dumbbell-reverse-curl"),
        {
            "primary": ["biceps-left", "biceps-right", "forearm-left", "forearm-right"],
            "secondary": [],
        },
    ),
    (
        (
            "cable-triceps-pushdown",
            "skull-crusher",
            "barbell-skull-crusher",
            "machine-triceps-extension",
            "cable-triceps-kickback",
            "dumbbell-kickback",
            "cable-rope-overhead-triceps-extension",
            "overhead-cable-triceps-extension",
            "smith-machine-jm-press",
            "barbell-jm-press",
            "bench-dip",
            "cable-jm-press",
            "cable-skull-crusher",
        ),
        {
            "primary": ["triceps-long-left", "triceps-long-right", "triceps-lateral-left", "triceps-lateral-right"],
            "secondary": [],
        },
    ),
    (
        ("dumbbell-fly", "cable-fly", "cable-crossover", "low-cable-fly", "pec-deck", "machine-chest-fly"),
        {
            "primary": ["chest-upper-left", "chest-upper-right", "chest-lower-left", "chest-lower-right"],
            "secondary": [],
        },
    ),
    (
        (
            "dumbbell-seated-lateral-raise",
            "dumbbell-lateral-raise",
            "cable-lateral-raise",
            "machine-lateral-raise",
            "cable-lean-away-lateral-raise",
        ),
        {
            "primary": ["shoulder-front-left", "shoulder-front-right"],
            "secondary": [],
        },
    ),
    (
        ("dumbbell-front-raise", "cable-front-raise"),
        {
            "primary": ["shoulder-front-left", "shoulder-front-right"],
            "secondary": [],
        },
    ),
    (
        ("rear-delt-fly", "machine-reverse-fly", "cable-rear-delt-row", "dumbbell-rear-delt-fly"),
        {
            "primary": ["deltoid-rear-left", "deltoid-rear-right"],
            "secondary": [],
        },
    ),
    (
        ("leg-extension", "single-leg-extension"),
        {
            "primary": ["quads-left", "quads-right"],
            "secondary": [],
        },
    ),
    (
        ("lying-leg-curl", "seated-leg-curl", "machine-standing-leg-curl", "cable-lying-leg-curl"),
        {
            "primary": ["hamstrings-left", "hamstrings-right"],
            "secondary": [],
        },
    ),
    (
        ("standing-calf-raise", "seated-calf-raise", "donkey-calf-raise", "smith-machine-calf-raise", "barbell-calf-raise", "machine-hack-calf-raise"),
        {
            "primary": ["calves-left", "calves-right"],
            "secondary": [],
        },
    ),
    (
        ("hip-abduction-machine", "abductor-machine", "cable-hip-abduction"),
        {
            "primary": ["glutes-left", "glutes-right"],
            "secondary": [],
        },
    ),
    (
        ("hip-adduction-machine", "adductor-machine", "cable-hip-adduction"),
        {
            "primary": ["adductors-left", "adductors-right"],
            "secondary": [],
        },
    ),
]

VALID_ANATOMY_REGION_IDS = frozenset(
    {
        "abs-lower-left",
        "abs-lower-right",
        "abs-upper-left",
        "abs-upper-right",
        "adductors-left",
        "adductors-right",
        "biceps-left",
        "biceps-right",
        "calves-left",
        "calves-right",
        "chest-lower-left",
        "chest-lower-right",
        "chest-upper-left",
        "chest-upper-right",
        "deltoid-rear-left",
        "deltoid-rear-right",
        "forearm-left",
        "forearm-right",
        "glutes-left",
        "glutes-right",
        "hamstrings-left",
        "hamstrings-right",
        "hip-flexors-left",
        "hip-flexors-right",
        "lats-lower-left",
        "lats-lower-right",
        "lats-mid-left",
        "lats-mid-right",
        "lats-upper-left",
        "lats-upper-right",
        "obliques-left",
        "obliques-right",
        "quads-left",
        "quads-right",
        "serratus-anterior-left",
        "serratus-anterior-right",
        "shoulder-front-left",
        "shoulder-front-right",
        "traps-lower-left",
        "traps-lower-right",
        "traps-mid-left",
        "traps-mid-right",
        "traps-upper-left",
        "traps-upper-right",
        "triceps-lateral-left",
        "triceps-lateral-right",
        "triceps-long-left",
        "triceps-long-right",
    }
)

ANATOMY_REGION_LABELS: dict[str, str] = {
    "abs-lower-left": "Lower abs – left",
    "abs-lower-right": "Lower abs – right",
    "abs-upper-left": "Upper abs – left",
    "abs-upper-right": "Upper abs – right",
    "adductors-left": "Adductors – left",
    "adductors-right": "Adductors – right",
    "biceps-left": "Biceps – left",
    "biceps-right": "Biceps – right",
    "calves-left": "Calves – left",
    "calves-right": "Calves – right",
    "chest-lower-left": "Lower chest – left",
    "chest-lower-right": "Lower chest – right",
    "chest-upper-left": "Upper chest – left",
    "chest-upper-right": "Upper chest – right",
    "deltoid-rear-left": "Rear delt – left",
    "deltoid-rear-right": "Rear delt – right",
    "forearm-left": "Forearm – left",
    "forearm-right": "Forearm – right",
    "glutes-left": "Glutes – left",
    "glutes-right": "Glutes – right",
    "hamstrings-left": "Hamstrings – left",
    "hamstrings-right": "Hamstrings – right",
    "hip-flexors-left": "Hip flexor – left",
    "hip-flexors-right": "Hip flexor – right",
    "lats-lower-left": "Lower lats – left",
    "lats-lower-right": "Lower lats – right",
    "lats-mid-left": "Mid lats – left",
    "lats-mid-right": "Mid lats – right",
    "lats-upper-left": "Upper lats – left",
    "lats-upper-right": "Upper lats – right",
    "obliques-left": "Obliques – left",
    "obliques-right": "Obliques – right",
    "quads-left": "Quads – left",
    "quads-right": "Quads – right",
    "serratus-anterior-left": "Serratus – left",
    "serratus-anterior-right": "Serratus – right",
    "shoulder-front-left": "Front delt – left",
    "shoulder-front-right": "Front delt – right",
    "traps-lower-left": "Lower traps – left",
    "traps-lower-right": "Lower traps – right",
    "traps-mid-left": "Mid traps – left",
    "traps-mid-right": "Mid traps – right",
    "traps-upper-left": "Upper traps – left",
    "traps-upper-right": "Upper traps – right",
    "triceps-lateral-left": "Lateral triceps – left",
    "triceps-lateral-right": "Lateral triceps – right",
    "triceps-long-left": "Long-head triceps – left",
    "triceps-long-right": "Long-head triceps – right",
}

ANATOMY_REGION_GROUPS: dict[str, list[str]] = {
    "Chest": ["chest-upper-left", "chest-upper-right", "chest-lower-left", "chest-lower-right"],
    "Back": [
        "traps-upper-left",
        "traps-upper-right",
        "traps-mid-left",
        "traps-mid-right",
        "traps-lower-left",
        "traps-lower-right",
        "lats-upper-left",
        "lats-upper-right",
        "lats-mid-left",
        "lats-mid-right",
        "lats-lower-left",
        "lats-lower-right",
    ],
    "Shoulders": [
        "shoulder-front-left",
        "shoulder-front-right",
        "deltoid-rear-left",
        "deltoid-rear-right",
    ],
    "Arms": [
        "biceps-left",
        "biceps-right",
        "forearm-left",
        "forearm-right",
        "triceps-long-left",
        "triceps-long-right",
        "triceps-lateral-left",
        "triceps-lateral-right",
    ],
    "Core": [
        "abs-upper-left",
        "abs-upper-right",
        "abs-lower-left",
        "abs-lower-right",
        "obliques-left",
        "obliques-right",
        "serratus-anterior-left",
        "serratus-anterior-right",
    ],
    "Legs": [
        "quads-left",
        "quads-right",
        "adductors-left",
        "adductors-right",
        "hamstrings-left",
        "hamstrings-right",
        "glutes-left",
        "glutes-right",
        "calves-left",
        "calves-right",
        "hip-flexors-left",
        "hip-flexors-right",
    ],
}


def anatomy_region_catalog() -> list[dict[str, object]]:
    return [
        {
            "group": group,
            "regions": [{"id": region_id, "label": ANATOMY_REGION_LABELS[region_id]} for region_id in region_ids],
        }
        for group, region_ids in ANATOMY_REGION_GROUPS.items()
    ]


def allows_empty_primary_muscles(muscle_group: str, category: str = "") -> bool:
    normalized_group = muscle_group.strip().lower()
    normalized_category = category.strip().lower()
    return normalized_group == "conditioning" or normalized_category in {"conditioning", "cardio", "recovery"}


def resolve_anatomy_regions(slug: str, muscle_group: str) -> tuple[list[str], list[str]]:
    override = ANATOMY_OVERRIDES.get(slug)
    if override is not None:
        return list(override["primary"]), list(override["secondary"])
    for slugs, anatomy in ISOLATION_RULES:
        if slug in slugs:
            return list(anatomy["primary"]), list(anatomy["secondary"])
    pattern_anatomy = resolve_isolation_pattern(slug)
    if pattern_anatomy is not None:
        return list(pattern_anatomy["primary"]), list(pattern_anatomy["secondary"])
    for slugs, anatomy in VARIANT_ALIAS_RULES:
        if slug in slugs:
            return list(anatomy["primary"]), list(anatomy["secondary"])
    fallback = DEFAULT_ANATOMY_BY_GROUP.get(muscle_group, {"primary": [], "secondary": []})
    return list(fallback["primary"]), list(fallback["secondary"])


def resolve_isolation_pattern(slug: str) -> dict[str, list[str]] | None:
    """Catch imported isolation variants before they fall back to broad groups like Arms.

    Open exercise catalogs often contain hundreds of machine/cable/alternate variants with
    different slugs. Exact overrides remain above this helper; these patterns only prevent
    obviously isolated curls, extensions, raises, and single-joint leg work from inheriting
    unrelated secondary muscles.
    """
    if "wrist-curl" in slug or slug.startswith("wrist-"):
        return {"primary": ["forearm-left", "forearm-right"], "secondary": []}
    if "leg-curl" in slug or "hamstring-curl" in slug:
        return {"primary": ["hamstrings-left", "hamstrings-right"], "secondary": []}
    if "lower-back-curl" in slug:
        return {"primary": ["lats-lower-left", "lats-lower-right"], "secondary": ["glutes-left", "glutes-right", "hamstrings-left", "hamstrings-right"]}
    if "glute-kickback" in slug or "cable-kickback" in slug or "cable-hip-extension" in slug:
        return {"primary": ["glutes-left", "glutes-right"], "secondary": []}
    if "curl" in slug and "leg-curl" not in slug and "wrist-curl" not in slug:
        if any(token in slug for token in ("hammer", "reverse", "zottman")):
            return {"primary": ["biceps-left", "biceps-right", "forearm-left", "forearm-right"], "secondary": []}
        return {"primary": ["biceps-left", "biceps-right"], "secondary": []}
    if any(token in slug for token in ("tricep", "triceps", "pushdown", "skull-crusher")) or slug == "dumbbell-kickback":
        return {
            "primary": ["triceps-long-left", "triceps-long-right", "triceps-lateral-left", "triceps-lateral-right"],
            "secondary": [],
        }
    if any(token in slug for token in ("chest-fly", "cable-fly", "crossover", "pec-deck")):
        return {
            "primary": ["chest-upper-left", "chest-upper-right", "chest-lower-left", "chest-lower-right"],
            "secondary": [],
        }
    if "lateral-raise" in slug:
        return {"primary": ["shoulder-front-left", "shoulder-front-right"], "secondary": []}
    if "front-raise" in slug:
        return {"primary": ["shoulder-front-left", "shoulder-front-right"], "secondary": []}
    if "rear-delt" in slug or "reverse-fly" in slug:
        return {"primary": ["deltoid-rear-left", "deltoid-rear-right"], "secondary": []}
    if "shrug" in slug:
        return {"primary": ["traps-upper-left", "traps-upper-right"], "secondary": ["forearm-left", "forearm-right"]}
    if "leg-extension" in slug:
        return {"primary": ["quads-left", "quads-right"], "secondary": []}
    if "calf-raise" in slug:
        return {"primary": ["calves-left", "calves-right"], "secondary": []}
    if "hip-abduction" in slug or "abductor" in slug:
        return {"primary": ["glutes-left", "glutes-right"], "secondary": []}
    if "hip-adduction" in slug or "adductor" in slug:
        return {"primary": ["adductors-left", "adductors-right"], "secondary": []}
    if "kettlebell-swing" in slug:
        return {"primary": ["glutes-left", "glutes-right", "hamstrings-left", "hamstrings-right"], "secondary": ["abs-upper-left", "abs-upper-right"]}
    if "sled-push" in slug:
        return {"primary": ["quads-left", "quads-right", "glutes-left", "glutes-right"], "secondary": ["hamstrings-left", "hamstrings-right", "calves-left", "calves-right"]}
    return None


def invalid_anatomy_regions(region_ids: Iterable[str]) -> list[str]:
    return sorted({region_id for region_id in region_ids if region_id not in VALID_ANATOMY_REGION_IDS})


def validate_anatomy_assignment(
    slug: str,
    primary: Iterable[str],
    secondary: Iterable[str],
    require_primary: bool = True,
) -> None:
    primary_list = list(primary)
    secondary_list = list(secondary)
    if require_primary and not primary_list:
        raise ValueError(f"Exercise '{slug}' is missing primary anatomy regions.")
    invalid_regions = invalid_anatomy_regions([*primary_list, *secondary_list])
    if invalid_regions:
        raise ValueError(f"Exercise '{slug}' uses unsupported anatomy regions: {', '.join(invalid_regions)}")
