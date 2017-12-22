import csv
from collections import defaultdict
from datetime import datetime
from gurobipy import *
import bjointsp.objective as objective
from bjointsp.heuristic import shortest_paths as sp


# save variable values globally => allows assigning and writing with nice format in separate functions
max_cpu, max_mem, max_dr = 0, 0, 0
cpu_exceeded, mem_exceeded, dr_exceeded = {}, {}, {}
instance, changed, cpu, mem = {}, {}, {}, {}
ingoing_fwd, ingoing_bwd, outgoing_fwd, outgoing_bwd = {}, {}, {}, {}
edge, edge_delay, link_dr, link_used, passes, flow_dr = {}, {}, defaultdict(int), {}, {}, {}		# default link_dr = 0


# reset all global variables (between multiple runs)
def reset_global():
	global max_cpu, max_mem, max_dr
	global cpu_exceeded, mem_exceeded, dr_exceeded
	global instance, changed, cpu, mem
	global ingoing_fwd, ingoing_bwd, outgoing_fwd, outgoing_bwd
	global edge, edge_delay, link_dr, link_used, passes, flow_dr

	max_cpu, max_mem, max_dr = 0, 0, 0
	cpu_exceeded, mem_exceeded, dr_exceeded = {}, {}, {}
	instance, changed, cpu, mem = {}, {}, {}, {}
	ingoing_fwd, ingoing_bwd, outgoing_fwd, outgoing_bwd = {}, {}, {}, {}
	edge, edge_delay, link_dr, link_used, passes, flow_dr = {}, {}, defaultdict(int), {}, {}, {}  # default link_dr = 0


# split link-string (eg., "('a', 'b')") into the two node names (eg., "a" and "b")
def split_link(link):
	split = link[1:-1].split(", ")  		# cut off parenthesis and split, removing the ", "
	start = split[0].replace("'", "")  		# get rid of ' around the node-names
	end = split[1].replace("'", "")
	return start, end


# write all variables in a nice format (sorted for easier comparability)
def write_variables(writer, links, heuristic):
	# objective info
	writer.writerow(["# objective info: type value"])
	writer.writerow(["num_cpu_ex {}".format(len(cpu_exceeded))])
	writer.writerow(["num_mem_ex {}".format(len(mem_exceeded))])
	writer.writerow(["num_dr_ex {}".format(len(dr_exceeded))])
	writer.writerow(["instances {}".format(len(instance))])
	writer.writerow(["changed {}".format(len(changed))])
	total_delay = 0
	for v in link_used:
		total_delay += links.delay[(v[3], v[4])]
	writer.writerow(["total_delay {}".format(total_delay)])
	total_cpu = 0
	for v in cpu:
		total_cpu += cpu[v]
	writer.writerow(["total_cpu {}".format(total_cpu)])
	total_mem = 0
	for v in mem:
		total_mem += mem[v]
	writer.writerow(["total_mem {}".format(total_mem)])
	total_dr = 0
	for v in link_dr:
		total_dr += link_dr[v]
	writer.writerow(["total_dr {}".format(total_dr)])
	writer.writerow("")

	# capacity violations
	writer.writerow(("max_cpu_over-subscription:", max_cpu))
	writer.writerow(("max_mem_over-subscription:", max_mem))
	writer.writerow(("max_dr_over-subscription:", max_dr))

	writer.writerow("")

	writer.writerow(["# cpu exceeded: node"])
	for v in sorted(cpu_exceeded):
		writer.writerow([v])					# node
	writer.writerow("")

	writer.writerow(["# mem exceeded: node"])
	for v in sorted(mem_exceeded):
		writer.writerow([v])					# node
	writer.writerow("")

	writer.writerow(["# dr exceeded: link-start link-end"])
	for v in sorted(dr_exceeded):
		writer.writerow((v[0], v[1]))  				# node, node
	writer.writerow("")


	# most relevant overlay information: instances, edges
	writer.writerow(["# instances: component node"])

	for v in sorted(instance):
		writer.writerow((v[0], v[1]))					# component, node
	writer.writerow("")

	writer.writerow(["# edges: arc start-node end-node flow"])
	for v in sorted(edge):
		writer.writerow((v[0], v[1], v[2], v[3]))  			# arc, node, node, flow
	writer.writerow("")


	# remaining variables
	writer.writerow(["# edge delays: arc start-node end-node delay"])
	for v in sorted(edge_delay):
		writer.writerow((v[0], v[1], v[2], edge_delay[v]))  # arc, node, node: delay
	writer.writerow("")

	writer.writerow(["# passes: dir component node flow"])
	if heuristic:
		writer.writerow(["# heuristic only records passed_stateful"])
	for v in sorted(passes):
		writer.writerow((v[0], v[1], v[2], v[3]))		# direction, comp, node, flow
	writer.writerow("")

	writer.writerow(["# changed: component node"])
	for v in sorted(changed):
		writer.writerow((v[0], v[1]))  					# component, node
	writer.writerow("")

	writer.writerow(["# cpu req: component node cpu_req"])
	for v in sorted(cpu):
		writer.writerow((v[0], v[1], cpu[v]))  						# component, node: value
	writer.writerow("")

	writer.writerow(["# mem req: component node mem_req"])
	for v in sorted(mem):
		writer.writerow((v[0], v[1], mem[v]))  						# component, node: value
	writer.writerow("")

	# these variables are only recorded by the MIP, not the heuristic
	if not heuristic:
		writer.writerow(["# ingoing fwd: component node flow port data_rate"])
		for v in sorted(ingoing_fwd):
			writer.writerow((v[0], v[1], v[2], v[3], ingoing_fwd[v]))  		# component, node, flow, port: dr
		writer.writerow("")

		writer.writerow(["# ingoing bwd: component node flow port data_rate"])
		for v in sorted(ingoing_bwd):
			writer.writerow((v[0], v[1], v[2], v[3], ingoing_bwd[v]))  		# component, node, flow, port: dr
		writer.writerow("")

		writer.writerow(["# outgoing fwd: component node flow port data_rate"])
		for v in sorted(outgoing_fwd):
			writer.writerow((v[0], v[1], v[2], v[3], outgoing_fwd[v]))  		# component, node, flow, port: dr
		writer.writerow("")

		writer.writerow(["# outgoing bwd: component node flow port data_rate"])
		for v in sorted(outgoing_bwd):
			writer.writerow((v[0], v[1], v[2], v[3], outgoing_bwd[v]))  		# component, node, flow, port: dr
		writer.writerow("")

	writer.writerow(["# link dr: arc-start arc-end link-start link-end data_rate"])
	for v in sorted(link_dr):
		writer.writerow((v[0], v[1], v[2], v[3], v[4], link_dr[v]))  	# arc, node, node, node, node: dr
	writer.writerow("")

	writer.writerow(["# link used: arc-start arc-end link-start link-end"])
	for v in sorted(link_used):
		writer.writerow((v[0], v[1], v[2], v[3], v[4]))  	# arc, node, node, node, node
	writer.writerow("")

	if heuristic:
		writer.writerow(["# flow_dr: flow edge dr"])
		for v in sorted(flow_dr):
			writer.writerow((v[0], v[1], flow_dr[v]))  	# arc, node, node, node, node
		writer.writerow("")


# prepare result-file based on scenario-file: in results-subdirectory, using scenario name + timestamp (+ seed + event)
# heuristic results also add the seed and event number; MIP results can add repetition instead
def create_result_file(scenario, subfolder, event="", seed=None, seed_subfolder=False, obj=None, bounds=""):
	# create subfolder for current objective
	obj_folder = ""
	if obj is not None:
		if obj == objective.COMBINED:
			obj_folder = "/combined"
		elif obj == objective.OVER_SUB:
			obj_folder = "/over-sub"
		elif obj == objective.CHANGED:
			obj_folder = "/changed"
		elif obj == objective.RESOURCES:
			obj_folder = "/resources"
		elif obj == objective.DELAY:
			obj_folder = "/delay"

	input_file = os.path.basename(scenario)
	input_directory = os.path.dirname(scenario)
	# put result in seed-subfolder
	if seed is not None and seed_subfolder:
		result_directory = os.path.join(input_directory, "../results/" + subfolder + obj_folder + "/{}".format(seed))
	else:
		result_directory = os.path.join(input_directory, "../results/" + subfolder + obj_folder)
	# add seed to result name
	if seed is None:
		seed = ""
	else:
		seed = "_{}".format(seed)
	split_file = input_file.split(".")
	timestamp = datetime.now().strftime("_%Y-%m-%d_%H-%M-%S")
	result_file = split_file[0] + timestamp + bounds + seed + event + "." + split_file[1]
	result_path = os.path.join(result_directory, result_file)

	os.makedirs(os.path.dirname(result_path), exist_ok=True)  # create subdirectories if necessary

	return result_path


# write input-scenario into
def write_scenario(writer, scenario, sources):
	writer.writerow(["Input: {}".format(scenario)])
	# copy scenario file into result file, ignoring comments and empty lines
	with open(scenario, "r") as scenario_file:
		reader = csv.reader((row for row in scenario_file if not row.startswith("#")), delimiter=" ")
		for row in reader:
			if len(row) > 0:
				writer.writerow(row)

	# write info about sources: #flows, #sources, total source dr
	writer.writerow(["flow_number: {}".format(sum(len(src.flows) for src in sources))])
	writer.writerow(["source_number: {}".format(len(sources))])
	source_dr = sum(f.src_dr for src in sources for f in src.flows)
	writer.writerow(["source_dr: {}".format(source_dr)])
	writer.writerow("")


# calculate the number of capacity violations based on the consumed resources and node capacities (after saving vars)
def num_cap_exceeded(nodes, links):
	global cpu_exceeded, mem_exceeded, dr_exceeded

	for v in nodes.ids:
		req_resources = 0
		instances_at_v = [i for i in cpu if i[1] == v]
		for i in instances_at_v:
			req_resources += cpu[i]
		if req_resources > nodes.cpu[v]:
			cpu_exceeded[v] = 1

	for v in nodes.ids:
		req_resources = 0
		instances_at_v = [i for i in mem if i[1] == v]
		for i in instances_at_v:
			req_resources += mem[i]
		if req_resources > nodes.mem[v]:
			mem_exceeded[v] = 1

	for l in links.ids:
		req_resources = 0
		edges_at_l = [e for e in link_dr if e[3] == l[0] and e[4] == l[1]]
		for e in edges_at_l:
			req_resources += link_dr[e]
		if req_resources > links.dr[l]:
			dr_exceeded[l] = 1


# save all variables with values != 0
# all values are rounded (to 3 digits after comma or to integer if integer variable) to prevent wrong results
def save_mip_variables(model):
	# access global variables
	global max_cpu, max_mem, max_dr
	global cpu_exceeded, mem_exceeded, dr_exceeded
	global instance, changed, cpu, mem
	global ingoing_fwd, ingoing_bwd, outgoing_fwd, outgoing_bwd
	global edge, edge_delay, link_dr, link_used, passes

	for v in model.getVars():
		# only write vars that are >0 (all others have to be 0); round to ignore values like 1e-10 that are basically 0
		if round(v.x, 3) > 0:
			if v.varName.startswith("max_cpu"):
				max_cpu = round(v.x, 3)
			elif v.varName.startswith("max_mem"):
				max_mem = round(v.x, 3)
			elif v.varName.startswith("max_dr"):
				max_dr = round(v.x, 3)

			elif v.varName.startswith("cpu_exceeded"):
				split = v.varName.split("_")  # cpu_exceeded_node
				cpu_exceeded[split[2]] = round(v.x)
			elif v.varName.startswith("mem_exceeded"):
				split = v.varName.split("_")  # mem_exceeded_node
				mem_exceeded[split[2]] = round(v.x)
			elif v.varName.startswith("dr_exceeded"):
				split = v.varName.split("_")  # dr_exceeded_link
				link = split_link(split[2])  	# split link into two nodes
				dr_exceeded[(link[0], link[1])] = round(v.x)

			elif v.varName.startswith("instance"):
				split = v.varName.split("_")  # instance_component_node
				instance[(split[1], split[2])] = round(v.x)
			elif v.varName.startswith("changed"):
				split = v.varName.split("_")  # changed_component_node
				changed[(split[1], split[2])] = round(v.x)
			elif v.varName.startswith("cpu_req"):
				split = v.varName.split("_")  # cpu_req_component_node
				cpu[(split[2], split[3])] = round(v.x, 3)
			elif v.varName.startswith("mem_req"):
				split = v.varName.split("_")  # mem_req_component_node
				mem[(split[2], split[3])] = round(v.x, 3)

			elif v.varName.startswith("ingoing_fwd"):
				split = v.varName.split("_")  # ingoing_fwd_component_node_flow_port
				ingoing_fwd[(split[2], split[3], split[4], split[5])] = round(v.x, 3)
			elif v.varName.startswith("ingoing_bwd"):
				split = v.varName.split("_")  # ingoing_bwd_component_node_flow_port
				ingoing_bwd[(split[2], split[3], split[4], split[5])] = round(v.x, 3)
			elif v.varName.startswith("outgoing_fwd"):
				split = v.varName.split("_")  # outgoing_fwd_component_node_flow_port
				outgoing_fwd[(split[2], split[3], split[4], split[5])] = round(v.x, 3)
			elif v.varName.startswith("outgoing_bwd"):
				split = v.varName.split("_")  # outgoing_bwd_component_node_flow_port
				outgoing_bwd[(split[2], split[3], split[4], split[5])] = round(v.x, 3)

			elif v.varName.startswith("edge_delay"):
				split = v.varName.split("_")  # edge_delay_arc_node_node
				edge_delay[(split[2], split[3], split[4])] = round(v.x, 3)
			elif v.varName.startswith("edge"):
				split = v.varName.split("_")  # edge_arc_node_node_flow
				edge[(split[1], split[2], split[3], split[4])] = round(v.x)
			elif v.varName.startswith("link_dr"):
				split = v.varName.split("_")  # link_dr_arc_node_node_link
				link = split_link(split[5])		# split link into two nodes
				link_dr[(split[2], split[3], split[4], link[0], link[1])] = round(v.x, 3)
			elif v.varName.startswith("link_used"):
				split = v.varName.split("_")  # link_used_arc_node_node_link
				link = split_link(split[5])  	# split link into two nodes
				link_used[(split[2], split[3], split[4], link[0], link[1])] = round(v.x)
			elif v.varName.startswith("passes"):
				split = v.varName.split("_")  	# passes_dir_component_node_flow
				passes[(split[1], split[2], split[3], split[4])] = round(v.x)

			else:
				raise ValueError("Unkown variable {}".format(v.varName))


def write_mip_result(model, scenario, nodes, links, obj, sources, bounds=None, rep=None, rep_subfolder=False):
	reset_global()
	bounds_str = ""
	if bounds is not None:
		# bounds_str = "_({},{},{})".format(bounds[0], bounds[1], bounds[2])
		bounds_str = "_({},{})".format(bounds[0], bounds[1])
	result_file = create_result_file(scenario, "mip", obj=obj, bounds=bounds_str, seed=rep, seed_subfolder=rep_subfolder)

	with open(result_file, "w", newline="") as csvfile:
		writer = csv.writer(csvfile, delimiter="\t")
		print("Writing solution to {}".format(result_file))

		# write input information
		writer.writerow(["End time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
		if rep is not None:
			writer.writerow(["Repetition: {}".format(rep)])
		write_scenario(writer, scenario, sources)
		writer.writerow(("Model:", model.ModelName))
		if obj == objective.COMBINED:
			writer.writerow(["Objective: COMBINED"])
		elif obj == objective.OVER_SUB:
			writer.writerow(["Objective: OVER_SUB"])
		elif obj == objective.DELAY:
			writer.writerow(["Objective: DELAY"])
		elif obj == objective.CHANGED:
			writer.writerow(["Objective: CHANGED"])
		elif obj == objective.RESOURCES:
			writer.writerow(["Objective: RESOURCES"])
		else:
			raise ValueError("Objective {} unknown".format(obj))
		writer.writerow(["Bounds: {}".format(bounds)])
		writer.writerow("")

		# write solution details
		if model.status == GRB.status.OPTIMAL:
			# write general information
			writer.writerow(["Optimal solution found"])				# strings with spaces -> list -> no splitting
			writer.writerow(("Runtime:", model.Runtime))
			writer.writerow(("Objective value:", round(model.objVal, 3)))
			writer.writerow(("Gap:", model.MIPGap))
			writer.writerow("")

			save_mip_variables(model)
			num_cap_exceeded(nodes, links)
			write_variables(writer, links, False)

		elif model.status == GRB.status.INTERRUPTED or model.status == GRB.status.SUBOPTIMAL:
			# write best solution
			writer.writerow(["Sub-optimal solution found"])
			writer.writerow(("model.status:", model.status))
			writer.writerow(("Runtime:", model.Runtime))
			writer.writerow(("Objective value:", round(model.objVal, 3)))
			writer.writerow(("Gap:", model.MIPGap, 5))
			writer.writerow("")

			save_mip_variables(model)
			num_cap_exceeded(nodes, links)
			write_variables(writer, links, False)

		elif model.status == GRB.status.INFEASIBLE:
			writer.writerow(("model.status:", model.status))

		return result_file


def save_heuristic_variables(changed_instances, instances, edges, nodes, links):
	# access global variables; in-/outgoing-drs and linked variables not set because not relevant for objective
	global max_cpu, max_mem, max_dr
	global cpu_exceeded, mem_exceeded, dr_exceeded
	global instance, changed, cpu, mem
	global ingoing_fwd, ingoing_bwd, outgoing_fwd, outgoing_bwd
	global edge, edge_delay, link_dr, link_used, passes, flow_dr

	# node capacity violations
	for v in nodes.ids:
		over_cpu = sum(i.consumed_cpu() for i in instances if i.location == v) - nodes.cpu[v]
		if over_cpu > 0:
			cpu_exceeded[v] = 1
			if over_cpu > max_cpu:
				max_cpu = over_cpu
		over_mem = sum(i.consumed_mem() for i in instances if i.location == v) - nodes.mem[v]
		if over_mem > 0:
			mem_exceeded[v] = 1
			if over_mem > max_mem:
				max_mem = over_mem

	# consumed node resources
	for i in instances:
		instance[(i.component.name, i.location)] = 1
		cpu[(i.component.name, i.location)] = i.consumed_cpu()
		mem[(i.component.name, i.location)] = i.consumed_mem()

	# changed instances (compared to previous embedding)
	for i in changed_instances:
		changed[(i.component.name, i.location)] = 1

	# edge and link data rate, used links
	consumed_dr = defaultdict(int)		# default = 0
	for e in edges:
		for f in e.flows:
			edge[(str(e.arc), e.source.location, e.dest.location, f.id)] = 1
		for path in e.paths:
			# record edge delay: all flows take the same (shortest) path => take path delay
			edge_delay[(str(e.arc), e.source.location, e.dest.location)] = sp.path_delay(links, path)

			# go through nodes of each path and increase the dr of the traversed links
			for i in range(len(path) - 1):
				# skip connections on the same node (no link used)
				if path[i] != path[i+1]:
					# assume the edge dr is split equally among all paths (currently only 1 path per edge)
					link_dr[(str(e.arc), e.source.location, e.dest.location, path[i], path[i+1])] += e.flow_dr() / len(e.paths)
					consumed_dr[(path[i], path[i+1])] += e.flow_dr() / len(e.paths)
					link_used[(str(e.arc), e.source.location, e.dest.location, path[i], path[i+1])] = 1

	# link capacity violations
	for l in links.ids:
		if links.dr[l] < consumed_dr[l]:
			dr_exceeded[l] = 1
			if consumed_dr[l] - links.dr[l] > max_dr:
				max_dr = consumed_dr[l] - links.dr[l]

	# passed_stateful, flow_dr
	flows = [f for e in edges for f in e.flows]
	for f in flows:
		for j, i in f.passed_stateful.items():
			passes[("both", j.name, i.location, f.id)] = 1		# passes_dir_component_node_flow
		for e, dr in f.dr.items():
			flow_dr[(f.id, str(e))] = dr			# flow, edge: dr


def write_heuristic_result(init_time, runtime, obj_value, changed, overlays, scenario, obj, event_no, event, nodes, links, seed, seed_subfolder, sources):
	reset_global()

	# initial embedding
	if event_no == -1:
		result_file = create_result_file(scenario, "heuristic", seed=seed, seed_subfolder=seed_subfolder, obj=obj)
	# updated embedding after event
	else:
		result_file = create_result_file(scenario, "heuristic", event="_event{}".format(event_no), seed=seed, seed_subfolder=seed_subfolder, obj=obj)

	with open(result_file, "w", newline="") as csvfile:
		writer = csv.writer(csvfile, delimiter="\t")
		print("Writing solution to {}".format(result_file))

		# write input information
		writer.writerow(["End time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
		writer.writerow(["Seed: {}".format(seed)])
		write_scenario(writer, scenario, sources)
		writer.writerow(["Model: Heuristic"])
		if obj == objective.COMBINED:
			writer.writerow(["Objective: COMBINED"])
		elif obj == objective.OVER_SUB:
			writer.writerow(["Objective: OVER_SUB"])
		elif obj == objective.DELAY:
			writer.writerow(["Objective: DELAY"])
		elif obj == objective.CHANGED:
			writer.writerow(["Objective: CHANGED"])
		elif obj == objective.RESOURCES:
			writer.writerow(["Objective: RESOURCES"])
		else:
			raise ValueError("Objective {} unknown".format(obj))
		writer.writerow(["Event: {} (Event {})".format(event, event_no)])
		writer.writerow("")

		# write solution details
		writer.writerow(["Pre-computation of shortest paths: {}".format(init_time)])
		writer.writerow(["Runtime: {}".format(runtime)])
		writer.writerow(["Objective value: {}".format(obj_value)])
		writer.writerow("")

		instances, edges = set(), set()
		for ol in overlays:
			instances.update(ol.instances)
			edges.update(ol.edges)
		save_heuristic_variables(changed, instances, edges, nodes, links)
		write_variables(writer, links, True)

	return result_file
