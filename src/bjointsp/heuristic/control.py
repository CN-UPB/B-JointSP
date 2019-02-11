import math
import time
import logging
import bjointsp.objective as objective
from collections import defaultdict
from bjointsp.heuristic import heuristic
from bjointsp.heuristic import improvement
from bjointsp.heuristic import shortest_paths as sp
from bjointsp.overlay.instance import Instance


# global variables for easy access by all functions
nodes, links, prev_instances, obj = None, None, None, None


# return dict of currently consumed node resources based on the instances of the specified overlays
def consumed_node_resources(overlays):
    consumed_cpu, consumed_mem = {}, {}
    # reused instances exist in multiple overlays with diff ingoing edges -> have to allow duplicates -> use list not set
    instances = [i for t in overlays.keys() for i in overlays[t].instances]
    for v in nodes.ids:
        consumed_cpu[v] = sum(i.consumed_cpu() for i in instances if i.location == v)
        consumed_mem[v] = sum(i.consumed_mem() for i in instances if i.location == v)
    return consumed_cpu, consumed_mem


# return the objective value based on the specified overlays
def objective_value(overlays, print_info=False):
    # check delay of each edge; if too high, return math.inf for infeasible/infinity
    edges = [e for ol in overlays.values() for e in ol.edges]
    for e in edges:
        for path in e.paths:
            if sp.path_delay(links, path) > e.arc.max_delay:
                print("Embedding INFEASIBLE because delay of path of {} is too high".format(e))
                logging.warning("Embedding INFEASIBLE because delay of path of {} is too high".format(e))
                return math.inf

    # calculate changed instances (compared to previous instances)
    curr_instances = {i for ol in overlays.values() for i in ol.instances}
    changed = prev_instances ^ curr_instances  # instances that are were added or removed
    # record max over-subscription of node capacities
    consumed_cpu, consumed_mem = consumed_node_resources(overlays)
    max_cpu_over, max_mem_over = 0, 0
    for v in nodes.ids:
        if consumed_cpu[v] - nodes.cpu[v] > max_cpu_over:
            max_cpu_over = consumed_cpu[v] - nodes.cpu[v]
        if consumed_mem[v] - nodes.mem[v] > max_mem_over:
            max_mem_over = consumed_mem[v] - nodes.mem[v]

    # calculate data rate of each link and mark used links for each edge
    consumed_dr = defaultdict(int)		# default = 0
    link_used = {}
    edges = [e for ol in overlays.values() for e in ol.edges]
    for e in edges:
        for path in e.paths:
            # go along nodes of the path and increment data rate of each traversed link
            for i in range(len(path) - 1):
                # skip connections on same node without a link (both inst at same node)
                if path[i] != path[i + 1]:
                    # assume the edge dr is split equally among all paths (currently only 1 path per edge)
                    consumed_dr[(path[i], path[i+1])] += e.flow_dr() / len(e.paths)
                    link_used[(e.arc, e.source.location, e.dest.location, path[i], path[i+1])] = 1

    # record max over-subscription of link capacitiy
    max_dr_over = 0
    for l in links.ids:
        if consumed_dr[l] - links.dr[l] > max_dr_over:
            max_dr_over = consumed_dr[l] - links.dr[l]

    # calculate total delay over all used links (by different edges)
    total_delay = 0
    for key in link_used:
        total_delay += links.delay[(key[3], key[4])]

    # calculate total vnf delay of each node and add it to total_delay
    vnf_delays = 0
    for i in curr_instances:
        vnf_delays += i.component.vnf_delay

    # adding vnf_delay to total_delay
    total_delay += vnf_delays
    
    # calculate total consumed resources
    total_consumed_cpu = sum(consumed_cpu[v] for v in nodes.ids)
    total_consumed_mem = sum(consumed_mem[v] for v in nodes.ids)
    total_consumed_dr = sum(consumed_dr[l] for l in links.ids)

    # print objective value info
    if print_info:
        print("Max over-subscription: {} (cpu), {} (mem), {} (dr)".format(max_cpu_over, max_mem_over, max_dr_over))
        print("Total delay: {}, Num changed instances: {}".format(total_delay, len(changed)))
        print("Total consumed resources: {} (cpu), {} (mem), {} (dr)".format(total_consumed_cpu, total_consumed_mem, total_consumed_dr))
        logging.info("Max over-subscription: {} (cpu), {} (mem), {} (dr)".format(max_cpu_over, max_mem_over, max_dr_over))
        logging.info("Total delay: {}, Num changed instances: {}".format(total_delay, len(changed)))
        logging.info("Total consumed resources: {} (cpu), {} (mem), {} (dr)".format(total_consumed_cpu, total_consumed_mem, total_consumed_dr))

    # calculate objective value; objectives & weights have to be identical to the MIP
    # lexicographical combination of all objectives
    if obj == objective.COMBINED:
        w1 = 100 * 1000 * 1000  	# assuming changed instances < 100
        w2 = 1000 * 1000  			# assuming total resource consumption < 1000
        w3 = 1000  					# assuming total delay < 1000
        value = w1 * (max_cpu_over + max_mem_over + max_dr_over)
        value += w2 * len(changed)
        value += w3 * (total_consumed_cpu + total_consumed_mem + total_consumed_dr)
        value += total_delay

    # minimize max over-subscription
    elif obj == objective.OVER_SUB:
        value = max_cpu_over + max_mem_over + max_dr_over

    # minimize changed instances (compared to previous embedding)
    elif obj == objective.CHANGED:
        value = len(changed)

    # minimize total resource consumption
    elif obj == objective.RESOURCES:
        value = total_consumed_cpu + total_consumed_mem + total_consumed_dr

    # minimize total delay
    elif obj == objective.DELAY:
        value = total_delay

    else:
        logging.error("Objective {} unknown".format(obj))
        raise ValueError("Objective {} unknown".format(obj))

    return value


# return a dict with the total source data rate for each source component
def total_source_drs(sources):
    src_drs = defaultdict(int)  # default = 0
    for src in sources:
        src_drs[src.component] += src.dr
    return src_drs


def solve(arg_nodes, arg_links, templates, prev_overlays, sources, fixed, arg_obj):
    # write global variables
    global nodes, links, prev_instances, obj
    nodes = arg_nodes
    links = arg_links
    # copy previous instances (attributes like edges_in etc are not needed and not copied)
    prev_instances = {Instance(i.component, i.location, i.src_flows) for ol in prev_overlays.values() for i in ol.instances}
    obj = arg_obj

    # print input
    print("Templates:", *templates, sep=" ")
    print("Sources:", *sources, sep=" ")
    print("Fixed instances:", *fixed, sep=" ")
    print("Previous instances:", *prev_instances, sep=" ")

    # pre-computation of shortest paths
    start_init = time.time()
    shortest_paths = sp.all_pairs_shortest_paths(nodes, links)
    init_time = time.time() - start_init
    print("Time for pre-computation of shortest paths: {}s\n".format(init_time))
    logging.info("Time for pre-computation of shortest paths: {}s\n".format(init_time))

    start_heuristic = time.time()
    # get total source data rate for each source component (for sorting the templates later)
    src_drs = defaultdict(int)  # default = 0
    for src in sources:
        src_drs[src.component] += src.total_flow_dr()

    # sort templates with decreasing weight: heaviest/most difficult templates get embedded first
    templates.sort(key=lambda t: t.weight(src_drs[t.source()]), reverse=True)
    print("Templates sorted to start with heaviest:", *templates, sep=" ")

    # initial solution
    #print("\n----- Initial solution -----")
    logging.info("----- Initial solution -----")
    overlays = heuristic.solve(arg_nodes, arg_links, templates, prev_overlays, sources, fixed, shortest_paths)
    obj_value = objective_value(overlays)
    #print("Objective value of initial solution: {}".format(obj_value))
    #print("Runtime for initial solution: {}".format(time.time() - start_heuristic))
    logging.info("Objective value of initial solution: {}".format(obj_value))
    logging.info("Runtime for initial solution: {}\n".format(time.time() - start_heuristic))


    # iterative improvement
    if len(nodes.ids) > 1:		# doesn't work for networks with just 1 node
        #print("\n----- Iterative improvement -----")
        logging.info("----- Iterative improvement -----")
        overlays = improvement.improve(arg_nodes, arg_links, templates, overlays, sources, fixed, shortest_paths)
        obj_value = objective_value(overlays)
        runtime = time.time() - start_heuristic
        #print("Objective value after improvement: {}".format(obj_value))
        #print("Heuristic runtime: {}s".format(runtime))
        logging.info("Objective value after improvement: {}".format(obj_value))
        logging.info("Heuristic runtime: {}s".format(runtime))
    else:
        runtime = time.time() - start_heuristic
        #print("Skip iterative improvement for network with just 1 node")
        logging.info("Skip iterative improvement for network with just 1 node")

    # calculate changed instances for writing result
    curr_instances = {i for ol in overlays.values() for i in ol.instances}
    changed = prev_instances ^ curr_instances  # instances that were added or removed

    return init_time, runtime, obj_value, changed, overlays
