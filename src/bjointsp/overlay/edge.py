class Edge:
    def __init__(self, arc, source, dest):
        self.arc = arc
        self.source = source
        self.dest = dest
        self.direction = arc.direction
        # initialize without path (adjusted later); FUTURE WORK: multiple paths per edge
        self.paths = []		# list of paths(=list of nodes); initially path-dr equally split among all paths
        self.flows = []		# list of flows passing the edge

        # automatically add edge to source and dest instance
        self.source.edges_out[dest] = self
        self.dest.edges_in[source] = self

    def __str__(self):
        if self.direction == "forward":
            return "{}->{}:{}".format(self.source, self.dest, self.flows)
        else:
            return "{}<-{}:{}".format(self.dest, self.source, self.flows)

    def __repr__(self):
        if self.direction == "forward":
            return "{}->{}:{}".format(self.source, self.dest, self.flows)
        else:
            return "{}<-{}:{}".format(self.dest, self.source, self.flows)

    # source and dest identify any edge (there can be at most 1 edge between any source and dest)
    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.source == other.source and self.dest == other.dest
        return NotImplemented

    def __ne__(self, other):
        if isinstance(other, self.__class__):
            return not self.__eq__(other)
        return NotImplemented

    def __hash__(self):
        return hash((self.source, self.dest))

    def print(self):
        print("Edge from {} to {} ({}) with flows {}".format(self.source, self.dest, self.direction, self.flows))
        for path in self.paths:
            print("\tNodes on path: ", *path, sep=" ")

    # total data rate along the edge of all current flows
    def flow_dr(self):
        return sum(f.dr[self] for f in self.flows)
