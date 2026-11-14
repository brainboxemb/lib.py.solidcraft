"""Independent expected geometry for native qualification cases.

These values describe the intended Forge contract, not the current SolidCraft
output. Native validators and visual goal overlays consume the same data so a
wrong implementation cannot become its own reference.
"""

EXPECTED_BOUNDS = {
    "simple-box": [
        {"label": "SimpleBox", "min": [-20, -15, 0], "max": [20, 15, 10]},
    ],
    "anchored-holes": [
        {"label": "AnchoredHoles", "min": [0, 0, 0], "max": [100, 60, 10]},
    ],
    "parameter-scope": [
        {"label": "local", "min": [-20, -10, 0], "max": [20, 10, 10]},
        {"label": "override", "min": [70, -10, 0], "max": [130, 10, 10]},
        {"label": "shared_a", "min": [180, -10, 0], "max": [260, 10, 10]},
        {"label": "shared_b", "min": [300, -10, 0], "max": [380, 10, 10]},
        {"label": "derived", "min": [440, -10, 0], "max": [480, 10, 10]},
    ],
    "parent-derived-child-size": [
        {"label": "ParentBlock", "min": [-60, -40, 0], "max": [60, 40, 10]},
        {"label": "DerivedChild", "min": [-30, -20, 20], "max": [30, 20, 26]},
    ],
    "components": [
        {"label": "left", "min": [-20, -15, 0], "max": [20, 15, 10]},
        {"label": "right", "min": [20, -15, 0], "max": [60, 15, 10]},
    ],
    "assembly-decorator": [
        {"label": "left Post", "min": [-20, -5, 0], "max": [-10, 5, 20]},
        {"label": "right Post", "min": [10, -5, 0], "max": [20, 5, 20]},
    ],
    "group-hierarchy": [
        {"label": "left Panel", "min": [-5, -1, 0], "max": [5, 1, 20]},
        {"label": "right Panel", "min": [6, -1, 0], "max": [16, 1, 20]},
        {"label": "root Frame", "min": [-17.5, 15, 0], "max": [17.5, 25, 40]},
    ],
    "attach-angle": [
        {"label": "Base", "min": [-30, -30, 0], "max": [30, 30, 10]},
        {"label": "Arm", "min": [-5, -15, 10], "max": [5, 15, 16]},
    ],
    "as-built-attach": [
        {"label": "Base", "min": [-20, -15, 0], "max": [20, 15, 10]},
        {"label": "Marker", "min": [45, 5, 15], "max": [55, 35, 23]},
    ],
    "parametric-attach": [
        {"label": "Base", "min": [-20, -15, 0], "max": [20, 15, 10]},
        {"label": "Block", "min": [30, -10, 0], "max": [50, 10, 10]},
    ],
    "parametric-offset": [
        {"label": "Base", "min": [-20, -15, 0], "max": [20, 15, 20]},
        {"label": "Marker", "min": [10, -25, 15], "max": [20, -15, 25]},
    ],
    "parametric-anchor": [
        {"label": "Base", "min": [-20, -15, 0], "max": [20, 15, 10]},
        {"label": "Block", "min": [20, -10, 0], "max": [40, 10, 10]},
    ],
    "corner-anchor": [
        {"label": "Base", "min": [-20, -15, 0], "max": [20, 15, 20]},
        {"label": "Marker", "min": [10, -25, 10], "max": [20, -15, 20]},
    ],
    "anchor-topology-mutation": [
        {"label": "Board", "min": [-20, -10, 0], "max": [20, 10, 20]},
        {"label": "Marker", "min": [-25, -20, 15], "max": [-15, -10, 25]},
    ],
    "assembly-owned-anchor": [
        {"label": "Base", "min": [-20, -15, 0], "max": [20, 15, 20]},
        {"label": "Companion", "min": [65, -5, 0], "max": [75, 5, 10]},
        {"label": "Marker", "min": [10, -25, 10], "max": [20, -15, 20]},
    ],
    "four-corner-l": [
        {"label": "FrameBlock", "min": [-60, -40, 0], "max": [60, 40, 60]},
        {"label": "front-left", "min": [-64, -44, 22], "max": [-32, -12, 38]},
        {"label": "front-right", "min": [32, -44, 22], "max": [64, -12, 38]},
        {"label": "rear-right", "min": [32, 12, 22], "max": [64, 44, 38]},
        {"label": "rear-left", "min": [-64, 12, 22], "max": [-32, 44, 38]},
    ],
    "eight-flightcase-corners": [
        {"label": "CaseBlock", "min": [-60, -40, 0], "max": [60, 40, 60]},
        {"label": "front bottom-left", "min": [-64, -44, -4], "max": [-40, -20, 20]},
        {"label": "front bottom-right", "min": [40, -44, -4], "max": [64, -20, 20]},
        {"label": "rear bottom-right", "min": [40, 20, -4], "max": [64, 44, 20]},
        {"label": "rear bottom-left", "min": [-64, 20, -4], "max": [-40, 44, 20]},
        {"label": "front top-left", "min": [-64, -44, 40], "max": [-40, -20, 64]},
        {"label": "front top-right", "min": [40, -44, 40], "max": [64, -20, 64]},
        {"label": "rear top-right", "min": [40, 20, 40], "max": [64, 44, 64]},
        {"label": "rear top-left", "min": [-64, 20, 40], "max": [-40, 44, 64]},
    ],
    "eight-corner-brackets": [
        {"label": "FrameBlock", "min": [-60, -40, 0], "max": [60, 40, 60]},
        {"label": "front-left bottom", "min": [-64, -44, 0], "max": [-32, -12, 16]},
        {"label": "front-left top", "min": [-64, -44, 44], "max": [-32, -12, 60]},
        {"label": "front-right bottom", "min": [32, -44, 0], "max": [64, -12, 16]},
        {"label": "front-right top", "min": [32, -44, 44], "max": [64, -12, 60]},
        {"label": "rear-right bottom", "min": [32, 12, 0], "max": [64, 44, 16]},
        {"label": "rear-right top", "min": [32, 12, 44], "max": [64, 44, 60]},
        {"label": "rear-left bottom", "min": [-64, 12, 0], "max": [-32, 44, 16]},
        {"label": "rear-left top", "min": [-64, 12, 44], "max": [-32, 44, 60]},
    ],
    "custom-anchor": [
        {"label": "Arm", "min": [-5, -20, 0], "max": [5, 20, 10]},
        {"label": "Marker", "min": [-5, 15, 0], "max": [5, 25, 10]},
    ],
    "xz-anchor": [
        {"label": "Board", "min": [-20, 0, 0], "max": [20, 12, 20]},
        {"label": "right Marker", "min": [10, -10, 10], "max": [20, 0, 20]},
        {"label": "left Marker", "min": [-20, -10, 10], "max": [-10, 0, 20]},
    ],
    "history-policy": [
        {"label": "HistoryPolicyBoss", "min": [-25, -25, 0], "max": [25, 25, 16]},
    ],
    "circle-negative-extrude": [
        {"label": "NegativeCircleExtrude", "min": [-10, -10, -30], "max": [10, 10, 0]},
    ],
    "rounded-rectangle-sketch": [
        {"label": "RoundedRectangleSketch", "min": [-40, -30, 0], "max": [40, 30, 13]},
    ],
    "primitive-csg": [
        # The X-axis Ø8 bore removes the sphere's exact X=-20 extremum.
        # Remaining sphere/bore intersection: -sqrt(20^2 - 4^2).
        {"label": "PrimitiveCsg", "min": [-19.595917942265423, -20, 0], "max": [25, 20, 20]},
    ],
    "bracket": [
        {"label": "Bracket", "min": [0, -12, -40], "max": [40, 12, 0]},
    ],
}


EXPECTED_MUTATION_BOUNDS = {
    "assembly-owned-anchor": [
        {"label": "Base", "min": [-40, -15, 0], "max": [40, 15, 40]},
        {"label": "Companion", "min": [65, -5, 0], "max": [75, 5, 10]},
        {"label": "Marker", "min": [30, -25, 30], "max": [40, -15, 40]},
    ],
    "anchor-topology-mutation": [
        {"label": "Board", "min": [-40, -10, 0], "max": [40, 10, 40]},
        {"label": "Marker", "min": [-45, -20, 35], "max": [-35, -10, 45]},
    ],
    "parent-derived-child-size": [
        {"label": "ParentBlock", "min": [-80, -60, 0], "max": [80, 60, 10]},
        {"label": "DerivedChild", "min": [-40, -30, 20], "max": [40, 30, 26]},
    ],
    "parameter-scope": [
        {"label": "local", "min": [-20, -10, 0], "max": [20, 10, 10]},
        {"label": "override", "min": [70, -10, 0], "max": [130, 10, 10]},
        {"label": "shared_a", "min": [170, -10, 0], "max": [270, 10, 10]},
        {"label": "shared_b", "min": [290, -10, 0], "max": [390, 10, 10]},
        {"label": "derived", "min": [435, -10, 0], "max": [485, 10, 10]},
    ],
    "parametric-attach": [
        {"label": "Base", "min": [-20, -15, 0], "max": [20, 15, 10]},
        {"label": "Block", "min": [50, -10, 0], "max": [70, 10, 10]},
    ],
    "parametric-offset": [
        {"label": "Base", "min": [-20, -15, 0], "max": [20, 15, 20]},
        {"label": "Marker", "min": [10, -25, 20], "max": [20, -15, 30]},
    ],
    "parametric-anchor": [
        {"label": "Base", "min": [-40, -15, 0], "max": [40, 15, 10]},
        {"label": "Block", "min": [40, -10, 0], "max": [60, 10, 10]},
    ],
    "corner-anchor": [
        {"label": "Base", "min": [-40, -15, 0], "max": [40, 15, 40]},
        {"label": "Marker", "min": [30, -25, 30], "max": [40, -15, 40]},
    ],
    "four-corner-l": [
        {"label": "FrameBlock", "min": [-80, -60, 0], "max": [80, 60, 60]},
        {"label": "front-left", "min": [-84, -64, 22], "max": [-52, -32, 38]},
        {"label": "front-right", "min": [52, -64, 22], "max": [84, -32, 38]},
        {"label": "rear-right", "min": [52, 32, 22], "max": [84, 64, 38]},
        {"label": "rear-left", "min": [-84, 32, 22], "max": [-52, 64, 38]},
    ],
    "eight-flightcase-corners": [
        {"label": "CaseBlock", "min": [-80, -60, 0], "max": [80, 60, 90]},
        {"label": "front bottom-left", "min": [-84, -64, -4], "max": [-60, -40, 20]},
        {"label": "front bottom-right", "min": [60, -64, -4], "max": [84, -40, 20]},
        {"label": "rear bottom-right", "min": [60, 40, -4], "max": [84, 64, 20]},
        {"label": "rear bottom-left", "min": [-84, 40, -4], "max": [-60, 64, 20]},
        {"label": "front top-left", "min": [-84, -64, 70], "max": [-60, -40, 94]},
        {"label": "front top-right", "min": [60, -64, 70], "max": [84, -40, 94]},
        {"label": "rear top-right", "min": [60, 40, 70], "max": [84, 64, 94]},
        {"label": "rear top-left", "min": [-84, 40, 70], "max": [-60, 64, 94]},
    ],
    "eight-corner-brackets": [
        {"label": "FrameBlock", "min": [-80, -60, 0], "max": [80, 60, 90]},
        {"label": "front-left bottom", "min": [-84, -64, 0], "max": [-52, -32, 16]},
        {"label": "front-left top", "min": [-84, -64, 74], "max": [-52, -32, 90]},
        {"label": "front-right bottom", "min": [52, -64, 0], "max": [84, -32, 16]},
        {"label": "front-right top", "min": [52, -64, 74], "max": [84, -32, 90]},
        {"label": "rear-right bottom", "min": [52, 32, 0], "max": [84, 64, 16]},
        {"label": "rear-right top", "min": [52, 32, 74], "max": [84, 64, 90]},
        {"label": "rear-left bottom", "min": [-84, 32, 0], "max": [-52, 64, 16]},
        {"label": "rear-left top", "min": [-84, 32, 74], "max": [-52, 64, 90]},
    ],
    "xz-anchor": [
        {"label": "Board", "min": [-40, 0, 0], "max": [40, 12, 40]},
        {"label": "right Marker", "min": [30, -10, 30], "max": [40, 0, 40]},
        {"label": "left Marker", "min": [-40, -10, 30], "max": [-30, 0, 40]},
    ],
}


# Visual overlays may use a more detailed decomposition than the Q4 outer
# bounds. In particular an L-profile can be mirrored/rotated incorrectly while
# retaining the same overall bounding box, so draw its two arms separately.
EXPECTED_VISUAL_BOXES = dict(EXPECTED_BOUNDS)

EXPECTED_VISUAL_BOXES["bracket"] = [
    {"label": "arm X", "min": [0, -12, -12], "max": [40, 12, 0]},
    {"label": "arm Z", "min": [0, -12, -40], "max": [12, 12, 0]},
]

EXPECTED_VISUAL_BOXES["four-corner-l"] = [
    {"label": "FrameBlock", "min": [-60, -40, 0], "max": [60, 40, 60]},

    {"label": "FL front arm", "min": [-60, -44, 22], "max": [-32, -40, 38]},
    {"label": "FL left arm", "min": [-64, -40, 22], "max": [-60, -12, 38]},
    {"label": "FR front arm", "min": [32, -44, 22], "max": [60, -40, 38]},
    {"label": "FR right arm", "min": [60, -40, 22], "max": [64, -12, 38]},
    {"label": "RR rear arm", "min": [32, 40, 22], "max": [60, 44, 38]},
    {"label": "RR right arm", "min": [60, 12, 22], "max": [64, 40, 38]},
    {"label": "RL rear arm", "min": [-60, 40, 22], "max": [-32, 44, 38]},
    {"label": "RL left arm", "min": [-64, 12, 22], "max": [-60, 40, 38]},
]

EXPECTED_VISUAL_BOXES["eight-flightcase-corners"] = [
    {"label": "CaseBlock", "min": [-60, -40, 0], "max": [60, 40, 60]},

    {"label": "FBL bottom plate", "min": [-60, -40, -4], "max": [-40, -20, 0]},
    {"label": "FBL front plate", "min": [-60, -44, 0], "max": [-40, -40, 20]},
    {"label": "FBL left plate", "min": [-64, -40, 0], "max": [-60, -20, 20]},

    {"label": "FBR bottom plate", "min": [40, -40, -4], "max": [60, -20, 0]},
    {"label": "FBR front plate", "min": [40, -44, 0], "max": [60, -40, 20]},
    {"label": "FBR right plate", "min": [60, -40, 0], "max": [64, -20, 20]},

    {"label": "RBR bottom plate", "min": [40, 20, -4], "max": [60, 40, 0]},
    {"label": "RBR rear plate", "min": [40, 40, 0], "max": [60, 44, 20]},
    {"label": "RBR right plate", "min": [60, 20, 0], "max": [64, 40, 20]},

    {"label": "RBL bottom plate", "min": [-60, 20, -4], "max": [-40, 40, 0]},
    {"label": "RBL rear plate", "min": [-60, 40, 0], "max": [-40, 44, 20]},
    {"label": "RBL left plate", "min": [-64, 20, 0], "max": [-60, 40, 20]},

    {"label": "FTL top plate", "min": [-60, -40, 60], "max": [-40, -20, 64]},
    {"label": "FTL front plate", "min": [-60, -44, 40], "max": [-40, -40, 60]},
    {"label": "FTL left plate", "min": [-64, -40, 40], "max": [-60, -20, 60]},

    {"label": "FTR top plate", "min": [40, -40, 60], "max": [60, -20, 64]},
    {"label": "FTR front plate", "min": [40, -44, 40], "max": [60, -40, 60]},
    {"label": "FTR right plate", "min": [60, -40, 40], "max": [64, -20, 60]},

    {"label": "RTR top plate", "min": [40, 20, 60], "max": [60, 40, 64]},
    {"label": "RTR rear plate", "min": [40, 40, 40], "max": [60, 44, 60]},
    {"label": "RTR right plate", "min": [60, 20, 40], "max": [64, 40, 60]},

    {"label": "RTL top plate", "min": [-60, 20, 60], "max": [-40, 40, 64]},
    {"label": "RTL rear plate", "min": [-60, 40, 40], "max": [-40, 44, 60]},
    {"label": "RTL left plate", "min": [-64, 20, 40], "max": [-60, 40, 60]},
]

EXPECTED_VISUAL_BOXES["eight-corner-brackets"] = [
    {"label": "FrameBlock", "min": [-60, -40, 0], "max": [60, 40, 60]},

    {"label": "FL bottom front arm", "min": [-60, -44, 0], "max": [-32, -40, 16]},
    {"label": "FL bottom left arm", "min": [-64, -40, 0], "max": [-60, -12, 16]},
    {"label": "FR bottom front arm", "min": [32, -44, 0], "max": [60, -40, 16]},
    {"label": "FR bottom right arm", "min": [60, -40, 0], "max": [64, -12, 16]},
    {"label": "RR bottom rear arm", "min": [32, 40, 0], "max": [60, 44, 16]},
    {"label": "RR bottom right arm", "min": [60, 12, 0], "max": [64, 40, 16]},
    {"label": "RL bottom rear arm", "min": [-60, 40, 0], "max": [-32, 44, 16]},
    {"label": "RL bottom left arm", "min": [-64, 12, 0], "max": [-60, 40, 16]},

    {"label": "FL top front arm", "min": [-60, -44, 44], "max": [-32, -40, 60]},
    {"label": "FL top left arm", "min": [-64, -40, 44], "max": [-60, -12, 60]},
    {"label": "FR top front arm", "min": [32, -44, 44], "max": [60, -40, 60]},
    {"label": "FR top right arm", "min": [60, -40, 44], "max": [64, -12, 60]},
    {"label": "RR top rear arm", "min": [32, 40, 44], "max": [60, 44, 60]},
    {"label": "RR top right arm", "min": [60, 12, 44], "max": [64, 40, 60]},
    {"label": "RL top rear arm", "min": [-60, 40, 44], "max": [-32, 44, 60]},
    {"label": "RL top left arm", "min": [-64, 12, 44], "max": [-60, 40, 60]},

]
