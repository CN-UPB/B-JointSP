class Template:
    def __init__(self, name, components, arcs):
        self.name = name
        self.components = components
        self.arcs = arcs

    def __str__(self):
        return self.name

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return NotImplemented

    def __ne__(self, other):
        if isinstance(other, self.__class__):
            return not self.__eq__(other)
        return NotImplemented

    def __hash__(self):
        # all templates need unique names
        return hash(self.name)

    def print(self):
        print("Template " + self.name + ":")

        string = "  Components: "
        for component in self.components:
            string += str(component) + ", "
        print(string)

        string = "  Arcs: "
        for arc in self.arcs:
            string += str(arc) + ", "
        print(string)

    # return source component (assuming there is only one)
    def source(self):
        for component in self.components:
            if component.source:
                return component
        return None

    # weight = expected resource consumption based on total source data rate and components
    def weight(self, src_dr):
        # outgoing data rate of specified component in specified direction and from specified output
        out_dr = {}

        # iterate over components in topological order, determine outgoing dr for each and store it in out_dr
        # first, consider only forward direction then only backward
        # also determine cpu/mem consumption per component and direction and increase total_cpu/mem accordingly
        total_cpu, total_mem = 0, 0
        topo_order = self.topological_component_order()
        direction = "forward"
        end_reached = False
        for j in topo_order:
            
            if j.end:
                end_reached = True
            # switch direction to backward after last end component
            if end_reached and not j.end:
                direction = "backward"
            # source component: specified outgoing data rate, no resource consumption
            if j.source:
                if direction == "forward":
                    out_dr[(j, direction, 0)] = src_dr

                continue


            # forward direction refers to the ingoing data rates and includes end components
            if direction == "forward":
                # ingoing data rates in forward direction
                in_dr_fwd = []
                for k_in in range(j.inputs):
                    # get ingoing arc at k_in
                    in_arcs = [a for a in self.arcs if a.dest == j and a.dest_in == k_in and a.direction == "forward"]
                    # if the component is adapted on the fly, k_in might belong to another template => set dr to 0
                    if len(in_arcs) == 0:
                        in_dr_fwd.append(0)
                    elif len(in_arcs) == 1:
                        in_arc = in_arcs[0]
                        in_dr_fwd.append(out_dr[(in_arc.source, "forward", in_arc.src_out)])
                    else:
                        raise ValueError("{} ingoing arcs at input {} of {}".format(len(in_arcs), k_in, j))

                # set ingoing data rates backward direction to 0
                in_dr_bwd = [0] * j.inputs_back

                # resource consumption
                cpu = j.cpu_req(in_dr_fwd + in_dr_bwd)
                mem = j.mem_req(in_dr_fwd + in_dr_bwd)
                
                
                total_cpu += cpu
                total_mem += mem


               

                # compute outgoing data rates and store them in the dictionary (end components only have bwd outputs)
                if j.end:
                    out_drs = [j.outgoing_back(in_dr_fwd, k_out) for k_out in range(j.outputs_back)]
                    for k_out in range(j.outputs_back):
                        out_dr[(j, "backward", k_out)] = out_drs[k_out]
                else:
                    out_drs = [j.outgoing(in_dr_fwd, k_out) for k_out in range(j.outputs)]
                    for k_out in range(j.outputs):
                        out_dr[(j, "forward", k_out)] = out_drs[k_out]
            

            if direction == "backward":
                # set ingoing data rates in forward direction to 0
                in_dr_fwd = [0] * j.inputs

                # ingoing data rates in backward direction
                in_dr_bwd = []
                for k_in in range(j.inputs_back):
                    # get ingoing arc at k_in
                    in_arcs = [a for a in self.arcs if a.dest == j and a.dest_in == k_in and a.direction == "backward"]
                    # if the component is adapted on the fly, k_in might belong to another template => set dr to 0
                    if len(in_arcs) == 0:
                        in_dr_bwd.append(0)
                    elif len(in_arcs) == 1:
                        in_arc = in_arcs[0]
                        in_dr_bwd.append(out_dr[(in_arc.source, "backward", in_arc.src_out)])
                    else:
                        raise ValueError("{} ingoing arcs at input {} of {}".format(len(in_arcs), k_in, j))

                # resource consumption
                cpu = j.cpu_req(in_dr_fwd + in_dr_bwd)
                mem = j.mem_req(in_dr_fwd + in_dr_bwd)
                total_cpu += cpu
                total_mem += mem
               

                # compute outgoing data rates and store them in the dictionary
                out_drs = [j.outgoing_back(in_dr_bwd, k_out) for k_out in range(j.outputs_back)]
                for k_out in range(j.outputs_back):
                    out_dr[(j, "backward", k_out)] = out_drs[k_out]

        total_dr = sum(out_dr.values())
        print("{}'s weight: {}\n".format(self, total_cpu+total_mem+total_dr))
        
        
        return total_cpu + total_mem + total_dr

    # start with source component and continue breadth-first style (first forward then backward direction)
    # FUTURE WORK: set as property/constant such that it only has to be computed once (eg, in init)
    def topological_component_order(self):
        # fwd_/bwd_order stores all ordered components (for each direction)
        # curr_level stores the components of the current level/depth of the VNF-FG
        fwd_order, bwd_order, curr_level = [], [], []

        # start with source component
        curr_level.append(self.source())
        fwd_order.append(self.source())

        # add remaining components by following the arcs of the components at the current level (forward)
        while len(curr_level) > 0:
            next_level = []
            for j in curr_level:
                fwd_arcs_out = [a for a in self.arcs if a.source == j and a.direction == "forward"]
                for a in fwd_arcs_out:
                    next_level.append(a.dest)
                    fwd_order.append(a.dest)
            curr_level = next_level

        # start backward direction with end components
        curr_level = [j for j in fwd_order if j.end]
        fwd_order += curr_level

        # return in backward direction from end components
        while len(curr_level) > 0:
            next_level = []
            for j in curr_level:
                bwd_arcs_out = [a for a in self.arcs if a.source == j and a.direction == "backward"]
                for a in bwd_arcs_out:
                    next_level.append(a.dest)
                    bwd_order.append(a.dest)
            curr_level = next_level

        # remove possible duplicates within a direction
        # always keeping the last one of each element to ensure that the order is correct
        seen = set()
        seen_add = seen.add
        fwd_order = [j for j in fwd_order[::-1] if not (j in seen or seen_add(j))][::-1]
        seen = set()
        seen_add = seen.add
        bwd_order = [j for j in bwd_order[::-1] if not (j in seen or seen_add(j))][::-1]

        return fwd_order + bwd_order
