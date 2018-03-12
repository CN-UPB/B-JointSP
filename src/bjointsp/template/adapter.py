# module for adapting templates on the fly if components are reused


# check that all reused components are defined consistently -> else: exception
def check_consistency(components):
    for j1 in components:
        for j2 in components:		# compare all components
            if j1 == j2 and j1.__dict__ != j2.__dict__:		# same name and reuseID but different other attributes
                raise ValueError("Inconsistent definition of reused component {}.".format(j1))


# check and return number of reuses
def reuses(component, arcs):
    # count number of reuses for each port
    times = set()  # set => no duplicates
    for k in range(component.inputs):
        times.add(len([a for a in arcs if a.ends_in("forward", k, component)]))
    for k in range(component.outputs):
        times.add(len([a for a in arcs if a.starts_at("forward", k, component)]))
    for k in range(component.inputs_back):
        times.add(len([a for a in arcs if a.ends_in("backward", k, component)]))
    for k in range(component.outputs_back):
        times.add(len([a for a in arcs if a.starts_at("backward", k, component)]))

    # check if each port was reused the same number of times (requirement/assumption)
    if len(times) != 1:
        raise ValueError("Not all ports of {} are (re-)used the same number of times (required).".format(component))

    return times.pop()


# return adapted templates with adapted reused components and exactly one arc per port (allows proportional output)
def adapt_for_reuse(templates):
    # create set of components and arcs
    arcs = []
    for t in templates:
        arcs += t.arcs

    # find reused components and adapt them
    component_reuses = {}					# dictionary with components-#reuses
    reused_components = []					# list of all reused components (contains duplicates) for consistency check
    for t in templates:
        for j in t.components:
            uses = reuses(j, arcs)
            if uses > 1:           			# used by >1 => reuse
                if j.source:
                    raise ValueError("Source component {} cannot be reused".format(j))
                j.adapt(uses)				# add ports and functions on the fly
                component_reuses[j] = uses
                reused_components.append(j)
    check_consistency(reused_components) 	# check consistent def of reused components

    # adjust arcs to use new ports
    for j in component_reuses:
        uses = component_reuses[j]
        port_offset = 0
        for t in templates:
            # adjust/shift ingoing arcs by offset to correct port
            arc_shifted = False
            for a in t.arcs:
                if a.dest == j:
                    a.dest_in += port_offset
                    arc_shifted = True
                if a.source == j:
                    a.src_out += port_offset
                    arc_shifted = True

            # increase the offset for the next template if an arc was shifted
            if arc_shifted:
                if port_offset >= uses:		# arc was shifted too often: something went wrong
                    raise ValueError("Port offset {} too high. Should be < {} (#reuses).".format(port_offset, uses))
                port_offset += 1

    return templates
