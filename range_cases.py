"""澄川测尺区间交班的手算样例，单位统一为毫米。"""

SPECIMEN = "range-demo"
SCALES = ("A", "B", "C", "D")
MARKS = ("P", "Q", "R", "S")

COUPLED = {"P": (0, 1), "Q": 0, "R": 1}
INDEPENDENT = {"P": 0, "Q": (-1, 0), "R": (0, 1)}
COINCIDENT = {"Q": 0, "R": 0}
COINCIDENCE_PAIRS = (("P", "R"),)
COINCIDENCE_EXPECTED = {
    "coupled": ("conflict", ()),
    "independent": ("signed", ((0, 0),)),
}

TRIPLE_A = {"P": 0, "Q": (1, 3)}
TRIPLE_B = {"Q": 0, "R": 2}
TRIPLE_C = {"P": 0, "R": 1}
TRIPLE_PAIRS = (("Q", "R"), ("R", "Q"), ("P", "R"), ("R", "R"), ("Q", "R"))
TRIPLE_EXPECTED = ((-2, -2), (2, 2), (-1, 1), (0, 0), (-2, -2))
CORRECTION_A = {"Q": (2, 3)}
CORRECTION_EXPECTED = ((-2, -2), (2, 2), (1, 1), (0, 0), (-2, -2))

ISOLATED_D = {"S": -5}
ISOLATED_PAIRS = (("Q", "S"), ("S", "S"), ("P", "Q"))
ISOLATED_EXPECTED = ((None, None), (0, 0), (1, 3))
