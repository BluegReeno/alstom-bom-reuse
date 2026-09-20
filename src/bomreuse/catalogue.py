"""The catalogue: the hand-written, seed-independent story the dataset tells.

Variants, the component master, what every sub-assembly contains in every variant, the
conflicts planted on purpose, the expected answer for each sub-assembly of the newest variant,
and the scripts of the technical notes. Everything here is *true* content: clean references,
true quantities in base units (`pcs`, `m`, `kg`), one true supplier and one true cost. The
dirt is applied later, by `generate.py`, and the seed moves the dirt — never this file
(DECISIONS.md 17).

The story cases of `data/dataset_spec.toml` are **referenced** by id and side, never copied:
two copies of a count is how a generator stops reproducing its contract (DECISIONS.md 23).

All company names are fictional. All data is synthetic (CLAUDE.md, rule 8).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, Literal

from bomreuse.spec import DatasetSpec

# --- shapes --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VariantDef:
    """One intermediate-car configuration. "Newest" is decided by `design_date`, never by the letter."""

    id: str
    name: str
    design_date: str
    region: str
    seats: int
    bike_spaces: int
    traction: str


@dataclass(frozen=True, slots=True)
class ComponentDef:
    """One true product: its clean reference, and the one supplier and cost it truly has."""

    reference: str
    designation: str
    base_unit: str
    supplier: str
    unit_cost: float


@dataclass(frozen=True, slots=True)
class FromStory:
    """The content is one side of a story case of the spec, verbatim."""

    case_id: str
    side: Literal["left", "right"]


@dataclass(frozen=True, slots=True)
class Own:
    """The content is written here: clean reference -> true quantity in the component's base unit."""

    counts: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class SameAs:
    """The very same content as another variant's sub-assembly: identical by construction."""

    variant_id: str
    name: str


@dataclass(frozen=True, slots=True)
class Derived:
    """Another sub-assembly's content, with a few declared changes."""

    variant_id: str
    name: str
    set_quantities: Mapping[str, float] = field(default_factory=dict)
    add: Mapping[str, float] = field(default_factory=dict)
    remove: tuple[str, ...] = ()


Content = FromStory | Own | SameAs | Derived


@dataclass(frozen=True, slots=True)
class SubAssemblyDef:
    """A sub-assembly of one variant. `reference` is the raw string it is emitted under."""

    variant_id: str
    name: str
    reference: str
    content: Content


@dataclass(frozen=True, slots=True)
class LabelDecl:
    """The expected backtest answer for one sub-assembly of the newest variant — declared, not computed.

    `reusable_from` lists the older variants whose sub-assembly of the same name is a valid
    ancestor. For `reused` the ancestors are every older sub-assembly with equal content, which
    needs no declaration. A test confronts all of it with the verdict rule.
    """

    name: str
    label: Literal["reused", "reusable", "new"]
    planted_as: Literal["open_reuse", "hidden_reuse", "near_reuse", "ref_reused_content_changed", "new"]
    story_case_id: str | None = None
    reusable_from: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SupplierOverride:
    """In this variant the component truly comes from someone else: a supplier conflict."""

    reference: str
    variant_id: str
    supplier: str


@dataclass(frozen=True, slots=True)
class CostOverride:
    """In this variant the component truly costs something else: a cost conflict."""

    reference: str
    variant_id: str
    unit_cost: float


@dataclass(frozen=True, slots=True)
class UnitConflict:
    """This one line carries its component in another dimension (reels of cable, not metres).

    The true content does not change — it is the same cable — so the raw strings are given
    literally and no unit noise is applied to them.
    """

    variant_id: str
    sub_assembly: str
    reference: str
    raw_quantity: str
    raw_unit: str


@dataclass(frozen=True, slots=True)
class TypoPlan:
    """A component that gets generated within-reach misspellings.

    `places` forces the `(variant, sub-assembly)` lines; left empty, the seed picks them.
    """

    reference: str
    kind: str
    places: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class FactScript:
    """What a note states. `cited_as` is the spelling the author used, when it is not the clean one."""

    fact_type: Literal["replacement", "obsolescence", "restriction"]
    reference: str
    cited_as: str | None = None
    replaced_by: str | None = None
    effective_date: str | None = None
    scope: str | None = None


@dataclass(frozen=True, slots=True)
class NoteScript:
    """One technical note. A note with no fact carries its literal `text`."""

    variant_id: str
    date: str
    language: Literal["fr", "en", "mixed"]
    fact: FactScript | None = None
    text: str | None = None


# --- variants ------------------------------------------------------------------------------

VARIANTS: Final[tuple[VariantDef, ...]] = (
    VariantDef("A", "Standard intermediate car", "2019-03-14", "Hauts-de-France", 48, 0, "electric"),
    VariantDef("B", "Bike / multi-purpose car", "2021-06-02", "Hauts-de-France", 36, 8, "electric"),
    VariantDef("D", "Bi-mode intermediate car", "2022-09-20", "Normandie", 48, 0, "bi-mode"),
    VariantDef("E", "Standard car, other region", "2023-11-08", "Grand Est", 44, 0, "electric"),
    VariantDef("C", "Bike car, new region", "2025-02-17", "Occitanie", 32, 6, "electric"),
)

#: Which variants a restriction's scope covers. A note says "do not use on bike cars"; this
#: says what a bike car is.
SCOPES: Final[Mapping[str, tuple[str, ...]]] = {
    "bike_car": ("B", "C"),
    "bi_mode": ("D",),
    "standard_car": ("A", "D", "E"),
    "electric": ("A", "B", "C", "E"),
}

# --- suppliers (fictional) -----------------------------------------------------------------

FERROVAL: Final[str] = "Ferroval Systèmes"
NORDRAIL: Final[str] = "Nordrail Composants"
LYS_METAL: Final[str] = "Atelier Lys Métal"
HAINAUT_CABLAGE: Final[str] = "Hainaut Câblage"
SCALDIS: Final[str] = "Scaldis Thermique"
SAMBRE: Final[str] = "Sambre Freinage"
ESCAUT: Final[str] = "Escaut Sièges"
DEULE: Final[str] = "Deûle Électronique"
ARTOIS: Final[str] = "Artois Polymères"
PORTALYS: Final[str] = "Portalys"
TRACTELYS: Final[str] = "Tractelys Énergie"
SANIRAIL: Final[str] = "Sanirail Modules"

# --- component master ----------------------------------------------------------------------
# True ids are assigned in this order (TRUE-0001, ...), skipping the ids the spec reserves.

COMPONENTS: Final[tuple[ComponentDef, ...]] = (
    # Carbody shell
    ComponentDef("SHELL-UNDERFRAME", "Underframe, welded aluminium", "pcs", LYS_METAL, 48200.00),
    ComponentDef("SHELL-SIDEWALL", "Sidewall panel, extruded", "pcs", LYS_METAL, 17650.00),
    ComponentDef("SHELL-ROOF", "Roof assembly", "pcs", LYS_METAL, 15400.00),
    ComponentDef("SHELL-ENDWALL", "Endwall frame", "pcs", LYS_METAL, 6900.00),
    ComponentDef("SHELL-BRACKET-KIT", "Equipment bracket kit", "pcs", LYS_METAL, 412.50),
    ComponentDef("SHELL-SEAL", "Carbody joint seal", "pcs", ARTOIS, 18.40),
    # Trailer bogie
    ComponentDef("BOGIE-FRAME", "Trailer bogie frame", "pcs", FERROVAL, 26800.00),
    ComponentDef("BOGIE-WHEELSET", "Wheelset, 840 mm", "pcs", FERROVAL, 11250.00),
    ComponentDef("BOGIE-PRIMARY-SUSP", "Primary suspension spring set", "pcs", FERROVAL, 1340.00),
    ComponentDef("BOGIE-AIRSPRING", "Secondary air spring", "pcs", ARTOIS, 2875.00),
    ComponentDef("BOGIE-BRAKE-CALIPER", "Brake caliper unit", "pcs", SAMBRE, 3120.00),
    ComponentDef("BOGIE-DAMPER", "Hydraulic damper", "pcs", FERROVAL, 486.00),
    ComponentDef("BOGIE-AXLEBOX", "Axlebox with bearing", "pcs", FERROVAL, 2240.00),
    # Traction package
    ComponentDef("TRAC-CONV-MAIN", "Main traction converter", "pcs", TRACTELYS, 96500.00),
    ComponentDef("TRAC-TRANSFORMER", "Main transformer 25 kV", "pcs", TRACTELYS, 74300.00),
    ComponentDef("TRAC-MOTOR", "Asynchronous traction motor", "pcs", TRACTELYS, 21800.00),
    ComponentDef("TRAC-COOLING-UNIT", "Converter cooling unit", "pcs", SCALDIS, 8650.00),
    ComponentDef("TRAC-HV-CABLE", "High-voltage cable, shielded", "m", HAINAUT_CABLAGE, 64.20),
    ComponentDef("TRAC-CIRCUIT-BREAKER", "Vacuum circuit breaker", "pcs", TRACTELYS, 13900.00),
    ComponentDef("TRAC-EARTH-SWITCH", "Earthing switch", "pcs", TRACTELYS, 4150.00),
    ComponentDef("TRAC-CTRL-RACK", "Traction control rack", "pcs", DEULE, 17200.00),
    ComponentDef("TRAC-SENSOR-KIT", "Speed and current sensor kit", "pcs", DEULE, 940.00),
    ComponentDef("TRAC-BUSBAR", "Copper busbar", "pcs", HAINAUT_CABLAGE, 215.00),
    ComponentDef("TRAC-INSULATOR", "Roof insulator", "pcs", TRACTELYS, 178.00),
    ComponentDef("TRAC-FIX-KIT", "Traction equipment fixing kit", "pcs", LYS_METAL, 96.50),
    ComponentDef("TRAC-DIESEL-GENSET", "Diesel generator set", "pcs", TRACTELYS, 118000.00),
    ComponentDef("TRAC-FUEL-TANK", "Fuel tank 1200 l", "pcs", LYS_METAL, 9400.00),
    ComponentDef("TRAC-EXHAUST-KIT", "Exhaust and after-treatment kit", "pcs", SCALDIS, 14250.00),
    # Passenger door set
    ComponentDef("DOOR-LEAF", "Sliding-plug door leaf", "pcs", PORTALYS, 3980.00),
    ComponentDef("DOOR-DRIVE-UNIT", "Door drive unit", "pcs", PORTALYS, 5240.00),
    ComponentDef("DOOR-GUIDE-RAIL", "Door guide rail", "pcs", PORTALYS, 612.00),
    ComponentDef("DOOR-SEAL", "Door leaf seal", "pcs", ARTOIS, 74.00),
    ComponentDef("DOOR-OBSTACLE-SENSOR", "Obstacle detection sensor", "pcs", DEULE, 328.00),
    ComponentDef("DOOR-CTRL-UNIT", "Door control unit", "pcs", DEULE, 2150.00),
    ComponentDef("DOOR-PUSHBUTTON-INT", "Interior push button", "pcs", DEULE, 86.00),
    ComponentDef("DOOR-PUSHBUTTON-INT-LED", "Interior push button, LED ring", "pcs", DEULE, 104.00),
    ComponentDef("DOOR-PUSHBUTTON-EXT", "Exterior push button", "pcs", DEULE, 112.00),
    ComponentDef("DOOR-EMERG-HANDLE", "Emergency egress handle", "pcs", PORTALYS, 265.00),
    ComponentDef("DOOR-STEP-PLATE", "Step plate", "pcs", LYS_METAL, 540.00),
    ComponentDef("DOOR-THRESHOLD", "Threshold profile", "pcs", LYS_METAL, 298.00),
    ComponentDef("DOOR-HARNESS", "Door wiring harness", "pcs", HAINAUT_CABLAGE, 386.00),
    ComponentDef("DOOR-LOCK", "Door locking device", "pcs", PORTALYS, 447.00),
    ComponentDef("DOOR-DAMPER", "Door end-stop damper", "pcs", PORTALYS, 58.50),
    ComponentDef("DOOR-PICTO", "Door pictogram", "pcs", ARTOIS, 6.80),
    ComponentDef("DOOR-FIX-KIT", "Door fixing kit", "pcs", LYS_METAL, 72.00),
    ComponentDef("DOOR-GAP-FILLER", "Platform gap filler", "pcs", PORTALYS, 1875.00),
    # Passenger information system
    ComponentDef("PIS-DISPLAY-INT", "Interior TFT display", "pcs", DEULE, 1480.00),
    ComponentDef("PIS-DISPLAY-EXT", "Exterior LED destination display", "pcs", DEULE, 2360.00),
    ComponentDef("PIS-SPEAKER", "Saloon loudspeaker", "pcs", DEULE, 64.00),
    ComponentDef("PIS-CONTROLLER", "PIS controller", "pcs", DEULE, 5720.00),
    ComponentDef("PIS-CABLE-TRUNK", "PIS cable trunk", "m", HAINAUT_CABLAGE, 12.60),
    ComponentDef("PIS-SIGN-STD", "Standard signage plate", "pcs", ARTOIS, 9.50),
    ComponentDef("PIS-SIGN-BIKE", "Bike area signage plate", "pcs", ARTOIS, 11.20),
    ComponentDef("PIS-SIGN-REGION", "Regional livery signage plate", "pcs", ARTOIS, 14.00),
    # Seating module
    ComponentDef("SEAT-FIX-DBL", "Fixed double seat", "pcs", ESCAUT, 1260.00),
    ComponentDef("SEAT-RAIL", "Seat mounting rail", "pcs", LYS_METAL, 184.00),
    ComponentDef("SEAT-FIX-KIT", "Seat fixing kit", "pcs", LYS_METAL, 23.50),
    ComponentDef("SEAT-TABLE", "Fixed table", "pcs", ESCAUT, 395.00),
    ComponentDef("SEAT-GRAB-HANDLE", "Seat-back grab handle", "pcs", ESCAUT, 31.00),
    ComponentDef("SEAT-END-PANEL", "Seat row end panel", "pcs", ESCAUT, 142.00),
    ComponentDef("SEAT-TIPUP", "Tip-up seat", "pcs", ESCAUT, 610.00),
    # Floor and wall anchorage
    ComponentDef("ANCH-SEAT-RAIL", "Floor anchorage rail", "pcs", LYS_METAL, 226.00),
    ComponentDef("ANCH-RAIL-BOLT", "Anchorage rail bolt", "pcs", NORDRAIL, 1.85),
    ComponentDef("ANCH-FLOOR-PLATE", "Floor anchorage plate", "pcs", LYS_METAL, 47.00),
    ComponentDef("ANCH-SHIM", "Levelling shim", "pcs", NORDRAIL, 2.40),
    ComponentDef("ANCH-HOOK-POINT", "Bike hook anchor point", "pcs", LYS_METAL, 38.00),
    ComponentDef("ANCH-BIKE-PLATE", "Bike zone anchorage plate", "pcs", LYS_METAL, 89.00),
    ComponentDef("ANCH-BIKE-BOLT", "Bike zone anchorage bolt", "pcs", NORDRAIL, 2.10),
    ComponentDef("ANCH-WALL-BRACKET", "Wall anchorage bracket", "pcs", LYS_METAL, 132.00),
    ComponentDef("ANCH-REINF-PANEL", "Wall reinforcement panel", "pcs", LYS_METAL, 418.00),
    # Bike module
    ComponentDef("BIKE-HOOK", "Vertical bike hook", "pcs", NORDRAIL, 148.00),
    ComponentDef("BIKE-RAIL", "Bike module carrier rail", "pcs", LYS_METAL, 365.00),
    ComponentDef("BIKE-STRAP", "Bike retaining strap", "pcs", ARTOIS, 12.90),
    ComponentDef("BIKE-FIX-KIT", "Bike rail fixing kit", "pcs", LYS_METAL, 27.00),
    ComponentDef("BIKE-FLOOR-MAT", "Bike zone floor mat", "pcs", ARTOIS, 286.00),
    ComponentDef("BIKE-PICTO", "Bike zone pictogram", "pcs", ARTOIS, 7.40),
    # HVAC unit
    ComponentDef("HVAC-COMPRESSOR", "Scroll compressor", "pcs", SCALDIS, 4380.00),
    ComponentDef("HVAC-CONDENSER", "Condenser coil", "pcs", SCALDIS, 2140.00),
    ComponentDef("HVAC-EVAPORATOR", "Evaporator coil", "pcs", SCALDIS, 1960.00),
    ComponentDef("HVAC-FAN-SUPPLY", "Supply air fan", "pcs", SCALDIS, 735.00),
    ComponentDef("HVAC-FILTER", "Fresh air filter G4", "pcs", SCALDIS, 38.00),
    ComponentDef("HVAC-DUCT-MAIN", "Main air duct", "m", ARTOIS, 96.00),
    ComponentDef("HVAC-CTRL-BOARD", "HVAC control board", "pcs", DEULE, 1820.00),
    ComponentDef("HVAC-TEMP-SENSOR", "Saloon temperature sensor", "pcs", DEULE, 54.00),
    ComponentDef("HVAC-GRILLE-12", "Air outlet grille type 12", "pcs", ARTOIS, 42.00),
    ComponentDef("HVAC-GRILLE-1L", "Air outlet grille, left-hand", "pcs", ARTOIS, 46.50),
    ComponentDef("HVAC-REFRIGERANT", "Refrigerant R-513A charge", "kg", SCALDIS, 31.00),
    ComponentDef("BGI-2031", "Bolt set M8, zinc-nickel", "pcs", NORDRAIL, 0.85),
    # Braking unit
    ComponentDef("BRK-COMPRESSOR", "Oil-free air compressor", "pcs", SAMBRE, 18700.00),
    ComponentDef("BRK-AIR-TANK", "Air reservoir 100 l", "pcs", SAMBRE, 1240.00),
    ComponentDef("BRK-CTRL-VALVE", "Brake control valve", "pcs", SAMBRE, 2680.00),
    ComponentDef("BRK-PIPE-STEEL", "Brake pipe, stainless", "m", SAMBRE, 28.50),
    ComponentDef("BRK-HOSE-FLEX", "Flexible brake hose", "pcs", SAMBRE, 93.00),
    ComponentDef("BRK-DRYER", "Air dryer", "pcs", SAMBRE, 3150.00),
    ComponentDef("BRK-PRESSURE-SENSOR", "Pressure transducer", "pcs", DEULE, 187.00),
    ComponentDef("BRK-ECU", "Brake electronic control unit", "pcs", DEULE, 9800.00),
    ComponentDef("BRK-PARKING-ACT", "Parking brake actuator", "pcs", SAMBRE, 2260.00),
    ComponentDef("BRK-BRACKET", "Pipe support bracket", "pcs", LYS_METAL, 14.20),
    # Gangway and couplers
    ComponentDef("GANG-BELLOWS", "Gangway bellows", "pcs", ARTOIS, 12400.00),
    ComponentDef("GANG-FRAME", "Gangway frame", "pcs", LYS_METAL, 5350.00),
    ComponentDef("GANG-BRIDGE-PLATE", "Gangway bridge plate", "pcs", LYS_METAL, 1980.00),
    ComponentDef("GANG-SEAL-PROFILE", "Gangway seal profile", "m", ARTOIS, 22.80),
    ComponentDef("COUP-SEMI-PERM", "Semi-permanent coupler", "pcs", FERROVAL, 15800.00),
    ComponentDef("COUP-DRAFT-GEAR", "Draft gear", "pcs", FERROVAL, 6240.00),
    ComponentDef("COUP-ELEC-HEAD", "Electrical coupler head", "pcs", HAINAUT_CABLAGE, 4470.00),
    ComponentDef("COUP-JUMPER-CABLE", "Inter-car jumper cable", "m", HAINAUT_CABLAGE, 148.00),
    ComponentDef("GANG-HANDRAIL", "Gangway handrail", "pcs", LYS_METAL, 215.00),
    ComponentDef("DOOR-SEAL-O", "Gangway door seal, outer", "pcs", ARTOIS, 81.00),
    # Auxiliary converter
    ComponentDef("AUX-INVERTER", "Auxiliary inverter 60 kVA", "pcs", TRACTELYS, 34600.00),
    ComponentDef("AUX-CAP-BANK", "DC-link capacitor bank", "pcs", TRACTELYS, 2890.00),
    ComponentDef("AUX-BATTERY-CHARGER", "Battery charger 24 V", "pcs", TRACTELYS, 7350.00),
    ComponentDef("AUX-BATTERY-PACK", "NiCd battery pack", "pcs", TRACTELYS, 9120.00),
    ComponentDef("AUX-FILTER-CHOKE", "Input filter choke", "pcs", TRACTELYS, 3480.00),
    ComponentDef("AUX-COOLING-FAN", "Converter cooling fan", "pcs", SCALDIS, 640.00),
    ComponentDef("AUX-CONTACTOR", "Power contactor", "pcs", DEULE, 385.00),
    ComponentDef("AUX-FUSE-BOX", "Fuse box", "pcs", DEULE, 520.00),
    ComponentDef("AUX-LV-CABLE", "Low-voltage power cable", "m", HAINAUT_CABLAGE, 9.40),
    ComponentDef("AUX-ENCLOSURE", "Underfloor enclosure", "pcs", LYS_METAL, 4250.00),
    # Interior lighting
    ComponentDef("LIGHT-LED-STRIP", "LED light strip 1200 mm", "pcs", DEULE, 118.00),
    ComponentDef("LIGHT-DRIVER", "LED driver", "pcs", DEULE, 96.00),
    ComponentDef("LIGHT-EMERG-UNIT", "Emergency lighting unit", "pcs", DEULE, 274.00),
    ComponentDef("LIGHT-DIFFUSER", "Light diffuser", "pcs", ARTOIS, 33.00),
    ComponentDef("LIGHT-CABLE", "Lighting cable", "m", HAINAUT_CABLAGE, 3.20),
    ComponentDef("LIGHT-SWITCH-PANEL", "Lighting switch panel", "pcs", DEULE, 460.00),
    ComponentDef("LIGHT-SENSOR-AMB", "Ambient light sensor", "pcs", DEULE, 72.00),
    ComponentDef("LIGHT-READING-SPOT", "Reading spot", "pcs", DEULE, 58.00),
    ComponentDef("LIGHT-CONNECTOR", "Lighting connector", "pcs", HAINAUT_CABLAGE, 2.70),
    ComponentDef("LIGHT-CLIP", "Cable clip", "pcs", NORDRAIL, 0.35),
    # Floor and wall panels
    ComponentDef("PANEL-FLOOR-PLY", "Plywood floor panel", "pcs", ARTOIS, 385.00),
    ComponentDef("PANEL-FLOOR-COVER", "Rubber floor covering", "m", ARTOIS, 58.00),
    ComponentDef("PANEL-WALL-GRP", "GRP wall panel", "pcs", ARTOIS, 640.00),
    ComponentDef("PANEL-CEILING", "Ceiling panel", "pcs", ARTOIS, 512.00),
    ComponentDef("PANEL-INSUL-MAT", "Thermal insulation mat", "kg", ARTOIS, 7.60),
    ComponentDef("PANEL-ADHESIVE", "Structural adhesive", "kg", ARTOIS, 24.50),
    ComponentDef("PANEL-TRIM-PROFILE", "Trim profile", "m", LYS_METAL, 11.80),
    ComponentDef("PANEL-SCREW-KIT", "Panel screw kit", "pcs", NORDRAIL, 6.30),
    ComponentDef("SEAT-FIX-KIT-4471", "Floor insert kit for seat fixing", "pcs", NORDRAIL, 19.90),
    ComponentDef("SEAT-RAIL-I", "Floor rail, stainless steel", "pcs", LYS_METAL, 312.00),
    ComponentDef("HVAC-GRILLE-11", "Wall ventilation grille type 11", "pcs", ARTOIS, 39.00),
    # Toilet module (older variants)
    ComponentDef("WC-CABIN-SHELL", "Toilet cabin shell", "pcs", SANIRAIL, 14800.00),
    ComponentDef("WC-BOWL-VACUUM", "Vacuum toilet bowl", "pcs", SANIRAIL, 3260.00),
    ComponentDef("WC-WATER-TANK", "Fresh water tank 120 l", "pcs", SANIRAIL, 1840.00),
    ComponentDef("WC-WASTE-TANK", "Waste retention tank 300 l", "pcs", SANIRAIL, 2970.00),
    ComponentDef("WC-WASHBASIN", "Washbasin unit", "pcs", SANIRAIL, 1120.00),
    ComponentDef("WC-DOOR-SLIDING", "Manual sliding toilet door", "pcs", SANIRAIL, 2380.00),
    ComponentDef("WC-VACUUM-PUMP", "Vacuum generator", "pcs", SANIRAIL, 4150.00),
    ComponentDef("WC-PIPE-KIT", "Toilet pipework kit", "pcs", SANIRAIL, 860.00),
    ComponentDef("WC-SEALANT", "Sanitary sealant", "kg", ARTOIS, 18.00),
    ComponentDef("WC-GRAB-BAR", "Toilet grab bar", "pcs", LYS_METAL, 128.00),
    ComponentDef("SEAT-RAIL-1", "Mounting rail, aluminium, mark 1", "pcs", LYS_METAL, 121.00),
    ComponentDef("DOOR-SEAL-0", "Inner door seal, revision 0", "pcs", ARTOIS, 52.00),
    # Toilet module (newest variant: universal PRM toilet, all new)
    ComponentDef("WCU-CABIN-PRM", "Universal toilet cabin, PRM", "pcs", SANIRAIL, 23600.00),
    ComponentDef("WCU-BOWL-VACUUM-G2", "Vacuum toilet bowl, generation 2", "pcs", SANIRAIL, 3840.00),
    ComponentDef("WCU-TANK-COMBO", "Combined fresh and waste tank", "pcs", SANIRAIL, 5120.00),
    ComponentDef("WCU-WASHBASIN-PRM", "Washbasin unit, PRM height", "pcs", SANIRAIL, 1490.00),
    ComponentDef("WCU-DOOR-POWERED", "Powered curved toilet door", "pcs", SANIRAIL, 6750.00),
    ComponentDef("WCU-CALL-ALARM", "Assistance call alarm", "pcs", DEULE, 245.00),
    ComponentDef("WCU-GRAB-BAR-FOLD", "Folding grab bar", "pcs", LYS_METAL, 296.00),
    ComponentDef("WCU-CHANGING-TABLE", "Baby changing table", "pcs", SANIRAIL, 870.00),
    ComponentDef("WCU-PIPE-KIT", "Universal toilet pipework kit", "pcs", SANIRAIL, 1180.00),
    ComponentDef("WCU-FLOOR-TRAY", "Sealed floor tray", "pcs", ARTOIS, 1340.00),
    # Known only through the notes: the parts that replace something
    ComponentDef("BIKE-STRAP-V2", "Bike retaining strap, version 2", "pcs", ARTOIS, 15.60),
    ComponentDef("HVAC-FILTER-F9", "Fresh air filter F9", "pcs", SCALDIS, 61.00),
    ComponentDef("WC-VACUUM-PUMP-G2", "Vacuum generator, generation 2", "pcs", SANIRAIL, 4580.00),
    ComponentDef("TRAC-TRANSFORMER-LW", "Main transformer, lightweight", "pcs", TRACTELYS, 81900.00),
    ComponentDef("HVAC-CTRL-BOARD-R2", "HVAC control board, revision 2", "pcs", DEULE, 1940.00),
    ComponentDef("PIS-SIGN-STD-V2", "Standard signage plate, version 2", "pcs", ARTOIS, 10.10),
    ComponentDef("SEAT-TIPUP-SOFT", "Tip-up seat, soft-close", "pcs", ESCAUT, 655.00),
    ComponentDef("LIGHT-EMERG-UNIT-LI", "Emergency lighting unit, lithium", "pcs", DEULE, 312.00),
)

# --- contents of the non-story sub-assemblies ----------------------------------------------

_HVAC_UNIT: Final[Own] = Own(
    {
        "HVAC-COMPRESSOR": 2,
        "HVAC-CONDENSER": 2,
        "HVAC-EVAPORATOR": 2,
        "HVAC-FAN-SUPPLY": 4,
        "HVAC-FILTER": 8,
        "HVAC-DUCT-MAIN": 18.5,
        "HVAC-CTRL-BOARD": 1,
        "HVAC-TEMP-SENSOR": 6,
        "HVAC-GRILLE-12": 16,
        "HVAC-GRILLE-1L": 2,
        "HVAC-REFRIGERANT": 6.5,
        "BGI-2031": 24,
    }
)

_BRAKING_UNIT: Final[Own] = Own(
    {
        "BRK-COMPRESSOR": 1,
        "BRK-AIR-TANK": 2,
        "BRK-CTRL-VALVE": 4,
        "BRK-PIPE-STEEL": 32.0,
        "BRK-HOSE-FLEX": 8,
        "BRK-DRYER": 1,
        "BRK-PRESSURE-SENSOR": 6,
        "BRK-ECU": 1,
        "BRK-PARKING-ACT": 2,
        "BRK-BRACKET": 12,
        "BGI-2031": 36,
    }
)

_GANGWAY: Final[Own] = Own(
    {
        "GANG-BELLOWS": 2,
        "GANG-FRAME": 2,
        "GANG-BRIDGE-PLATE": 2,
        "GANG-SEAL-PROFILE": 14.4,
        "COUP-SEMI-PERM": 2,
        "COUP-DRAFT-GEAR": 2,
        "COUP-ELEC-HEAD": 2,
        "COUP-JUMPER-CABLE": 9.6,
        "GANG-HANDRAIL": 4,
        "DOOR-SEAL-O": 4,
        "BGI-2031": 48,
    }
)

_AUX_CONVERTER: Final[Own] = Own(
    {
        "AUX-INVERTER": 1,
        "AUX-CAP-BANK": 2,
        "AUX-BATTERY-CHARGER": 1,
        "AUX-BATTERY-PACK": 2,
        "AUX-FILTER-CHOKE": 1,
        "AUX-COOLING-FAN": 2,
        "AUX-CONTACTOR": 4,
        "AUX-FUSE-BOX": 1,
        "AUX-LV-CABLE": 28.0,
        "AUX-ENCLOSURE": 1,
        "BGI-2031": 16,
    }
)

_LIGHTING: Final[Own] = Own(
    {
        "LIGHT-LED-STRIP": 24,
        "LIGHT-DRIVER": 6,
        "LIGHT-EMERG-UNIT": 4,
        "LIGHT-DIFFUSER": 24,
        "LIGHT-CABLE": 45.0,
        "LIGHT-SWITCH-PANEL": 1,
        "LIGHT-SENSOR-AMB": 2,
        "LIGHT-READING-SPOT": 12,
        "LIGHT-CONNECTOR": 48,
        "LIGHT-CLIP": 96,
    }
)

_PANELS: Final[Own] = Own(
    {
        "PANEL-FLOOR-PLY": 14,
        "PANEL-FLOOR-COVER": 38.5,
        "PANEL-WALL-GRP": 16,
        "PANEL-CEILING": 12,
        "PANEL-INSUL-MAT": 22.0,
        "PANEL-ADHESIVE": 7.5,
        "PANEL-TRIM-PROFILE": 52.0,
        "PANEL-SCREW-KIT": 40,
        "SEAT-FIX-KIT-4471": 12,
        "SEAT-RAIL-I": 6,
        "HVAC-GRILLE-11": 4,
    }
)

_TOILET_LEGACY: Final[Own] = Own(
    {
        "WC-CABIN-SHELL": 1,
        "WC-BOWL-VACUUM": 1,
        "WC-WATER-TANK": 1,
        "WC-WASTE-TANK": 1,
        "WC-WASHBASIN": 1,
        "WC-DOOR-SLIDING": 1,
        "WC-VACUUM-PUMP": 1,
        "WC-PIPE-KIT": 1,
        "WC-SEALANT": 1.5,
        "WC-GRAB-BAR": 2,
        "SEAT-RAIL-1": 2,
        "DOOR-SEAL-0": 2,
    }
)

_TOILET_UNIVERSAL: Final[Own] = Own(
    {
        "WCU-CABIN-PRM": 1,
        "WCU-BOWL-VACUUM-G2": 1,
        "WCU-TANK-COMBO": 1,
        "WCU-WASHBASIN-PRM": 1,
        "WCU-DOOR-POWERED": 1,
        "WCU-CALL-ALARM": 2,
        "WCU-GRAB-BAR-FOLD": 2,
        "WCU-CHANGING-TABLE": 1,
        "WCU-PIPE-KIT": 1,
        "WCU-FLOOR-TRAY": 1,
    }
)

_ANCHORAGE_BIKE_CAR: Final[Own] = Own(
    {
        "ANCH-SEAT-RAIL": 10,
        "ANCH-RAIL-BOLT": 80,
        "ANCH-FLOOR-PLATE": 10,
        "ANCH-SHIM": 20,
        "ANCH-HOOK-POINT": 8,
    }
)

# --- sub-assemblies, variant by variant ----------------------------------------------------
# Older variants use SA-dddd, shared when the content is shared. The newest variant was
# designed in another office: new references under another scheme, one reference mistyped,
# one kept although its content changed.

SHELL: Final[str] = "Carbody shell"
HVAC: Final[str] = "HVAC unit"
BRAKING: Final[str] = "Braking unit"
GANGWAY: Final[str] = "Gangway and couplers"
BOGIE: Final[str] = "Trailer bogie"
TRACTION: Final[str] = "Traction package"
AUX: Final[str] = "Auxiliary converter"
LIGHTING: Final[str] = "Interior lighting"
PANELS: Final[str] = "Floor and wall panels"
BIKE: Final[str] = "Bike module"
DOORS: Final[str] = "Passenger door set"
PIS: Final[str] = "Passenger information system"
SEATING: Final[str] = "Seating module"
ANCHORAGE: Final[str] = "Floor and wall anchorage"
TOILET: Final[str] = "Toilet module"

#: The sub-assemblies whose content comes from, or derives from, a story case of the spec.
STORY_SUB_ASSEMBLIES: Final[frozenset[str]] = frozenset({SHELL, BOGIE, TRACTION, BIKE, DOORS, PIS, SEATING, ANCHORAGE})

SUB_ASSEMBLIES: Final[tuple[SubAssemblyDef, ...]] = (
    # A — standard intermediate car
    SubAssemblyDef("A", SHELL, "SA-0101", FromStory("carbody_shell_identical", "left")),
    SubAssemblyDef("A", HVAC, "SA-0104", _HVAC_UNIT),
    SubAssemblyDef("A", BRAKING, "SA-0105", _BRAKING_UNIT),
    SubAssemblyDef("A", GANGWAY, "SA-0106", _GANGWAY),
    SubAssemblyDef("A", BOGIE, "SA-0102", FromStory("trailer_bogie_identical", "left")),
    SubAssemblyDef("A", TRACTION, "SA-0103", FromStory("traction_package_bimode_specific", "left")),
    SubAssemblyDef("A", AUX, "SA-0107", _AUX_CONVERTER),
    SubAssemblyDef("A", LIGHTING, "SA-0108", _LIGHTING),
    SubAssemblyDef("A", PANELS, "SA-0109", _PANELS),
    SubAssemblyDef("A", DOORS, "SA-0111", FromStory("passenger_door_set_reusable", "left")),
    SubAssemblyDef("A", PIS, "SA-0112", FromStory("pis_bike_pictograms", "left")),
    SubAssemblyDef("A", SEATING, "SA-0113", FromStory("seating_module_tipup", "left")),
    SubAssemblyDef("A", ANCHORAGE, "SA-0114", FromStory("floor_wall_anchorage_new", "left")),
    SubAssemblyDef("A", TOILET, "SA-0110", _TOILET_LEGACY),
    # B — bike / multi-purpose car
    SubAssemblyDef("B", SHELL, "SA-0101", FromStory("carbody_shell_identical", "right")),
    SubAssemblyDef("B", HVAC, "SA-0104", SameAs("A", HVAC)),
    SubAssemblyDef("B", BRAKING, "SA-0105", SameAs("A", BRAKING)),
    SubAssemblyDef("B", GANGWAY, "SA-0106", SameAs("A", GANGWAY)),
    SubAssemblyDef("B", BOGIE, "SA-0102", SameAs("A", BOGIE)),
    SubAssemblyDef("B", TRACTION, "SA-0103", SameAs("A", TRACTION)),
    SubAssemblyDef("B", AUX, "SA-0107", SameAs("A", AUX)),
    SubAssemblyDef("B", LIGHTING, "SA-0108", SameAs("A", LIGHTING)),
    SubAssemblyDef("B", PANELS, "SA-0109", SameAs("A", PANELS)),
    SubAssemblyDef("B", BIKE, "SA-0215", FromStory("bike_module_two_fewer_hooks", "left")),
    SubAssemblyDef("B", DOORS, "SA-0111", SameAs("A", DOORS)),
    SubAssemblyDef("B", PIS, "SA-0212", FromStory("pis_bike_pictograms", "right")),
    SubAssemblyDef("B", SEATING, "SA-0213", FromStory("seating_module_tipup", "right")),
    SubAssemblyDef("B", ANCHORAGE, "SA-0214", _ANCHORAGE_BIKE_CAR),
    SubAssemblyDef("B", TOILET, "SA-0110", SameAs("A", TOILET)),
    # D — bi-mode intermediate car
    SubAssemblyDef("D", SHELL, "SA-0101", SameAs("A", SHELL)),
    SubAssemblyDef("D", HVAC, "SA-0104", SameAs("A", HVAC)),
    SubAssemblyDef("D", BRAKING, "SA-0105", SameAs("A", BRAKING)),
    SubAssemblyDef("D", GANGWAY, "SA-0106", SameAs("A", GANGWAY)),
    SubAssemblyDef("D", BOGIE, "SA-0102", SameAs("A", BOGIE)),
    SubAssemblyDef("D", TRACTION, "SA-0403", FromStory("traction_package_bimode_specific", "right")),
    SubAssemblyDef("D", AUX, "SA-0107", SameAs("A", AUX)),
    SubAssemblyDef("D", LIGHTING, "SA-0108", SameAs("A", LIGHTING)),
    SubAssemblyDef("D", PANELS, "SA-0109", SameAs("A", PANELS)),
    SubAssemblyDef("D", DOORS, "SA-0111", SameAs("A", DOORS)),
    SubAssemblyDef("D", PIS, "SA-0112", SameAs("A", PIS)),
    SubAssemblyDef("D", SEATING, "SA-0113", SameAs("A", SEATING)),
    SubAssemblyDef("D", ANCHORAGE, "SA-0114", SameAs("A", ANCHORAGE)),
    SubAssemblyDef("D", TOILET, "SA-0110", SameAs("A", TOILET)),
    # E — standard car, other region
    SubAssemblyDef("E", SHELL, "SA-0101", SameAs("A", SHELL)),
    SubAssemblyDef("E", HVAC, "SA-0104", SameAs("A", HVAC)),
    SubAssemblyDef("E", BRAKING, "SA-0105", SameAs("A", BRAKING)),
    SubAssemblyDef("E", GANGWAY, "SA-0106", SameAs("A", GANGWAY)),
    SubAssemblyDef("E", BOGIE, "SA-0102", SameAs("A", BOGIE)),
    SubAssemblyDef("E", TRACTION, "SA-0103", SameAs("A", TRACTION)),
    SubAssemblyDef("E", AUX, "SA-0107", SameAs("A", AUX)),
    SubAssemblyDef("E", LIGHTING, "SA-0108", SameAs("A", LIGHTING)),
    SubAssemblyDef("E", PANELS, "SA-0109", SameAs("A", PANELS)),
    SubAssemblyDef("E", DOORS, "SA-0111", SameAs("A", DOORS)),
    SubAssemblyDef("E", PIS, "SA-0112", SameAs("A", PIS)),
    SubAssemblyDef("E", SEATING, "SA-0513", Derived("A", SEATING, set_quantities={"SEAT-FIX-DBL": 22, "SEAT-FIX-KIT": 22})),
    SubAssemblyDef("E", ANCHORAGE, "SA-0114", SameAs("A", ANCHORAGE)),
    SubAssemblyDef("E", TOILET, "SA-0110", SameAs("A", TOILET)),
    # C — bike car for a new region: the newest variant, the backtest target
    SubAssemblyDef("C", SHELL, "SA-0101", SameAs("A", SHELL)),
    SubAssemblyDef("C", HVAC, "SA-0104", SameAs("A", HVAC)),
    SubAssemblyDef("C", BRAKING, "SA-0105", SameAs("A", BRAKING)),
    SubAssemblyDef("C", GANGWAY, "SA-0106", SameAs("A", GANGWAY)),
    SubAssemblyDef("C", BOGIE, "OCC-SA-0302", FromStory("trailer_bogie_identical", "right")),
    SubAssemblyDef("C", TRACTION, "OCC-SA-0303", SameAs("A", TRACTION)),
    SubAssemblyDef("C", AUX, "SA-O107", SameAs("A", AUX)),  # A's SA-0107, mistyped: a letter O for the zero
    SubAssemblyDef("C", LIGHTING, "OCC-SA-0308", SameAs("A", LIGHTING)),
    SubAssemblyDef("C", PANELS, "OCC-SA-0309", SameAs("A", PANELS)),
    SubAssemblyDef("C", BIKE, "OCC-SA-0315", FromStory("bike_module_two_fewer_hooks", "right")),
    SubAssemblyDef("C", DOORS, "OCC-SA-0311", FromStory("passenger_door_set_reusable", "right")),
    SubAssemblyDef("C", PIS, "OCC-SA-0312", Derived("B", PIS, add={"PIS-SIGN-REGION": 2})),
    # B's reference kept although the seat count changed: the exact-reference search's false positive.
    SubAssemblyDef("C", SEATING, "SA-0213", Derived("B", SEATING, set_quantities={"SEAT-FIX-DBL": 16, "SEAT-FIX-KIT": 16})),
    SubAssemblyDef("C", ANCHORAGE, "OCC-SA-0314", FromStory("floor_wall_anchorage_new", "right")),
    SubAssemblyDef("C", TOILET, "OCC-SA-0310", _TOILET_UNIVERSAL),
)

# --- the expected answers for the newest variant -------------------------------------------

LABELS: Final[tuple[LabelDecl, ...]] = (
    LabelDecl(SHELL, "reused", "open_reuse"),
    LabelDecl(HVAC, "reused", "open_reuse"),
    LabelDecl(BRAKING, "reused", "open_reuse"),
    LabelDecl(GANGWAY, "reused", "open_reuse"),
    LabelDecl(BOGIE, "reused", "hidden_reuse", story_case_id="trailer_bogie_identical"),
    LabelDecl(TRACTION, "reused", "hidden_reuse"),
    LabelDecl(AUX, "reused", "hidden_reuse"),
    LabelDecl(LIGHTING, "reused", "hidden_reuse"),
    LabelDecl(PANELS, "reused", "hidden_reuse"),
    LabelDecl(BIKE, "reusable", "near_reuse", story_case_id="bike_module_two_fewer_hooks", reusable_from=("B",)),
    LabelDecl(DOORS, "reusable", "near_reuse", story_case_id="passenger_door_set_reusable", reusable_from=("A", "B", "D", "E")),
    LabelDecl(PIS, "reusable", "near_reuse", reusable_from=("A", "B", "D", "E")),
    LabelDecl(SEATING, "reusable", "ref_reused_content_changed", reusable_from=("A", "B", "D", "E")),
    LabelDecl(ANCHORAGE, "new", "new", story_case_id="floor_wall_anchorage_new"),
    LabelDecl(TOILET, "new", "new"),
)

# --- planted conflicts ---------------------------------------------------------------------
# Outside these, a component has one supplier and one cost everywhere. The cost gaps are blunt
# (at least +15 %): the spec holds no cost tolerance, and the generator must not invent one.

SUPPLIER_OVERRIDES: Final[tuple[SupplierOverride, ...]] = (
    SupplierOverride("BOGIE-DAMPER", "E", SAMBRE),
    SupplierOverride("HVAC-FILTER", "D", ARTOIS),
    SupplierOverride("LIGHT-LED-STRIP", "C", HAINAUT_CABLAGE),
    SupplierOverride("DOOR-SEAL", "B", PORTALYS),
    SupplierOverride("BRK-HOSE-FLEX", "E", ARTOIS),
)

COST_OVERRIDES: Final[tuple[CostOverride, ...]] = (
    CostOverride("SEAT-TABLE", "B", 474.00),
    CostOverride("PANEL-FLOOR-PLY", "C", 455.00),
    CostOverride("COUP-DRAFT-GEAR", "D", 7490.00),
    CostOverride("TRAC-MOTOR", "E", 25950.00),
    CostOverride("LIGHT-DRIVER", "C", 118.00),
)

UNIT_CONFLICTS: Final[tuple[UnitConflict, ...]] = (
    UnitConflict("E", LIGHTING, "LIGHT-CABLE", "2", "pcs"),  # two reels, not 45 m
    UnitConflict("D", TOILET, "WC-SEALANT", "3", "pcs"),  # three cartridges, not 1.5 kg
    UnitConflict("B", GANGWAY, "COUP-JUMPER-CABLE", "4", "pcs"),  # four jumpers, not 9.6 m
)

# --- planted spellings ---------------------------------------------------------------------

#: Spec spellings that must land on one precise line. `SEAT-FIX-KIT-447` is the single
#: out-of-reach spelling allowed in the newest variant: it costs the tool one honest backtest
#: miss caused by resolution, so "Known limits" can carry a figure.
FORCED_SPELLINGS: Final[Mapping[str, tuple[str, str]]] = {
    "SEAT-FIX-KIT-447": ("C", PANELS),
}

TYPO_PLANS: Final[tuple[TypoPlan, ...]] = (
    TypoPlan("LIGHT-LED-STRIP", "homoglyph", places=(("C", LIGHTING),)),
    TypoPlan("LIGHT-DRIVER", "separator", places=(("C", LIGHTING),)),
    TypoPlan("LIGHT-CONNECTOR", "case_and_whitespace", places=(("C", LIGHTING),)),
    TypoPlan("BOGIE-AIRSPRING", "homoglyph"),
    TypoPlan("SHELL-SIDEWALL", "separator"),
    TypoPlan("BRK-CTRL-VALVE", "case_and_whitespace"),
    TypoPlan("DOOR-GUIDE-RAIL", "homoglyph"),
    TypoPlan("TRAC-INSULATOR", "homoglyph"),
    TypoPlan("AUX-FUSE-BOX", "separator"),
    TypoPlan("PANEL-CEILING", "case_and_whitespace"),
    TypoPlan("GANG-HANDRAIL", "homoglyph"),
    TypoPlan("PIS-SPEAKER", "separator"),
    TypoPlan("WC-WASHBASIN", "case_and_whitespace"),
)

# --- notes ---------------------------------------------------------------------------------
# About half of the fact-bearing notes are respected by the BOM: precision needs negatives.
# Only two contradictions reach the newest variant through an obsolete or replaced part —
# BIKE-STRAP and AUX-CAP-BANK — and they are the two planted unsafe reuses.

NOTES: Final[tuple[NoteScript, ...]] = (
    NoteScript("A", "2019-05-06", "fr", text="Contrôle du couple de serrage effectué sur le châssis de bogie, RAS."),
    NoteScript("A", "2019-09-12", "en", fact=FactScript("restriction", "ANCH-FLOOR-PLATE", scope="bike_car")),
    NoteScript("A", "2019-11-04", "fr", fact=FactScript("restriction", "TRAC-TRANSFORMER", scope="bi_mode")),
    NoteScript("A", "2020-02-18", "en", text="Drawing index updated to rev C after the design review. No change to the part list."),
    NoteScript("A", "2021-01-11", "en", fact=FactScript("obsolescence", "WC-GRAB-BAR", effective_date="2021-01-01")),
    NoteScript("A", "2022-01-20", "en", fact=FactScript("obsolescence", "AUX-CAP-BANK", cited_as="aux-cap-bank", effective_date="2022-01-01")),
    NoteScript("A", "2022-04-05", "fr", fact=FactScript("restriction", "SEAT-TABLE", scope="bi_mode")),
    NoteScript("A", "2022-10-03", "mixed", text="Retour atelier : le montage des BGI-2031 est OK, torque values as per the drawing."),
    NoteScript("B", "2021-07-19", "fr", text="Essai de chargement de huit vélos réalisé avec le client, zone conforme."),
    NoteScript("B", "2021-09-30", "mixed", fact=FactScript("restriction", "WC-WASTE-TANK", scope="bike_car")),
    NoteScript("B", "2022-03-14", "mixed", fact=FactScript("replacement", "WC-VACUUM-PUMP", replaced_by="WC-VACUUM-PUMP-G2", effective_date="2022-03-01")),
    NoteScript("B", "2022-06-08", "en", fact=FactScript("restriction", "BIKE-FLOOR-MAT", scope="bi_mode")),
    NoteScript("B", "2023-05-09", "fr", fact=FactScript("replacement", "BIKE-STRAP", cited_as="BIKE STRAP", replaced_by="BIKE-STRAP-V2", effective_date="2023-05-01")),
    NoteScript("B", "2023-08-22", "en", fact=FactScript("restriction", "PIS-SIGN-BIKE", scope="standard_car")),
    NoteScript("B", "2024-01-22", "fr", fact=FactScript("replacement", "ANCH-HOOK-POINT", replaced_by="ANCH-BIKE-PLATE", effective_date="2024-01-15")),
    NoteScript("B", "2024-03-04", "fr", text="Les sangles vélo sont à contrôler visuellement à chaque visite de maintenance."),
    NoteScript("D", "2022-11-15", "fr", fact=FactScript("restriction", "HVAC-REFRIGERANT", scope="bi_mode")),
    NoteScript("D", "2023-01-10", "en", fact=FactScript("replacement", "DOOR-PUSHBUTTON-INT", cited_as="door-pushbutton-int", replaced_by="DOOR-PUSHBUTTON-INT-LED", effective_date="2023-01-01")),
    NoteScript("D", "2023-02-06", "fr", fact=FactScript("replacement", "WC-DOOR-SLIDING", replaced_by="WCU-DOOR-POWERED", effective_date="2023-02-01")),
    NoteScript("D", "2023-03-27", "mixed", fact=FactScript("restriction", "TRAC-FUEL-TANK", scope="electric")),
    NoteScript("D", "2023-07-03", "fr", fact=FactScript("obsolescence", "WC-BOWL-VACUUM", effective_date="2023-06-30")),
    NoteScript("D", "2023-09-18", "en", text="Genset noise measurement done at the depot, within the contractual limits."),
    NoteScript("D", "2024-02-12", "mixed", text="Point fournisseur sur le groupe diesel : delivery schedule confirmed, pas d'impact planning."),
    NoteScript("D", "2026-02-09", "en", fact=FactScript("obsolescence", "TRAC-EXHAUST-KIT", effective_date="2026-02-01")),
    NoteScript("E", "2023-12-04", "mixed", fact=FactScript("obsolescence", "ANCH-SHIM", effective_date="2023-12-01")),
    NoteScript("E", "2024-04-16", "fr", text="Livrée régionale validée par l'autorité organisatrice."),
    NoteScript("E", "2024-09-05", "fr", fact=FactScript("replacement", "WC-WATER-TANK", replaced_by="WCU-TANK-COMBO", effective_date="2024-09-01")),
    NoteScript("E", "2024-11-25", "en", text="Seat pitch checked against the regional specification: compliant."),
    NoteScript("E", "2025-01-13", "fr", text="Mise à jour de la nomenclature après revue de conception, sans changement de pièce."),
    NoteScript("E", "2026-01-12", "fr", fact=FactScript("replacement", "HVAC-FILTER", cited_as="HVAC_FILTER", replaced_by="HVAC-FILTER-F9", effective_date="2026-01-01")),
    NoteScript("E", "2026-03-09", "fr", fact=FactScript("obsolescence", "BRK-PARKING-ACT", effective_date="2026-03-01")),
    NoteScript("C", "2025-03-03", "fr", text="Première revue de conception avec la région : six emplacements vélos confirmés."),
    NoteScript("C", "2025-06-10", "mixed", fact=FactScript("replacement", "HVAC-CTRL-BOARD", replaced_by="HVAC-CTRL-BOARD-R2", effective_date="2025-06-01")),
    NoteScript("C", "2025-07-07", "mixed", text="Toilettes universelles PMR : mock-up review done with the accessibility panel, RAS."),
    NoteScript("C", "2025-09-08", "en", fact=FactScript("replacement", "PIS-SIGN-STD", replaced_by="PIS-SIGN-STD-V2", effective_date="2025-09-01")),
    NoteScript("C", "2025-12-08", "fr", fact=FactScript("replacement", "SEAT-TIPUP", replaced_by="SEAT-TIPUP-SOFT", effective_date="2025-12-01")),
    NoteScript("C", "2026-03-16", "en", fact=FactScript("replacement", "TRAC-TRANSFORMER", replaced_by="TRAC-TRANSFORMER-LW", effective_date="2026-03-01")),
    NoteScript("C", "2026-04-13", "en", fact=FactScript("replacement", "LIGHT-EMERG-UNIT", cited_as="light-emerg-unit", replaced_by="LIGHT-EMERG-UNIT-LI", effective_date="2026-04-01")),
    NoteScript("C", "2026-06-08", "en", fact=FactScript("obsolescence", "COUP-ELEC-HEAD", effective_date="2026-06-01")),
    NoteScript("C", "2026-09-07", "fr", fact=FactScript("obsolescence", "SEAT-END-PANEL", effective_date="2026-09-01")),
)

# --- wording -------------------------------------------------------------------------------
# Placeholders: {ref} the cited spelling, {new} the replacing part, {date_iso} / {date_fr} the
# effective date, {scope_en} / {scope_fr} the restricted configuration.

SCOPE_WORDING: Final[Mapping[str, tuple[str, str]]] = {
    "bike_car": ("bike cars", "voitures vélos"),
    "bi_mode": ("bi-mode units", "rames bi-mode"),
    "standard_car": ("standard cars", "voitures standard"),
    "electric": ("electric-only units", "rames électriques"),
}

NOTE_TEMPLATES: Final[Mapping[tuple[str, str], tuple[str, ...]]] = {
    ("replacement", "fr"): (
        "{ref} remplacé par {new} à compter du {date_fr}.",
        "À partir du {date_fr}, monter {new} à la place de {ref}.",
        "Évolution nomenclature : {ref} est remplacé par {new} (applicable au {date_fr}).",
    ),
    ("replacement", "en"): (
        "{ref} replaced by {new} as of {date_iso}.",
        "From {date_iso} on, fit {new} instead of {ref}.",
        "Engineering change: {ref} is superseded by {new}, effective {date_iso}.",
    ),
    ("replacement", "mixed"): (
        "Suite à la revue fournisseur : {ref} replaced by {new}, applicable au {date_fr}.",
        "ECR closed. {ref} remplacé par {new} from {date_iso}.",
    ),
    ("obsolescence", "fr"): (
        "{ref} obsolète depuis le {date_fr}, ne plus approvisionner.",
        "Fin de vie fournisseur : {ref} est obsolète à compter du {date_fr}.",
        "Pièce {ref} déclarée obsolète au {date_fr}.",
    ),
    ("obsolescence", "en"): (
        "{ref} obsolete since {date_iso}, do not order.",
        "Supplier end of life: {ref} is obsolete as of {date_iso}.",
        "Part {ref} declared obsolete, effective {date_iso}.",
    ),
    ("obsolescence", "mixed"): (
        "Info fournisseur : {ref} obsolete since {date_iso}, stock restant à écouler.",
    ),
    ("restriction", "fr"): (
        "{ref} : ne pas utiliser sur {scope_fr}.",
        "Ne pas monter {ref} sur {scope_fr}.",
        "Restriction d'emploi : {ref} interdit sur {scope_fr}.",
    ),
    ("restriction", "en"): (
        "{ref}: do not use on {scope_en}.",
        "Do not fit {ref} on {scope_en}.",
        "Usage restriction: {ref} is not approved for {scope_en}.",
    ),
    ("restriction", "mixed"): (
        "Attention montage : {ref} do not use on {scope_en}, voir avis technique.",
        "Safety review outcome — {ref} : ne pas utiliser sur {scope_fr}.",
    ),
}

# --- reading the catalogue -----------------------------------------------------------------


class CatalogueError(ValueError):
    """The catalogue contradicts itself or the spec."""


def contents(spec: DatasetSpec) -> dict[tuple[str, str], dict[str, float]]:
    """`(variant, sub-assembly name) -> {clean reference: true quantity}`, every source resolved."""
    definitions = {(d.variant_id, d.name): d for d in SUB_ASSEMBLIES}
    resolved: dict[tuple[str, str], dict[str, float]] = {}

    def resolve(key: tuple[str, str], trail: tuple[tuple[str, str], ...] = ()) -> dict[str, float]:
        if key in resolved:
            return resolved[key]
        if key in trail:
            raise CatalogueError(f"sub-assembly {key} is defined in terms of itself")
        if key not in definitions:
            raise CatalogueError(f"sub-assembly {key} is referred to but never defined")
        content = definitions[key].content
        if isinstance(content, FromStory):
            case = spec.story_case(content.case_id)
            counts = dict(case.left if content.side == "left" else case.right)
        elif isinstance(content, Own):
            counts = {reference: float(quantity) for reference, quantity in content.counts.items()}
        elif isinstance(content, SameAs):
            counts = dict(resolve((content.variant_id, content.name), (*trail, key)))
        else:
            counts = dict(resolve((content.variant_id, content.name), (*trail, key)))
            for reference in content.remove:
                if reference not in counts:
                    raise CatalogueError(f"{key} removes {reference!r}, which its source does not contain")
                del counts[reference]
            for reference, quantity in content.set_quantities.items():
                if reference not in counts:
                    raise CatalogueError(f"{key} sets the quantity of {reference!r}, which its source does not contain")
                counts[reference] = float(quantity)
            for reference, quantity in content.add.items():
                if reference in counts:
                    raise CatalogueError(f"{key} adds {reference!r}, which its source already contains")
                counts[reference] = float(quantity)
        resolved[key] = counts
        return counts

    for definition in SUB_ASSEMBLIES:
        resolve((definition.variant_id, definition.name))
    return resolved
