# unsplittable flow with a unique ID and an initial data rate (when leaving the source)
class Flow:
    def __init__(self, flow_id, src_dr):
        self.id = flow_id
        self.src_dr = src_dr
        self.dr = {}					# the flow's dr along a specific edge (edge: dr)
        self.passed_stateful = {}		# stateful instances passed by the flow (component: instance)

    def __str__(self):
        return self.id

    def __repr__(self):
        return self.id

    # flow defined by ID only => assume to be unique
    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.id == other.id
        return NotImplemented

    def __ne__(self, other):
        if isinstance(other, self.__class__):
            return not self.__eq__(other)
        return NotImplemented

    def __hash__(self):
        return hash((self.id))

    def full_str(self):
        return "({}, {})".format(self.id, self.src_dr)
