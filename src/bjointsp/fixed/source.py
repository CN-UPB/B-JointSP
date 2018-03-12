class Source:
    def __init__(self, location, component, flows):
        self.location = location
        self.component = component
        self.flows = flows    # list of flows, each with ID and data rate

    def __str__(self):
        flow_str = ""
        for f in self.flows:
            flow_str += str(f)
        return "({}, {}, {})".format(self.location, self.component, flow_str)

    # return sum of dr of all flows leaving the source
    def total_flow_dr(self):
        return sum(f.src_dr for f in self.flows)
