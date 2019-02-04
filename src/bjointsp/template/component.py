class Component:
    def __init__(self, name, type, stateful, inputs, outputs, cpu, mem, dr, vnf_delay=0, config=None):
        self.name = name
        if type == "source":
            self.source = True
            self.end = False
        elif type == "normal":
            self.source = False
            self.end = False
        elif type == "end":
            self.source = False
            self.end = True
        else:
            raise ValueError("Invalid type: " + type)
        self.stateful = stateful
        self.inputs = inputs[0]
        self.inputs_back = inputs[1]
        self.outputs = outputs[0]
        self.outputs_back = outputs[1]
        self.cpu = cpu      # function of forward and backward ingoing data rates
        self.mem = mem
        self.vnf_delay = vnf_delay
        self.dr = dr[0]
        self.dr_back = dr[1]
        self.config = config		# config used by external apps/MANOs (describes image, ports, ...)

        total_inputs = self.inputs + self.inputs_back

        if len(self.cpu) != total_inputs + 1: # always need idle consumption (can be 0)
            raise ValueError("Inputs and CPU function mismatch or missing idle consumption")
        if len(self.mem) != total_inputs + 1:
            raise ValueError("Inputs and memory function mismatch or missing idle consumption")

        if not self.source and len(self.dr) != self.outputs:
            raise ValueError("Outputs and #outgoing data rate functions mismatch (forward direction)")
        if len(self.dr_back) != self.outputs_back:
            raise ValueError("Outputs and #outgoing data rate functions mismatch (backward direction)")

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.name

    # equal iff same name (name includes reuseID, e.g., A1)
    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.name == other.name
        return NotImplemented

    def __ne__(self, other):
        if isinstance(other, self.__class__):
            return not self.__eq__(other)
        return NotImplemented

    def __hash__(self):
        return hash((self.name))

    def print(self):
        if self.source:
            type = "Source component"
        elif self.end:
            type = "End component"
        else:
            type = "Component"
        if self.stateful:
            type += " (stateful)"
        print("{} {} with CPU: {}, mem: {}".format(type, self, self.cpu, self.mem))
        print("\tforward: {} in, {} out, data rate: {}".format(self.inputs, self.outputs, self.dr))
        print("\tbackward: {} in, {} out, data rate: {}".format(self.inputs_back, self.outputs_back, self.dr_back))

    # CPU requirement based on the incoming data rates and the specified function
    # ignore idle consumption if component specified in ignore_idle
    def cpu_req(self, incoming, ignore_idle=None):
        inputs = self.inputs + self.inputs_back
        if len(incoming) != inputs:
            raise ValueError("Mismatch of #incoming data rates and inputs")

        requirement = self.cpu[-1]      # idle consumption
        if self == ignore_idle:
            requirement = 0
        for i in range(inputs):
            requirement += self.cpu[i] * incoming[i]    # linear function

        return requirement

    # memory requirement based on the incoming data rates and the specified function
    # ignore idle consumption if component specified in ignore_idle
    def mem_req(self, incoming, ignore_idle=None):
        inputs = self.inputs + self.inputs_back
        if len(incoming) != inputs:
            raise ValueError("Mismatch of #incoming data rates and inputs")

        requirement = self.mem[-1]  # idle consumption
        if self == ignore_idle:
            requirement = 0
        for i in range(inputs):
            requirement += self.mem[i] * incoming[i]    # linear function

        return requirement

    # outgoing data rate at specified output based on the incoming data rates
    def outgoing(self, in_vector, output):
        if output >= self.outputs:
            raise ValueError("output %d not one of the component's %d output(s)" % (output, self.outputs))

        function = self.dr[output]       # get function for current output
        out_dr = function[-1]            # idle data rate
        for i in range(self.inputs):
            out_dr += function[i] * in_vector[i]  # linear function

        return out_dr

    def outgoing_back(self, in_vector, output):
        if output >= self.outputs_back:
            raise ValueError("output %d not one of the component's %d output(s) on way back" % (output, self.outputs))

        function = self.dr_back[output]         # get function for current output
        out_dr = function[-1]                   # idle data rate
        for i in range(len(in_vector)):         # at end-component: input comes from forward direction => not range(self.inputs_back)
            out_dr += function[i] * in_vector[i]  # linear function

        return out_dr

    # adapt component on the fly: split and duplicate ports and functions for reuse
    # assumption: all ports are reused the same number of times
    def adapt(self, reuses):
        if reuses < 2:  # < 2 uses => only used by one template => no reuse => no extension required
            print("{} doesn't need extension. It's only used by {} template.".format(self, reuses))
            return

        # update resource consumption functions
        inputs = self.inputs + self.inputs_back
        new_cpu = []
        new_mem = []
        for k in range(inputs):
            for i in range(reuses):
                new_cpu.append(self.cpu[k]) # duplicate coefficient of input k reuses-times
                new_mem.append(self.mem[k])
        new_cpu.append(self.cpu[-1])        # append idle consumption
        new_mem.append(self.mem[-1])
        self.cpu = new_cpu                  # update functions
        self.mem = new_mem

        # update outgoing data rates in forward direction
        new_outgoing = []
        for old_out in range(self.outputs):
            for new_out in range(reuses):           # reuses-many new outputs for each original output
                curr_out = (old_out * reuses) + new_out    # number of current output
                new_outgoing.append([])             # new empty data rate for each new output

                # adjust/add coefficients to match the new inputs, eg., [1,0] -> [1,0,0], [0,1,0] (1 in, 2 reuses)
                # split each old input coefficient into reuses-many new coefficient for the new inputs
                for old_in in range(self.inputs):
                    for new_in in range(reuses):    # add reuses-many new coefficients for each old input-coefficient
                        if new_out == new_in:       # connect i-th new input and output with each other
                            new_outgoing[curr_out].append(self.dr[old_out][old_in])
                        else:                       # not the others
                            new_outgoing[curr_out].append(0)

                new_outgoing[curr_out].append(self.dr[old_out][-1])     # append idle data rate
        self.dr = new_outgoing                      # update data rate

        # same for backward direction
        new_outgoing = []
        for old_out in range(self.outputs_back):
            for new_out in range(reuses):           # reuses-many new outputs for each original output
                curr_out = (old_out * reuses) + new_out  # number of current output
                new_outgoing.append([])             # new empty data rate for each new output

                # adjust/add coefficients to match the new inputs, eg., [1,0] -> [1,0,0], [0,1,0] (1 in, 2 reuses)
                # split each old input coefficient into reuses-many new coefficient for the new inputs
                for old_in in range(self.inputs_back):
                    for new_in in range(reuses):    # add reuses-many new coefficients for each old input-coefficient
                        if new_out == new_in:       # connect i-th new input and output with each other
                            new_outgoing[curr_out].append(self.dr_back[old_out][old_in])
                        else:                       # not the others
                            new_outgoing[curr_out].append(0)

                new_outgoing[curr_out].append(self.dr_back[old_out][-1])  # append idle data rate
        self.dr_back = new_outgoing                 # update data rate

        # duplicate ports (each port split into reuses-many new ports)
        self.inputs *= reuses
        self.outputs *= reuses
        self.inputs_back *= reuses
        self.outputs_back *= reuses