# the different objectives are assigned to constants to use in other modules

COMBINED = 0
OVER_SUB = 1
CHANGED = 2
RESOURCES = 3
DELAY = 4


# return constant corresponding to the string-input
def get_objective(obj_arg):
    if obj_arg == "combined":
        return COMBINED
    elif obj_arg == "over-sub":
        return OVER_SUB
    elif obj_arg == "changed":
        return CHANGED
    elif obj_arg == "resources":
        return RESOURCES
    elif obj_arg == "delay":
        return DELAY
    else:
        raise ValueError("Objective {} unknown".format(obj_arg))
