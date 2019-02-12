import os
import yaml
from collections import defaultdict
from datetime import datetime
import bjointsp.objective as objective
from bjointsp.heuristic import shortest_paths as sp
import networkx as nx


# prepare result-file based on scenario-file: in results-subdirectory, using scenario name + timestamp (+ seed + event)
# heuristic results also add the seed and event number; MIP results can add repetition instead
def create_result_file(input_files, subfolder, seed=None, seed_subfolder=False, obj=None):
    file_name = ""
    # add basename of each input file to the output filename
    for f in input_files:
        if f is not None:
            file_name += os.path.basename(f).split(".")[0] + "-"
    # put result in seed-subfolder
    if seed is not None and seed_subfolder:
        result_directory = os.path.join("results/" + subfolder + "/{}".format(seed))
    else:
        result_directory = os.path.join("results/" + subfolder)
    # add seed to result name
    if seed is None:
        seed = ""
    else:
        seed = "_{}".format(seed)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    result_file = file_name + timestamp + seed + ".yaml"
    result_path = os.path.join(result_directory, result_file)

    os.makedirs(os.path.dirname(result_path), exist_ok=True)  # create subdirectories if necessary

    return result_path


# add variable values to the result dictionary
def save_heuristic_variables(result, changed_instances, instances, edges, nodes, links):
    # save placement
    result["placement"] = {"vnfs": [], "vlinks": []}
    for i in instances:
        vnf = {"name": i.component.name, "node": i.location, "image": i.component.config}
        result["placement"]["vnfs"].append(vnf)
    result["metrics"]["num_instances"] = len(result["placement"]["vnfs"])

    for e in edges:
        vlink = {"src_vnf": e.source.component.name, "src_node": e.source.location,
                 "dest_vnf": e.dest.component.name, "dest_node": e.dest.location}
        result["placement"]["vlinks"].append(vlink)

    # node capacity violations
    result["placement"]["cpu_oversub"] = []
    result["placement"]["mem_oversub"] = []
    max_cpu, max_mem = 0, 0
    for v in nodes.ids:
        over_cpu = sum(i.consumed_cpu() for i in instances if i.location == v) - nodes.cpu[v]
        if over_cpu > 0:
            result["placement"]["cpu_oversub"].append({"node": v})
            if over_cpu > max_cpu:
                max_cpu = over_cpu
        over_mem = sum(i.consumed_mem() for i in instances if i.location == v) - nodes.mem[v]
        if over_mem > 0:
            result["placement"]["mem_oversub"].append({"node": v})
            if over_mem > max_mem:
                max_mem = over_mem
    result["metrics"]["max_cpu_oversub"] = max_cpu
    result["metrics"]["max_mem_oversub"] = max_mem

    # consumed node resources
    result["placement"]["alloc_node_res"] = []
    for i in instances:
        resources = {"name": i.component.name, "node": i.location, "cpu": i.consumed_cpu(), "mem": i.consumed_mem()}
        result["placement"]["alloc_node_res"].append(resources)

    # changed instances (compared to previous embedding)
    result["metrics"]["changed"] = []
    for i in changed_instances:
        result["metrics"]["changed"].append({"name": i.component.name, "node": i.location})
    result["metrics"]["num_changed"] = len(result["metrics"]["changed"])

    # edge and link data rate, used links
    result["placement"]["flows"] = []
    result["metrics"]["path_delays"] = []
    result["metrics"]["vnf_delays"] = []
    result["metrics"]["total_path_delay"] = 0
    result["metrics"]["total_vnf_delay"] = 0
    result['metrics']["total_delay"] = 0
    result["placement"]["links"] = []
    consumed_dr = defaultdict(int)		# default = 0
    for e in edges:
        for f in e.flows:
            flow = {"arc": str(e.arc), "src_node": e.source.location, "dst_node": e.dest.location, "flow_id": f.id}
            result["placement"]["flows"].append(flow)
        for path in e.paths:
            # record edge delay: all flows take the same (shortest) path => take path delay
            path_delay = {"src": e.arc.source.name, "dest": e.arc.dest.name, "src_node": e.source.location, "dest_node": e.dest.location, "path_delay": sp.path_delay(links, path)}
            result["metrics"]["path_delays"].append(path_delay)
            result["metrics"]["total_path_delay"] += sp.path_delay(links, path)
            result["metrics"]["total_delay"] += sp.path_delay(links, path)

            # go through nodes of each path and increase the dr of the traversed links
            for i in range(len(path) - 1):
                # skip connections on the same node (no link used)
                if path[i] != path[i+1]:
                    consumed_dr[(path[i], path[i+1])] += e.flow_dr() / len(e.paths)
                    link = {"arc": str(e.arc), "edge_src": e.source.location, "edge_dst": e.dest.location, "link_src": path[i], "link_dst": path[i+1]}
                    result["placement"]["links"].append(link)

    # record VNF delay
    for i in instances:
        vnf_delay = {"vnf": i.component.name, "vnf_delay": i.component.vnf_delay}
        result["metrics"]["vnf_delays"].append(vnf_delay)
        result["metrics"]["total_vnf_delay"] += i.component.vnf_delay

    # record total delay = link + vnf delay
    result["metrics"]["total_delay"] = result["metrics"]["total_path_delay"] + result["metrics"]["total_vnf_delay"]


    # link capacity violations
    result["placement"]["dr_oversub"] = []
    max_dr = 0
    for l in links.ids:
        if links.dr[l] < consumed_dr[l]:
            result["placement"]["dr_oversub"].append({"link": l})
            if consumed_dr[l] - links.dr[l] > max_dr:
                max_dr = consumed_dr[l] - links.dr[l]
    result["metrics"]["max_dr_oversub"] = max_dr

    return result


def write_heuristic_result(runtime, obj_value, changed, overlays, input_files, obj, nodes, links, seed, seed_subfolder):
    result_file = create_result_file(input_files, "bjointsp", seed=seed, seed_subfolder=seed_subfolder, obj=obj)

    instances, edges = set(), set()
    for ol in overlays:
        instances.update(ol.instances)
        edges.update(ol.edges)

    # construct result as dictionary for writing into YAML result file
    result = {"time": datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
              "input": {"network": os.path.basename(input_files[0]),
                        "service": os.path.basename(input_files[1]),
                        "sources": os.path.basename(input_files[2]),
                        "fixed": "None",
                        "prev_embedding": "None",
                        "seed": seed,
                        "algorithm": "bjointsp",
                        "objective": obj},
              "metrics": {"runtime": runtime,
                          "obj_value": obj_value}}

    # set file of fixed instances and of previous embedding if they are specified
    if input_files[3] is not None:
        result["input"]["fixed"] = os.path.basename(input_files[3])
    if input_files[4] is not None:
        result["input"]["prev_embedding"] = os.path.basename(input_files[4])

    # add input details to simplify evaluation: network size, etc
    network = nx.read_graphml(input_files[0])
    result["input"]["num_nodes"] = network.number_of_nodes()
    result["input"]["num_edges"] = network.number_of_edges()
    with open(input_files[1]) as f:
        service = yaml.load(f)
        result["input"]["num_vnfs"] = len(service["vnfs"])
    with open(input_files[2]) as f:
        sources = yaml.load(f)
        result["input"]["num_sources"] = len(sources)

    result = save_heuristic_variables(result, changed, instances, edges, nodes, links)

    with open(result_file, "w", newline="") as outfile:
        yaml.dump(result, outfile, default_flow_style=False)
        print("Writing solution to {}".format(result_file))

    return result_file
