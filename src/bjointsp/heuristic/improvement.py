import copy
import random
import logging
from bjointsp.heuristic import control
from bjointsp.heuristic import heuristic


nodes, links, shortest_paths, overlays = None, None, None, None


# reset overlay of specified template and update flows in the overlays_to_modify
# keep instances and edges before the specified instance (less changes, shorter runtime)
def reset_overlay(template, instance, overlays_to_modify):
    overlay = overlays_to_modify[template]

    # only keep instances before the specified instance (in topological order)
    order = overlay.topological_order()
    index = order.index(instance)
    instances_to_keep = order[:index]

    # remove other instances and associated edges:
    overlay.instances = [i for i in overlay.instances if i in instances_to_keep]
    overlay.edges = [e for e in overlay.edges if e.source in instances_to_keep and e.dest in instances_to_keep]

    # update the in-/outgoing edges of all instances
    for i in overlay.instances:
        i.edges_in = {key: e for key, e in i.edges_in.items() if e in overlay.edges}
        i.edges_out = {key: e for key, e in i.edges_out.items() if e in overlay.edges}

    # update flows
    flows = [f for i in overlay.instances if i.src_flows for f in i.src_flows]
    for f in flows:
        f.dr = {e:dr for e,dr in f.dr.items() if e in overlay.edges}
        f.passed_stateful = {j:i for j,i in f.passed_stateful.items() if i in overlay.instances}


# iteratively improve the specified overlays
def improve(arg_nodes, arg_links, templates, arg_overlays, sources, fixed, arg_shortest_paths):
    # write global variables
    global nodes, links, shortest_paths, overlays
    nodes = arg_nodes
    links = arg_links
    shortest_paths = arg_shortest_paths
    overlays = arg_overlays

    # three different solutions (overlays): incumbent, modified (by current iteration), best
    best_overlays = copy.deepcopy(overlays)
    incumbent_overlays = copy.deepcopy(overlays)

    # outer loop: iteratively improve the overlays
    total_outer_iterations = 0
    unsuccessful_iterations = 0			# unsuccessful = best solution not improved; iteration = outer loop (modify all)
    max_unsuccessful_iterations = 20
    while unsuccessful_iterations < max_unsuccessful_iterations:
        total_outer_iterations += 1
        unsuccessful_iterations += 1

        # reset to incumbent solution before next modifications (only once per outer loop iteration)
        modified_overlays = copy.deepcopy(incumbent_overlays)

        # inner loop: modify templates' overlays in predefined order
        # pick instance of each overlay, add it to tabu-list, reset overlay, and solve anew
        # FUTURE WORK: smarter than random? e.g., such instances that could be used in both direction but aren't?
        for t in templates:
            # an overlay may be deleted if it has no source -> skip the template and its overlay
            if t not in modified_overlays.keys():
                continue
            ol = modified_overlays[t]
            ol.print()

            # set random instance to tabu and remove it and following instances
            # FUTURE WORK: keep instances in tabu-list for multiple iterations?
            tabu = set()  # set of forbidden instances tuples: (component, location)
            # ignore source or fixed instances, which have to be at a specific location
            non_fixed_instances = [i for i in ol.instances if not i.component.source and not i.fixed]
            if len(non_fixed_instances) == 0:
                print("Skip modification of {}'s overlay because all instances are fixed".format(t))
                logging.info("Skip modification of {}'s overlay because all instances are fixed".format(t))
                continue
            rand_instance = random.choice(non_fixed_instances)
            tabu.add((rand_instance.component, rand_instance.location))

            print("\n--Iteration {}: Modifying overlay of {}--".format(total_outer_iterations, ol.template))
            print("Set random instance {} of {}'s overlay to tabu and rebuild overlay".format(rand_instance, ol.template))
            logging.info("--Iteration {}: Modifying overlay of {}--".format(total_outer_iterations, ol.template))
            logging.info("Set random instance {} of {}'s overlay to tabu and rebuild overlay".format(rand_instance, ol.template))

            reset_overlay(ol.template, rand_instance, modified_overlays)
            modified_overlays = heuristic.solve(nodes, links, templates, modified_overlays, sources, fixed, shortest_paths, tabu)

            # update solution
            new_obj_value = control.objective_value(modified_overlays)
            print("Objective value of modified overlays: {}".format(new_obj_value))
            logging.info("Objective value of modified overlays: {}".format(new_obj_value))
            incumbent_obj_value = control.objective_value(incumbent_overlays)
            if new_obj_value < incumbent_obj_value:
                print("\tImproved objective value -> new incumbent solution")
                logging.info("\tImproved objective value -> new incumbent solution")
                incumbent_overlays = copy.deepcopy(modified_overlays)
                if new_obj_value < control.objective_value(best_overlays):
                    print("\tNew best solution")
                    logging.info("\tNew best solution")
                    best_overlays = copy.deepcopy(modified_overlays)
                    unsuccessful_iterations = 0
            # even update incumbent solution if it is slightly worse (50% chance)
            elif new_obj_value <= 1.1 * incumbent_obj_value:
                if random.random() < 0.5:
                    print("\tOnly slightly worse objective value; new incumbent solution")
                    logging.info("\tOnly slightly worse objective value; new incumbent solution")
                    incumbent_overlays = copy.deepcopy(modified_overlays)
                else:
                    print("\tOnly slightly worse objective value; solution discarded")
                    logging.info("\tOnly slightly worse objective value; solution discarded")
            else:
                print("\tWorse objective value -> solution discarded after last inner loop")
                logging.info("\tWorse objective value -> solution discarded after this iteration")
                # keep using modified_overlays during the remainder of the inner loop

    print("\n---Heuristic finished---")
    print("Total outer loop iterations: {}".format(total_outer_iterations))
    logging.info("---Heuristic finished---")
    logging.info("Total outer loop iterations: {}".format(total_outer_iterations))
    print("Best overlays:")
    for ol in best_overlays.values():
        ol.print()

    return best_overlays
