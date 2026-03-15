"""
Shared workout analysis constants.
"""

WEEKLY_SET_TARGETS = {
    'chest': (10, 20),
    'shoulders': (16, 22),
    'biceps': (14, 20),
    'triceps': (10, 14),
    'forearms': (10, 14),
    'lats': (10, 20),
    'traps': (12, 20),
    'lower_back': (6, 10),
    'quads': (12, 20),
    'hamstrings': (10, 16),
    'glutes': (4, 12),
    'calves': (8, 16),
    'abs': (16, 20),
    'obliques': (0, 16),
    'abductors': (0, 16),
    'adductors': (0, 16),
}

PRIMARY_RECOVERY_SKIP = 70.0
SECONDARY_RECOVERY_SWAP = 80.0
READY_TO_TRAIN_RECOVERY = 85.0
ACTIVE_SESSION_SET_CAP = 4

PERFORMANCE_REGRESSION_PCT = -5.0
PERFORMANCE_IMPROVEMENT_PCT = 3.0
PERFORMANCE_STAGNATION_BAND_PCT = 1.0

LOW_RIR_WARNING = 1.0
REP_DROP_WARNING_PCT = 25.0

COMPOUND_MIN_REST_SECONDS = 90
ISOLATION_MIN_REST_SECONDS = 45

CNS_BACKOFF_THRESHOLD = 70.0
CNS_PUSH_THRESHOLD = 85.0

TOO_LITTLE_FREQUENCY_DAYS = 7

NO_PROGRAM_MUSCLE_PRIORITY = [
    'chest',
    'lats',
    'quads',
    'hamstrings',
    'shoulders',
    'glutes',
    'biceps',
    'triceps',
    'calves',
    'abs',
    'traps',
    'forearms',
    'lower_back',
    'obliques',
    'abductors',
    'adductors',
]
