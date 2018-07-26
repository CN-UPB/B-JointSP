# embedding procedure
import math
import logging
import random
from collections import OrderedDict			# for deterministic behavior
from bjointsp.overlay.edge import Edge
from bjointsp.overlay.instance import Instance
from bjointsp.overlay.overlay import Overlay

# global variables for easy access by all functions
nodes, links, shortest_paths, overlays = None, None, None, None


# return the outgoing arc of the specified component at the specified output in the specified direction
def out_arc(template, component, output, direction):
    out_arcs = [a for a in template.arcs if a.starts_at(direction, output, component)]
    # there has to be exactly one arc per input and output; but the arc might belong to another template
    if len(out_arcs) == 1:
        return out_arcs[0]
    elif len(out_arcs) == 0:
        return None
    else:
        raise ValueError("#outgoing arcs of {} at {} output {} is {}. It should be at most 1 per output and template."
                        .format(component, direction, output, len(out_arcs)))


# remove the specified instance and its in- and outgoing edges from all overlays/specified overlay
# if the instance is stateful, also remove it from passed_stateful of all flows
def remove_instance(instance, overlay=None):
    # if an overlay is specified, only remove from that overlay; else from all
    if overlay is not None:
        overlays_to_update = [overlay]
    else:
        overlays_to_update = overlays.values()

    # remove instance and associated edges from overlays_to_update and update flows
    for ol in overlays_to_update:
        flows_to_update = [f for e in ol.edges for f in e.flows if instance in f.passed_stateful.values()]
        for f in flows_to_update:
            f.passed_stateful = {k:v for k, v in f.passed_stateful.items() if v != instance}

        if instance in ol.instances:
            ol.instances = [i for i in ol.instances if i != instance]
            #print("\tRemoved instance {} from overlay of {}".format(instance, ol.template))
            logging.info("\tRemoved instance {} from overlay of {}".format(instance, ol.template))

        edges_to_remove = [e for e in ol.edges if e.source == instance or e.dest == instance]
        for e in edges_to_remove:
            remove_edge(e, overlay)


# remove the specified edge from all overlays/specified overlay and instances
def remove_edge(edge, overlay=None):
    # remove mapped dr
    for f in edge.flows:
        del f.dr[edge]
    # remove edge from specified overlay or from all (if none is specified) and update flows
    for ol in overlays.values():
        if ol == overlay or overlay is None:
            if edge in ol.edges:
                ol.edges.remove(edge)
            for i in ol.instances:
                i.edges_in = {key: e for key, e in i.edges_in.items() if e != edge}
                i.edges_out = {key: e for key, e in i.edges_out.items() if e != edge}
    #print("\tRemoved edge {}".format(edge))
    logging.info("\tRemoved edge {}".format(edge))


# remove specified flow: remove mapping from/to edges, remove edges that are now "empty" (without mapped flows)
def remove_flow(overlay, flow):
    #print("Removing outdated flow {} and corresponding edges (without other flows)".format(flow))
    logging.info("Removing outdated flow {} and corresponding edges (without other flows)".format(flow))
    for e in list(overlay.edges):		# iterate over copy as edges are removed during loop
        # remove mappings
        if flow in e.flows:
            e.flows.remove(flow)
            del flow.dr[e]

        # remove empty edges
        if not e.flows:
            remove_edge(e, overlay)


# return dict of currently consumed node resources
# ignore the idle cpu/mem consumption of the instances of component specified in ignore_idle
def consumed_node_resources(ignore_idle=None):
    consumed_cpu, consumed_mem = {}, {}
    # reused instances exist in multiple overlays with diff ingoing edges -> have to allow duplicates (use list)
    instances = [i for t in overlays.keys() for i in overlays[t].instances]
    for v in nodes.ids:
        consumed_cpu[v] = sum(i.consumed_cpu(ignore_idle) for i in instances if i.location == v)
        consumed_mem[v] = sum(i.consumed_mem(ignore_idle) for i in instances if i.location == v)
    return consumed_cpu, consumed_mem


# return dict of nodes with enough remaining node resources (based on delta_dr and the components requirements)
# ignoring nodes that are too far away, i.e., with a too high delay, and that are on the tabu list
# keys: nodes, values: (remaining cpu, remaining mem)
def candidate_nodes(start_node, arc, delta_dr, tabu=set()):
    # increase ingoing dr: delta_dr at corresponding input, 0 elsewhere
    delta_in_dr = []
    for i in range(arc.dest.inputs + arc.dest.inputs_back):
        if arc.direction == "forward" and i == arc.dest_in:
            delta_in_dr.append(delta_dr)
        elif arc.direction == "backward" and i == arc.dest.inputs + arc.dest_in:
            delta_in_dr.append(delta_dr)
        else:
            delta_in_dr.append(0)

    # get currently consumed node resources without idle consumption of dest-instances (to avoid subtracting it twice)
    consumed_cpu, consumed_mem = consumed_node_resources(arc.dest)

    # only consider nodes that are close enough (short delay) and that are not on the tabu list for the component
    allowed_nodes = [v for v in nodes.ids if shortest_paths[(start_node, v)][2] <= arc.max_delay and (arc.dest, v) not in tabu]

    # check each node and add it if it has any of the required resources remaining
    candidates = OrderedDict()
    for v in allowed_nodes:
        remaining_cpu = nodes.cpu[v] - consumed_cpu[v]
        remaining_mem = nodes.mem[v] - consumed_mem[v]

        if remaining_cpu - arc.dest.cpu_req(delta_in_dr) >= 0 and remaining_mem - arc.dest.mem_req(delta_in_dr) >= 0:
            candidates[v] = (remaining_cpu, remaining_mem)

    return candidates


# return the best node to create an edge to (from a given location, along a given arc, excluding the tabu-instance)
# FUTURE WORK: favor nodes with suitable instances -> encourage reuse of existing instances -> better objective 2
def find_best_node(overlay, start_location, arc, delta_dr, fixed, tabu):
    # candidate nodes with enough remaining node capacity
    candidates = candidate_nodes(start_location, arc, delta_dr, tabu)
    #print("\tCandidate nodes for component {}:".format(arc.dest))
    logging.debug("\tCandidate nodes for component {}:".format(arc.dest))
    for v in candidates.keys():
        #print("\t\t{} with {}".format(v, candidates[v]))
        logging.debug("\t\t{} with {}".format(v, candidates[v]))

    # fixed instances need special treatment: cannot be added or removed => enforce reuse
    if fixed:
        #print("Component {} has fixed instances, which have to be used (no new instances allowed)".format(arc.dest))
        logging.info("Component {} has fixed instances, which have to be used (no new instances allowed)".format(arc.dest))
        fixed_nodes = [i.location for i in overlay.instances if i.component == arc.dest and
                       shortest_paths[(start_location, i.location)][2] <= arc.max_delay]
        candidates = {node: resources for node, resources in candidates.items() if node in fixed_nodes}

    # check all candidate nodes and place instance at node with lowest resulting path-weight (high dr, low delay)
    if len(candidates) > 0:
        path_weight = OrderedDict()
        for v in candidates.keys():
            path_weight[v] = shortest_paths[(start_location, v)][1]
        best_node = min(path_weight, key=path_weight.get)

    # if no nodes have remaining capacity, choose node with lowest over-subscription (within delay bounds)
    else:
        #print("No nodes with enough remaining resources. Choosing node with lowest over-subscription.")
        logging.info("No nodes enough remaining resources. Choosing node with lowest over-subscription.")
        consumed_cpu, consumed_mem = consumed_node_resources()
        best_node = None
        min_over_subscription = math.inf
        min_path_weight = math.inf  # path weight of current best node, use as tie breaker
        # only allow nodes that are close enough, i.e., with low enough delay, and that are not tabu
        allowed_nodes = [v for v in nodes.ids if shortest_paths[(start_location, v)][2] <= arc.max_delay
                         and (arc.dest, v) not in tabu]
        # if fixed, only allow nodes of fixed instances => enforce reuse
        if fixed:
            allowed_nodes = fixed_nodes
        for v in allowed_nodes:
            # looking at sum of cpu and memory over-subscription to find nodes with little over-sub of both
            over_subscription = (consumed_cpu[v] - nodes.cpu[v]) + (consumed_mem[v] - nodes.mem[v])
            if over_subscription <= min_over_subscription:
                path_weight = shortest_paths[(start_location, v)][1]
                if over_subscription < min_over_subscription or path_weight < min_path_weight:
                    best_node = v
                    min_over_subscription = over_subscription
                    min_path_weight = path_weight

    return best_node


# map the specified flow (with specified flow_dr) to a possibly new edge from the start_instance
def map_flow2edge(overlay, start_instance, arc, flow, flow_dr, tabu):
    # determine if the instances of the destination component are fixed => if so, cannot place new instances
    fixed = False
    for i in overlay.instances:
        if i.component == arc.dest and i.fixed:
            fixed = True
            break
    best_node = find_best_node(overlay, start_instance.location, arc, flow_dr, fixed, tabu)

    # if the instance at best node already exists (e.g., from forward dir), just connect to it, else create anew
    # look for existing instance
    instance_exists = False
    for i in overlay.instances:
        if i.component == arc.dest and i.location == best_node:
            instance_exists = True
            dest_instance = i
            break
    # create new instance if none exists in the overlay
    if not instance_exists:
        dest_instance = Instance(arc.dest, best_node)
        overlay.instances.append(dest_instance)
        #print("\tAdded new instance {} at best node {} (may exist in other overlays)".format(dest_instance, best_node))
        logging.info("\tAdded new instance {} at best node {} (may exist in other overlays)".format(dest_instance, best_node))

    # check if edge to dest_instance already exists
    edge_exists = False
    if instance_exists:
        if dest_instance in start_instance.edges_out.keys():
            edge_exists = True
            edge = start_instance.edges_out[dest_instance]

    # if it doesn't exist, create a new edge and assign a path (shortest path)
    if not edge_exists:
        edge = Edge(arc, start_instance, dest_instance)
        overlay.edges.append(edge)
        edge.paths.append(shortest_paths[(start_instance.location, dest_instance.location)][0])

    # map flow to edge
    flow.dr[edge] = flow_dr
    edge.flows.append(flow)
    #print("\tMapped flow {} (dr {}) to edge {} (new: {})".format(flow, flow_dr, edge, not edge_exists))
    logging.info("\tMapped flow {} (dr {}) to edge {} (new: {})".format(flow, flow_dr, edge, not edge_exists))


# map out_flows to edges back to the same stateful instances that were passed in fwd direction
def map_flows2stateful(overlay, start_instance, arc, out_flows):
    # remove any existing mappings of flows to edges along the arc
    for e in start_instance.edges_out.values():
        if e.arc == arc:
            e.flows = []

    # add currently outgoing flows to edges back to stateful instances (create edges if necessary)
    for f in out_flows:
        dest_inst = f.passed_stateful[arc.dest]
        if dest_inst in start_instance.edges_out.keys():
            new_edge = False
            edge = start_instance.edges_out[dest_inst]
        else:
            new_edge = True
            edge = Edge(arc, start_instance, dest_inst)
            edge.paths.append(shortest_paths[(start_instance.location, dest_inst.location)][0])
            overlay.edges.append(edge)
        f.dr[edge] = out_flows[f]
        edge.flows.append(f)
        #print("\tMapped flow {} (dr {}) to edge {} (new: {}) back to same stateful instance".format(f, out_flows[f], edge, new_edge))
        logging.info("\tMapped flow {} (dr {}) to edge {} (new: {}) back to same stateful instance".format(f, out_flows[f], edge, new_edge))


# update the mapping of flows leaving the start_instances along the specified edge
def update_flow_mapping(overlay, start_instance, arc, out_flows, tabu):
    flow_mapping = {f: e for e in start_instance.edges_out.values() if e.arc == arc for f in e.flows}

    # remove outdated flows
    for f in list(flow_mapping.keys()):
        if f not in out_flows:
            del f.dr[flow_mapping[f]]
            flow_mapping[f].flows.remove(f)
            del flow_mapping[f]
            #print("\tRemoved outdated flow {} along {}".format(f, arc))

    # enforce return of flows to the same stateful instances as passed in fwd direction
    if arc.dest.stateful and arc.direction == "backward":
        map_flows2stateful(overlay, start_instance, arc, out_flows)
    # update dr of mapped flows and map new ones
    else:
        # sort flows for determinism and reproducibility (same results with same key)
        ordered_flows = [f for f in sorted(out_flows, key=lambda flow: flow.id)]
        # shuffle order to achieve different order of mapping in different iterations; maintains determinism and reproducibility (due to same key)
        random.shuffle(ordered_flows)
        for f in ordered_flows:		# sort according to flow.id to ensure determinism
            if f in flow_mapping:
                f.dr[flow_mapping[f]] = out_flows[f]		# update data rate
                #print("\tUpdated dr of existing flow {} (Now: {})".format(f, f.dr[flow_mapping[f]]))
                # FUTURE WORK: maybe check if capacitiy violated => if yes, reassign flow to different edge; but might also be fixed during iterative improvement
            else:
                map_flow2edge(overlay, start_instance, arc, f, out_flows[f], tabu)
                # FUTURE WORK: maybe try to minimize number of edges or number of new edges by combining flows to one edge or preferring existing edges (opj 2)

    # remove empty edges
    for e in start_instance.edges_out.values():
        if e.arc == arc and not e.flows:
            #print("\nRemoved empty edge {}".format(e))
            logging.info("\nRemoved empty edge {}".format(e))
            remove_edge(e, overlay)


# update sources (add, rem), update source flows, reset passed_stateful of all flows
def update_sources(overlay, sources):
    # reset passed_stateful for all flows (set up to date later) and remove outdated flows
    #print("Reset passed_stateful for all flows of template {}".format(overlay.template))
    src_flows = {f for src in sources for f in src.flows}
    mapped_flows = {f for e in overlay.edges for f in e.flows} | {f for src in sources for f in src.flows}
    for f in mapped_flows:
        f.passed_stateful.clear()
        if f not in src_flows:
            remove_flow(overlay, f)

    # add/update source instances
    for src in sources:
        # get existing source instance at the location
        src_exists = False
        for i in overlay.instances:
            if i.component == src.component and i.location == src.location:
                src_exists = True
                break

        # update or add source instance depending on whether such an instance already exists or not
        if src_exists:
            # remove outdated flows
            for f in i.src_flows:
                if f not in src.flows:
                    i.src_flows.remove(f)
                    for e in f.dr:
                        e.flows.remove(f)
                    f.dr.clear()
                    f.passed_stateful.clear()

            # update or add new flows
            for f in src.flows:
                # if the flow already exists, keep the existing flow and only update its src_dr
                if f in i.src_flows:
                    new_src_dr = f.src_dr
                    f = i.src_flows[i.src_flows.index(f)]		# get existing flow object in i.src_flows
                    f.src_dr = new_src_dr
                # else add the new flow
                else:
                    i.src_flows.append(f)
                f.passed_stateful[i.component] = i
            #print("Updated/checked src_flows of existing source instance {}".format(i))
            logging.info("Updated/checked src_flows of existing source instance {}".format(i))
        else:
            src_instance = Instance(src.component, src.location, src.flows)
            overlay.instances.append(src_instance)
            #print("Added new source instance {}".format(src_instance))
            logging.info("Added new source instance {}".format(src_instance))

    # remove old source instances without source
    source_instances = [i for i in overlay.instances if i.component.source]
    for src in source_instances:
        corresponding_sources = {s for s in sources if s.component == src.component and s.location == src.location}
        if len(corresponding_sources) == 0:
            #print("Remove source instance {} without corresponding source".format(src))
            logging.info("Remove source instance {} without corresponding source".format(src))
            remove_instance(src)


# create an initial solution for the provided input
def solve(arg_nodes, arg_links, templates, prev_overlays, sources, fixed, arg_shortest_paths, tabu=set()):
    # print("Previous overlays:")
    # for ol in prev_overlays.values():
    #     ol.print()
    # tabu_string = ""
    # for i in tabu:
    #     tabu_string += "({},{}) ".format(i[0], i[1])
    #     print("Tabu list: {}".format(tabu_string))

    # write global variables
    global nodes, links, shortest_paths, overlays
    nodes = arg_nodes
    links = arg_links
    shortest_paths = arg_shortest_paths

    # keep previous overlays of templates that still exist
    overlays = {t: ol for t, ol in prev_overlays.items() if t in templates}

    # create empty overlays for new templates
    for t in templates:
        if t not in overlays.keys():
            overlays[t] = Overlay(t, [], [])
            #print("Created empty overlay for new template {}".format(t))
            logging.info("Created empty overlay for new template {}".format(t))

    # remove all instances of fixed components => curr fixed instances added again later; prev fixed instances removed
    fixed_components = {f.component for f in fixed}
    fixed_instances = {i for ol in overlays.values() for i in ol.instances if i.component in fixed_components}
    #print("Remove any existing fixed instances:", *fixed_instances, sep=" ")
    for i in fixed_instances:
        remove_instance(i)

    # embed templates sequentially in given order
    for t in templates:
        #print("\n-Embedding template: {}-".format(t))
        logging.info("-Embedding template: {}-".format(t))

        own_sources = [src for src in sources if src.component in t.components]
        update_sources(overlays[t], own_sources)

        # add fixed instances that match template t's components
        for f in fixed:
            if f.component in t.components:
                fixed_instance = Instance(f.component, f.location, fixed=True)
                if fixed_instance not in overlays[t].instances:
                    overlays[t].instances.append(fixed_instance)
                    #print("Added fixed instance of {} at {}".format(f.component, f.location))
                    logging.info("Added fixed instance of {} at {}".format(f.component, f.location))

        # iterate over all instances in topological order; start in forward direction then switch to backward
        i = 0
        direction = "forward"
        while i < len(overlays[t].topological_order()):
            instance = overlays[t].topological_order()[i]
            # #print("Topological order:", *overlays[t].topological_order(), sep=" ")

            # remove unused instances (except fixed instances)
            if not instance.fixed:
                if not instance.used(direction, overlays[t]):
                    #print("Removed unused instance {} from overlay of {}".format(instance, t))
                    logging.info("Removed unused instance {} from overlay of {}".format(instance, t))
                    remove_instance(instance, overlays[t])
                    continue

            # switch direction at the first instance of an end component (bc outgoing not ingoing direction considered)
            if instance.component.end:
                direction = "backward"

            # get outgoing flows (and their dr) for each output
            out_flows = instance.out_flows(direction)
            for k in range(len(out_flows)):
                arc = out_arc(t, instance.component, k, direction)
                # when a component is adapted for reuse, it has separate outputs for the arcs of different templates
                if arc is None:			# for output k, this template has no arc => skip to next output
                    #print("{}'s outgoing arc at output {} in {} direction belongs to a different template. The output is skipped".format(instance, k, direction))
                    logging.debug("{}'s outgoing arc at output {} in {} direction belongs to a different template. The output is skipped".format(instance, k, direction))
                    continue

                update_flow_mapping(overlays[t], instance, arc, out_flows[k], tabu)
                #print("Updated the flow mapping along arc {} at {}\n".format(arc, instance))
                logging.info("Updated the flow mapping along arc {} at {}\n".format(arc, instance))

            i += 1

        #print()
        if overlays[t].empty():
            del overlays[t]
            #print("Deleted empty overlay of {}".format(t))
            logging.info("Deleted empty overlay of {}".format(t))
       # else:
            #overlays[t].print()
            #print("Topological order:", *overlays[t].topological_order(), sep=" ")
        #print()

    return overlays
