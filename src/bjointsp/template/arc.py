class Arc:
    def __init__(self, direction, source, src_out, dest, dest_in, max_delay):
        self.direction = direction
        self.source = source
        self.src_out = src_out
        self.dest = dest
        self.dest_in = dest_in
        self.max_delay = max_delay

    def __str__(self):
        if self.direction == "forward":
            return str(self.source) + "." + str(self.src_out) + "->" + str(self.dest) + "." + str(self.dest_in)
        if self.direction == "backward":
            return str(self.dest) + "." + str(self.dest_in) + "<-" + str(self.source) + "." + str(self.src_out)

    def __repr__(self):
        if self.direction == "forward":
            return str(self.source) + "." + str(self.src_out) + "->" + str(self.dest) + "." + str(self.dest_in)
        if self.direction == "backward":
            return str(self.dest) + "." + str(self.dest_in) + "<-" + str(self.source) + "." + str(self.src_out)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return NotImplemented

    def __ne__(self, other):
        if isinstance(other, self.__class__):
            return not self.__eq__(other)
        return NotImplemented

    def __hash__(self):
        return hash(tuple(sorted(self.__dict__.items())))

    # whether arc with the specified direction ends in port of component
    def ends_in(self, direction, port, component):
        return self.direction == direction and (port == self.dest_in) and (component == self.dest)

    # whether arc with the specified directions starts at port of component
    def starts_at(self, direction, port, component):
        return self.direction == direction and (port == self.src_out) and (component == self.source)
