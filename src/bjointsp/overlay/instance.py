import math
from collections import defaultdict


class Instance:
    def __init__(self, component, location, src_flows=None, fixed=False):
        if (component.source and src_flows is None) or (not component.source and src_flows is not None):
            raise ValueError("src_flows has to be set for source components and source components only")
        self.component = component
        self.location = location
        self.src_flows = src_flows
        if src_flows is not None:
            for f in src_flows:
                f.passed_stateful[component] = self
        self.fixed = fixed
        # edges can be accessed in the dictionary with the other instance as key
        self.edges_in = {}
        self.edges_out = {}

    def __str__(self):
        if self.src_flows is not None:
            return "({},{}):{}".format(self.component, self.location, self.src_flows)
        return "({},{})".format(self.component, self.location)

    def __repr__(self):
        if self.src_flows is not None:
            return "({},{}):{}".format(self.component, self.location, self.src_flows)
        return "({},{})".format(self.component, self.location)

    # instance defined by component and location (only one per comp and loc)
    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.component == other.component and self.location == other.location
        return NotImplemented

    def __ne__(self, other):
        if isinstance(other, self.__class__):
            return not self.__eq__(other)
        return NotImplemented

    def __hash__(self):
        return hash((self.component, self.location))

    # return cpu consumption based on all ingoing edges
    # ignore the idle consumption if instances of component specified in ignore_idle
    def consumed_cpu(self, ignore_idle=None):
        return self.component.cpu_req(self.input_dr(), ignore_idle)

    # return mem consumption based on all ingoing edges
    # ignore the idle consumption if instances of component specified in ignore_idle
    def consumed_mem(self, ignore_idle=None):
        return self.component.mem_req(self.input_dr(), ignore_idle)

    # return the ingoing data rate of each input as vector/list based on all ingoing edges (and the flows mapped to them)
    def input_dr(self):
        in_dr = []
        for k in range(self.component.inputs):
            # get all ingoing edges at input k and append their summed up data rate
            in_edges = [e for e in self.edges_in.values() if e.direction == "forward" and e.arc.dest_in == k]
            in_dr.append(sum(e.flow_dr() for e in in_edges))
        for k in range(self.component.inputs_back):
            # get all ingoing edges at input k and append their summed up data rate
            in_edges = [e for e in self.edges_in.values() if e.direction == "backward" and e.arc.dest_in == k]
            in_dr.append(sum(e.flow_dr() for e in in_edges))
        return in_dr

    # if this instance is stateful and traversed in fwd dir, update passed_stateful of all ingoing flows
    # in bwd dir the same instance is traversed and passed_stateful doesn't need any update
    def update_passed_stateful(self, direction):
        if self.component.stateful and direction == "forward":
            flows = [f for e in self.edges_in.values() if e.direction == direction for f in e.flows]
            for f in flows:
                f.passed_stateful[self.component] = self

    # return dict with the flows and their dr that should leave each output of the instance in the specified direction
    # based on the ingoing edges, the flows mapped to these edges, and the dr-functions of each output
    # dict of dicts => output: flow: flow_dr; (a flow might leave multiple outputs with different drs)
    def out_flows(self, direction):
        # update passed_stateful of all ingoing flows in current direction
        self.update_passed_stateful(direction)

        out_flow_dr = {}
        if direction == "forward":
            # init dict
            for k_out in range(self.component.outputs):
                # use default dr=0 and increment to handle a single flow being mapped to multiple ingoing edges
                out_flow_dr[k_out] = defaultdict(int)

            if self.component.source:
                out_flow_dr[0] = {f: f.src_dr for f in self.src_flows}
                return out_flow_dr
            elif self.component.end:
                return {}
            else:
                # calculate for each flow its outgoing data rate at each output
                in_edges = [e for e in self.edges_in.values() if e.direction == "forward"]
                for e in in_edges:
                    for f in e.flows:
                        # vector of ingoing drs for this individual flow f
                        in_dr = [f.dr[e] if i == e.arc.dest_in else 0 for i in range(self.component.inputs)]
                        # corresponding vector of outgoing drs for f
                        out_dr = [self.component.outgoing(in_dr, k_out) for k_out in range(self.component.outputs)]
                        # store result in the dictionary
                        for k_out in range(self.component.outputs):
                            if out_dr[k_out] > 0:
                                out_flow_dr[k_out][f] += out_dr[k_out]
                return out_flow_dr

        if direction == "backward":
            # init dict
            for k_out in range(self.component.outputs_back):
                # use default dr=0 and increment to handle a single flow being mapped to multiple ingoing edges
                out_flow_dr[k_out] = defaultdict(int)

            if self.component.source:
                return {}
            elif self.component.end:
                # for end instances consider ingoing flows in fwd and outgoing in bwd direction
                in_edges = [e for e in self.edges_in.values() if e.direction == "forward"]
                for e in in_edges:
                    for f in e.flows:
                        # vector of ingoing drs for this individual flow f
                        in_dr = [f.dr[e] if i == e.arc.dest_in else 0 for i in range(self.component.inputs)]
                        # corresponding vector of outgoing drs for f
                        out_dr = [self.component.outgoing_back(in_dr, k_out) for k_out in range(self.component.outputs_back)]
                        # store result in the dictionary
                        for k_out in range(self.component.outputs_back):
                            if out_dr[k_out] > 0:
                                out_flow_dr[k_out][f] += out_dr[k_out]
                return out_flow_dr
            else:
                # now consider ingoing and outgoing flows in backward direction
                in_edges = [e for e in self.edges_in.values() if e.direction == "backward"]
                for e in in_edges:
                    for f in e.flows:
                        # vector of ingoing drs for this individual flow f
                        in_dr = [f.dr[e] if i == e.arc.dest_in else 0 for i in range(self.component.inputs_back)]
                        # corresponding vector of outgoing drs for f
                        out_dr = [self.component.outgoing_back(in_dr, k_out) for k_out in range(self.component.outputs_back)]
                        # store result in the dictionary
                        for k_out in range(self.component.outputs_back):
                            if out_dr[k_out] > 0:
                                out_flow_dr[k_out][f] += out_dr[k_out]
                return out_flow_dr
        else:
            raise ValueError("Direction {} invalid. Only forward or backward allowed.".format(direction))

    # return whether the instance is used, ie, has ingoing edges with flows (with dr>0) mapped to them
    def used(self, direction, overlay):
        # source instances are always used
        if self.src_flows is not None:
            return True
        # end instances need ingoing edges in forward direction
        if self.component.end:
            direction = "forward"
        # check dr of all flows along all corresponding edges
        edges = [e for e in self.edges_in.values() if e in overlay.edges and e.direction == direction]
        for e in edges:
            if e.flow_dr() > 0:
                return True
        return False
