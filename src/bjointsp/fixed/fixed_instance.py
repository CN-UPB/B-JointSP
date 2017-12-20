# instance with fixed location, e.g., of a legacy network function
class FixedInstance:
    def __init__(self, location, component):
        self.location = location
        self.component = component

    def __str__(self):
        return "({}, {})".format(self.location, self.component)